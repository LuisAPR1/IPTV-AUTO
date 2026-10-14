"""Automação do site Fast CCCam / ServicePortal IPTV Trial usando sessões HTTP."""

import os
import re
import logging
import random
import time
import requests
import threading
from collections import Counter
from contextvars import copy_context
from datetime import datetime
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup

from config import (
    BASE_URL, PORTAL_URL, HEADLESS, DEFAULT_TIMEOUT, NAVIGATION_TIMEOUT, USER_AGENT, 
    PROXY_URL, USE_TOR, TOR_PROXY, USE_PROXY_LIST, PROXY_LIST_FILE,
    USE_PROXYSCRAPE, PROXYSCRAPE_TYPES, PROXYSCRAPE_TIMEOUT,
    PROXYSCRAPE_COUNTRY, PROXYSCRAPE_MAX, MAX_PROXY_RETRIES, ERROR_LOG_FILE
)
from proxy_manager import SimpleProxyManager
from email_service import TempMailService
from diagnostics import diagnostic_event, has_active_run, register_secrets, sanitize_text

logger = logging.getLogger(__name__)


class IPTVScraper:
    """Automação do site Fast CCCam / ServicePortal IPTV Trial."""

    def __init__(self, email_service: TempMailService, ui=None, progress_callback=None):
        self.email_service = email_service
        self.ui = ui
        self.progress_callback = progress_callback
        self.proxy_manager: Optional[SimpleProxyManager] = None
        self._current_proxy: Optional[str] = None
        self.session = self._new_session()
        self.current_step_name: str = "Início / Preparação"
        self.last_email_created: str = ""
        self.last_error: str = ""
        self._probe_lock = threading.Lock()
        self._probe_failures = Counter()

    @staticmethod
    def _record_http_response(response, *args, **kwargs):
        """Regista apenas metadados HTTP; o coletor sanitiza o URL."""
        diagnostic_event(
            "http", "Resposta HTTP",
            method=response.request.method,
            url=response.url,
            status_code=response.status_code,
            duration_ms=round(response.elapsed.total_seconds() * 1000, 1),
        )

    def _new_session(self):
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        session.hooks["response"].append(self._record_http_response)
        return session

    def _ui_step(self, step_index: int, message: str = ""):
        """Atualiza UI se disponível e guarda o passo atual."""
        self.current_step_name = f"Passo {step_index}: {message}" if message else f"Passo {step_index}"
        if self.ui:
            self.ui.update(step_index, message)
        if self.progress_callback:
            try:
                self.progress_callback(step_index, message)
            except Exception:
                pass
    
    def _get_proxy_manager(self) -> SimpleProxyManager:
        """Inicializa o proxy manager (sempre com ProxyScrape ativo para evitar bloqueio de IP no checkout)."""
        if self.proxy_manager is None:
            self.proxy_manager = SimpleProxyManager(
                proxy_file=PROXY_LIST_FILE if USE_PROXY_LIST else "",
                use_proxyscrape=True,
                proxyscrape_types=PROXYSCRAPE_TYPES,
                proxyscrape_timeout=PROXYSCRAPE_TIMEOUT,
                proxyscrape_country=PROXYSCRAPE_COUNTRY,
                proxyscrape_max=PROXYSCRAPE_MAX,
                direct_proxy=PROXY_URL
            )
        return self.proxy_manager
    
    def _pre_test_proxy(self, proxy_url: str, timeout: int = 8) -> Optional[float]:
        """Testa se um proxy consegue aceder diretamente ao portal de trial via HTTPS."""
        try:
            masked = proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url
            start = time.time()
            resp = requests.get(
                f"{PORTAL_URL}/store/single-users/trial-admin",
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=False,
                hooks={"response": self._record_http_response},
            )
            latency = time.time() - start
            if resp.status_code in (200, 301, 302):
                logger.info(f"✅ {masked} → {latency:.1f}s (status {resp.status_code})")
                return latency
            else:
                with self._probe_lock:
                    self._probe_failures[f"http_{resp.status_code}"] += 1
                return None
        except Exception as exc:
            with self._probe_lock:
                self._probe_failures[type(exc).__name__] += 1
            return None

    def _find_working_proxy(self, pm: SimpleProxyManager, max_tests: int = 500) -> Optional[str]:
        """Encontra o proxy funcional mais rápido."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        MAX_LATENCY = 8.0
        BATCH_SIZE = 5
        tested = 0
        with self._probe_lock:
            self._probe_failures.clear()
        
        while tested < max_tests and pm.has_proxies():
            batch = []
            for _ in range(BATCH_SIZE):
                if tested >= max_tests or not pm.has_proxies():
                    break
                proxy = pm.get_next_proxy()
                if proxy:
                    batch.append(proxy)
                    tested += 1
            if not batch:
                break
            
            results = {}
            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                futures = {
                    executor.submit(copy_context().run, self._pre_test_proxy, p, 8): p
                    for p in batch
                }
                for future in as_completed(futures):
                    proxy = futures[future]
                    try:
                        lat = future.result()
                        if lat is not None:
                            results[proxy] = lat
                    except Exception:
                        pass
            
            fast_proxies = {p: lat for p, lat in results.items() if lat <= MAX_LATENCY}
            if fast_proxies:
                best = min(fast_proxies, key=fast_proxies.get)
                for p in batch:
                    if p != best:
                        pm.mark_failed(p)
                diagnostic_event("proxy_search", "Procura de proxy concluída", tested=tested,
                                 found=True, failure_counts=dict(self._probe_failures))
                return best
            for p in batch:
                pm.mark_failed(p)
        diagnostic_event("proxy_search", "Nenhum proxy funcional encontrado", tested=tested,
                         found=False, failure_counts=dict(self._probe_failures))
        return None

    def _human_delay(self, min_seconds: float = 0.3, max_seconds: float = 1.0):
        """Adiciona delay aleatório para simular comportamento humano."""
        time.sleep(random.uniform(min_seconds, max_seconds))

    def _detect_payment_method(self, soup: BeautifulSoup) -> str:
        """Auto-deteta o método de pagamento disponível na página de checkout.
        
        Procura inputs radio com name='paymentmethod' e retorna o valor do
        primeiro que estiver checked, ou o primeiro disponível.
        
        Ordem de preferência:
        1. Gateway marcado como checked (default do site)
        2. 'creditcardmodule' (funciona para trials $0.00)
        3. 'plisio' (crypto - alternativa)
        4. Qualquer outro gateway disponível
        5. Fallback: 'creditcardmodule'
        
        Returns:
            str: Valor do paymentmethod a enviar no checkout
        """
        payment_inputs = soup.find_all("input", {"name": "paymentmethod"})
        
        if not payment_inputs:
            logger.warning("Nenhum gateway encontrado na página. A usar 'creditcardmodule' como fallback.")
            return "creditcardmodule"
        
        available = []
        checked_value = None
        
        for inp in payment_inputs:
            value = inp.get("value", "")
            if value:
                available.append(value)
                if inp.get("checked") is not None:
                    checked_value = value
        
        logger.info(f"Gateways disponíveis: {available}")
        
        # 1. Usar o que está checked por defeito
        if checked_value:
            logger.info(f"Gateway default (checked): {checked_value}")
            return checked_value
        
        # 2. Ordem de preferência para trials gratuitos
        preferred = ["creditcardmodule", "plisio"]
        for pref in preferred:
            if pref in available:
                return pref
        
        # 3. Qualquer um disponível
        if available:
            return available[0]
        
        return "creditcardmodule"

    def _run_single_attempt(self, proxy_url: str = None) -> Optional[Dict[str, str]]:
        """Executa uma tentativa completa de obtenção de trial."""
        REQUEST_TIMEOUT = 25
        try:
            # Reiniciar sessão HTTP para limpar cookies, carrinho e proxies de tentativas anteriores
            self.session.close()
            self.session = self._new_session()
            if proxy_url:
                self.session.proxies = {"http": proxy_url, "https": proxy_url}

            # 1. Email Temporário
            self._ui_step(1, "Criando email temporário...")
            logger.info("=== PASSO 1: Criar email temporário ===")
            email = self.email_service.create_inbox()
            register_secrets(email)
            self.last_email_created = email
            logger.info("Email criado com sucesso")

            # 2. Aceder ao portal de trial
            self._ui_step(2, "Acedendo ao portal de trial Fast CCCam...")
            logger.info("=== PASSO 2: Aceder ao portal de trial ===")
            trial_portal_url = f"{PORTAL_URL}/store/single-users/trial-admin"
            r1 = self.session.get(trial_portal_url, timeout=REQUEST_TIMEOUT)
            
            if r1.status_code != 200 and "confproduct" not in r1.url:
                raise RuntimeError(f"Resposta inesperada no portal de trial (status code: {r1.status_code})")
            
            soup1 = BeautifulSoup(r1.text, "html.parser")
            token1_el = soup1.find("input", {"name": "token"})
            token1 = token1_el.get("value") if token1_el else ""
            register_secrets(token1)
            diagnostic_event("portal", "Página inicial analisada", token_present=bool(token1))

            # 3. Configurar Produto de 48h
            self._ui_step(3, "Configurando produto 48h trial...")
            logger.info("=== PASSO 3: Configurar produto ===")
            conf_payload = {
                "token": token1,
                "configure": "true",
                "i": "0",
                "customfield[126]": ""  # Bouquets (vazio = todos)
            }
            r2 = self.session.post(
                f"{PORTAL_URL}/cart.php?a=confproduct&i=0",
                data=conf_payload,
                timeout=REQUEST_TIMEOUT
            )
            
            # 4. Aceder à página de Checkout
            self._ui_step(4, "Preparando página de checkout...")
            logger.info("=== PASSO 4: Aceder ao checkout ===")
            r3 = self.session.get(f"{PORTAL_URL}/cart.php?a=checkout", timeout=REQUEST_TIMEOUT)
            soup3 = BeautifulSoup(r3.text, "html.parser")
            
            chk_form = soup3.find("form", {"id": "frmCheckout"})
            token3_el = chk_form.find("input", {"name": "token"}) if chk_form else soup3.find("input", {"name": "token"})
            token3 = token3_el.get("value") if token3_el else token1
            register_secrets(token3)
            diagnostic_event(
                "checkout", "Página de checkout analisada",
                form_present=chk_form is not None, token_present=bool(token3),
            )

            # 5. Solicitar Código de Verificação por Email
            self._ui_step(5, "Solicitando código de verificação por email...")
            logger.info("=== PASSO 5: Solicitar código de verificação ===")
            ajax_url = f"{PORTAL_URL}/modules/addons/ValidEmail/ajaxhandler.php"
            r_send = self.session.post(
                ajax_url,
                data={"action": "sendvalidcode", "email": email},
                timeout=REQUEST_TIMEOUT
            )
            logger.info(
                "Resposta envio código: HTTP %s, %s caracteres, sucesso=%s",
                r_send.status_code, len(r_send.text), "success" in r_send.text,
            )

            if "success" not in r_send.text:
                raise RuntimeError(
                    f"[email_send_failed] Falha ao enviar código de verificação "
                    f"(HTTP {r_send.status_code}; resposta sem indicação de sucesso)"
                )

            # 6. Aguardar Código por IMAP
            self._ui_step(6, "Aguardando código no email...")
            logger.info("=== PASSO 6: Aguardar código por email ===")
            code = self.email_service.get_verification_code()
            register_secrets(code)
            if not code:
                raise RuntimeError("Código de verificação não recebido por email (timeout)")

            logger.info("✓ Código de verificação obtido")

            # 7. Validar Código no Servidor
            self._ui_step(6, "Validando código no servidor...")
            logger.info("=== PASSO 7: Validar código no servidor ===")
            r_val = self.session.post(
                ajax_url,
                data={"action": "validatecode", "email": email, "validatecode": code},
                timeout=REQUEST_TIMEOUT
            )
            logger.info(
                "Resposta validação código: HTTP %s, %s caracteres, validado=%s",
                r_val.status_code, len(r_val.text), r_val.text.strip() == "1",
            )

            if r_val.text.strip() != "1":
                raise RuntimeError(
                    f"[verification_rejected] Validação de código falhou no servidor "
                    f"(HTTP {r_val.status_code}; resposta diferente da confirmação esperada)"
                )

            logger.info("✓ Código verificado com sucesso!")

            # 8. Re-obter token fresco (o anterior pode ter expirado após os AJAX calls)
            self._ui_step(7, "Finalizando encomenda do trial...")
            logger.info("=== PASSO 8: Finalizar checkout ===")
            r3_fresh = self.session.get(f"{PORTAL_URL}/cart.php?a=checkout", timeout=REQUEST_TIMEOUT)
            soup3_fresh = BeautifulSoup(r3_fresh.text, "html.parser")
            chk_form_fresh = soup3_fresh.find("form", {"id": "frmCheckout"})
            if chk_form_fresh:
                token_fresh_el = chk_form_fresh.find("input", {"name": "token"})
            else:
                token_fresh_el = soup3_fresh.find("input", {"name": "token"})
            token_fresh = token_fresh_el.get("value") if token_fresh_el else token3
            register_secrets(token_fresh)
            logger.info("Token de checkout presente: %s", bool(token_fresh))

            # Auto-detetar método de pagamento disponível na página
            payment_method = self._detect_payment_method(soup3_fresh)
            logger.info(f"Método de pagamento selecionado: {payment_method}")

            suffix = self.email_service.personal_service.generated_suffix or "user1234"
            fn = f"User{suffix[:4]}"
            ln = f"Test{suffix[4:]}"
            # Password simples alfanumérica (8-64 chars, sem caracteres especiais)
            pw = f"Tr1alPass{suffix}"
            register_secrets(pw)

            checkout_payload = {
                "token": token_fresh,
                "submit": "true",
                "custtype": "new",
                "firstname": fn,
                "lastname": ln,
                "email": email,
                "phonenumber": "912345678",
                "companyname": "",
                "address1": "Rua Principal 123",
                "address2": "",
                "city": "Lisboa",
                "state": "Lisboa",
                "postcode": "1000-001",
                "country": "PT",
                "password": pw,
                "password2": pw,
                "paymentmethod": payment_method,
                "accepttos": "on"
            }

            r_checkout = self.session.post(
                f"{PORTAL_URL}/cart.php?a=checkout",
                data=checkout_payload,
                timeout=REQUEST_TIMEOUT
            )
            logger.info("Checkout submetido. URL: %s", sanitize_text(r_checkout.url))

            # Verificar se o checkout foi bem sucedido
            if "a=complete" not in r_checkout.url:
                err_msg = "Checkout não completou (não foi redirecionado para a=complete)"
                soup_err = BeautifulSoup(r_checkout.text, "html.parser")
                for alert in soup_err.find_all("div", class_=lambda c: c and "alert" in c):
                    alert_text = alert.get_text(strip=True)
                    if alert_text and "correct" in alert_text.lower():
                        err_msg = "[checkout_rejected] O formulário de checkout solicitou correções"
                raise RuntimeError(err_msg)

            logger.info("✓ Checkout completado com sucesso!")

            # 9. Extrair Credenciais da página de confirmação
            self._ui_step(7, "Extraindo credenciais do serviço IPTV...")
            logger.info("=== PASSO 9: Extrair credenciais ===")
            credentials = self.extract_credentials_from_confirmation(r_checkout.text)
            credentials['email_used'] = email

            self._ui_step(7, "Concluído com sucesso!")
            return credentials

        except Exception as e:
            logger.error("Erro na tentativa de automação (%s): %s", type(e).__name__, sanitize_text(str(e)))
            raise

    def extract_credentials_from_confirmation(self, html: str) -> Dict[str, str]:
        """Extrai credenciais IPTV da página de confirmação de encomenda (cart.php?a=complete).
        
        A página de confirmação contém as credenciais em texto:
        - M3U URL: http://s1.dnspass.xyz/get.php?username=XXX&password=YYY&type=m3u_plus&output=ts
        - EPG URL: http://s1.dnspass.xyz/xmltv.php?username=XXX&password=YYY
        - Server URL: http://s1.dnspass.xyz:80
        - Username: XXX
        - Password: YYY
        
        Returns:
            Dict com username, password, dns, epg, m3u, url
        """
        credentials = {
            "username": "",
            "password": "",
            "dns": "",
            "epg": "",
            "m3u": "",
            "url": ""
        }

        try:
            soup = BeautifulSoup(html, "html.parser")
            page_text = soup.get_text(separator="\n", strip=True)
            
            logger.debug(f"Texto da página de confirmação ({len(page_text)} chars)")

            # 1. Extrair M3U URL (mais fiável — contém username e password nos parâmetros)
            m3u_match = re.search(r'(https?://[^\s]+/get\.php\?username=[^\s]+)', page_text)
            if m3u_match:
                credentials["m3u"] = m3u_match.group(1)
                register_secrets(credentials["m3u"])
                logger.info("✓ M3U URL extraído")

            # 2. Extrair EPG URL
            epg_match = re.search(r'(https?://[^\s]+/xmltv\.php\?username=[^\s]+)', page_text)
            if epg_match:
                credentials["epg"] = epg_match.group(1)
                register_secrets(credentials["epg"])
                logger.info("✓ EPG URL extraído")

            # 3. Extrair Username e Password — PRIORIDADE do M3U URL (texto colado causa problemas)
            if credentials["m3u"]:
                u_match = re.search(r'username=([^&\s]+)', credentials["m3u"])
                p_match = re.search(r'password=([^&\s]+)', credentials["m3u"])
                if u_match:
                    credentials["username"] = u_match.group(1)
                    register_secrets(credentials["username"])
                    logger.info("✓ Username extraído")
                if p_match:
                    credentials["password"] = p_match.group(1)
                    register_secrets(credentials["password"])
                    logger.info("✓ Password extraída")

            # Fallback texto: tentar "Username: XXX" se não veio do M3U
            if not credentials["username"]:
                user_match = re.search(r'Username:\s*([A-Za-z0-9_]+)', page_text)
                if user_match:
                    credentials["username"] = user_match.group(1)
                    register_secrets(credentials["username"])
                    logger.info("✓ Username extraído do texto")

            if not credentials["password"]:
                pw_match = re.search(r'Password:\s*([A-Za-z0-9_]+)', page_text)
                if pw_match:
                    credentials["password"] = pw_match.group(1)
                    register_secrets(credentials["password"])
                    logger.info("✓ Password extraída do texto")

            # 4. Extrair Server URL / DNS — primeiro tentar "Server URL:", senão extrair do M3U host
            server_match = re.search(r'Server\s*URL:\s*(https?://[^\s\nA-Z]+)', page_text)
            if server_match:
                credentials["dns"] = server_match.group(1)
                logger.info("✓ DNS/Server extraído")
            elif credentials["m3u"]:
                dns_match = re.search(r'(https?://[^/\s]+)', credentials["m3u"])
                if dns_match:
                    credentials["dns"] = dns_match.group(1)
                    logger.info("✓ DNS extraído do M3U")

            # 5. URL da confirmação
            credentials["url"] = f"{PORTAL_URL}/cart.php?a=complete"

            # Verificar se obtivemos pelo menos username e password
            if credentials["username"] and credentials["password"] and credentials["m3u"]:
                logger.info("✓ Todas as credenciais extraídas com sucesso a 100%!")
            else:
                missing = []
                if not credentials["username"]: missing.append("Username")
                if not credentials["password"]: missing.append("Password")
                if not credentials["m3u"]: missing.append("M3U Playlist")
                if not credentials["dns"]: missing.append("DNS / Server")
                if not credentials["epg"]: missing.append("EPG")
                
                logger.warning(f"⚠ Extração incompleta. Campos em falta: {', '.join(missing)}")
                
                # O relatório web regista os campos em falta sem guardar HTML com segredos.
                diagnostic_event("extraction", "Extração incompleta", missing_fields=missing)
                if not has_active_run():
                    try:
                        debug_path = os.path.join(os.path.dirname(__file__), "debug_confirmation.html")
                        with open(debug_path, "w", encoding="utf-8") as f:
                            f.write(html)
                        logger.info(f"HTML de confirmação guardado em: {debug_path}")
                    except Exception:
                        pass
                
                raise RuntimeError(f"Processo não completou a 100%: faltam dados essenciais ({', '.join(missing)})")

        except Exception as e:
            logger.error("Erro ao extrair credenciais (%s): %s", type(e).__name__, sanitize_text(str(e)))
            raise

        return credentials

    def _log_failure_to_file(self, attempt: int, total_attempts: int, error_msg: str, proxy_url: str = None, traceback_str: str = ""):
        """Regista detalhes de qualquer falha / reinício do processo num ficheiro de log dedicado."""
        if has_active_run():
            return
        try:
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ERROR_LOG_FILE)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            proxy_display = proxy_url if proxy_url else "Nenhum (Ligação direta / IP local)"
            email_display = self.last_email_created if self.last_email_created else "N/A"
            step_display = self.current_step_name if self.current_step_name else "Início / Preparação"
            
            divider = "=" * 75
            entry = [
                divider,
                f"REGISTO DE FALHA - PROCESSO NÃO CONCLUÍDO A 100%",
                f"Data e Hora    : {timestamp}",
                f"Tentativa      : {attempt} de {total_attempts}",
                f"Passo / Etapa  : {step_display}",
                f"Proxy Utilizado: {proxy_display}",
                f"Email Utilizado: {email_display}",
                f"Motivo do Erro : {error_msg}",
            ]
            if traceback_str and traceback_str.strip():
                entry.append(f"Traceback Técnico:\n{traceback_str.strip()}")
            entry.append(divider + "\n\n")
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(sanitize_text("\n".join(entry)))
            
            logger.info(f"📁 Detalhes da falha guardados em: {ERROR_LOG_FILE}")
        except Exception as ex:
            logger.error(f"Não foi possível gravar no ficheiro de log de falhas: {ex}")

    def run_automation(self) -> Optional[Dict[str, str]]:
        """Executa a automação completa com retries."""
        import traceback
        pm = self._get_proxy_manager()
        max_retries = MAX_PROXY_RETRIES if pm.has_proxies() else 5

        for attempt in range(max_retries):
            diagnostic_event("attempt", "Início da tentativa", attempt=attempt + 1,
                             total_attempts=max_retries)
            if attempt > 0:
                logger.info(f"\n{'=' * 60}")
                logger.info(f"RECOMEÇANDO O LOOP: TENTATIVA {attempt + 1}/{max_retries}")
                logger.info(f"{'=' * 60}")
                self._ui_step(0, f"Tentativa {attempt}/{max_retries} falhou. A procurar novo proxy ({attempt + 1}/{max_retries})...")

            proxy_url = None
            if pm.has_proxies():
                if attempt == 0:
                    self._ui_step(0, "A procurar proxy funcional...")
                proxy_url = self._find_working_proxy(pm, max_tests=500)

            diagnostic_event("connection", "Ligação selecionada", proxy=proxy_url,
                             mode="proxy" if proxy_url else "direct")
            try:
                result = self._run_single_attempt(proxy_url)
                if result is not None:
                    return result
            except Exception as e:
                tb = traceback.format_exc()
                self.last_error = str(e)
                logger.exception("[ERRO TENTATIVA %s] (%s): %s", attempt + 1, type(e).__name__, sanitize_text(str(e)))
                self._log_failure_to_file(
                    attempt=attempt + 1,
                    total_attempts=max_retries,
                    error_msg=str(e),
                    proxy_url=proxy_url,
                    traceback_str=tb
                )
                if proxy_url:
                    pm.mark_failed(proxy_url)
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ Processo não concluído a 100%. A recomeçar o loop (Tentativa {attempt + 2}/{max_retries})...")
                    if not has_active_run():
                        logger.warning(f"ℹ️ Consulta '{ERROR_LOG_FILE}' para ver o motivo detalhado da falha.")

        logger.error("Todas as %s tentativas falharam.", max_retries)
        if not has_active_run():
            logger.error("Consulta '%s' para mais detalhes.", ERROR_LOG_FILE)
        return None
