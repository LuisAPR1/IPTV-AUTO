"""Automação do site Fast CCCam / ServicePortal IPTV Trial usando Playwright e HTTP Fallback."""

import re
import logging
import random
import time
import requests
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Browser

from window_manager import minimize_chromium_windows
from config import (
    BASE_URL, PORTAL_URL, HEADLESS, DEFAULT_TIMEOUT, NAVIGATION_TIMEOUT, USER_AGENT, 
    PROXY_URL, USE_TOR, TOR_PROXY, USE_PROXY_LIST, PROXY_LIST_FILE,
    USE_PROXYSCRAPE, PROXYSCRAPE_TYPES, PROXYSCRAPE_TIMEOUT,
    PROXYSCRAPE_COUNTRY, PROXYSCRAPE_MAX, MAX_PROXY_RETRIES
)
from proxy_manager import SimpleProxyManager
from email_service import TempMailService

logger = logging.getLogger(__name__)


class IPTVScraper:
    """Automação do site Fast CCCam / ServicePortal IPTV Trial."""

    def __init__(self, email_service: TempMailService, ui=None):
        self.email_service = email_service
        self.ui = ui
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.proxy_manager: Optional[SimpleProxyManager] = None
        self._current_proxy: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _ui_step(self, step_index: int, message: str = ""):
        """Atualiza UI se disponível."""
        if self.ui:
            self.ui.update(step_index, message)
    
    def _get_proxy_manager(self) -> SimpleProxyManager:
        """Inicializa o proxy manager."""
        if self.proxy_manager is None:
            self.proxy_manager = SimpleProxyManager(
                proxy_file=PROXY_LIST_FILE if USE_PROXY_LIST else "",
                use_proxyscrape=USE_PROXYSCRAPE,
                proxyscrape_types=PROXYSCRAPE_TYPES,
                proxyscrape_timeout=PROXYSCRAPE_TIMEOUT,
                proxyscrape_country=PROXYSCRAPE_COUNTRY,
                proxyscrape_max=PROXYSCRAPE_MAX,
                direct_proxy=PROXY_URL
            )
        return self.proxy_manager
    
    def _pre_test_proxy(self, proxy_url: str, timeout: int = 12) -> Optional[float]:
        """Testa se um proxy consegue aceder ao site via HTTPS."""
        try:
            masked = proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url
            start = time.time()
            resp = requests.get(
                BASE_URL,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True
            )
            latency = time.time() - start
            if resp.status_code in (200, 301, 302):
                logger.info(f"✅ {masked} → {latency:.1f}s (status {resp.status_code})")
                return latency
            else:
                return None
        except Exception:
            return None

    def _find_working_proxy(self, pm: SimpleProxyManager, max_tests: int = 500) -> Optional[str]:
        """Encontra o proxy funcional mais rápido."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        MAX_LATENCY = 10.0
        BATCH_SIZE = 5
        tested = 0
        
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
                futures = {executor.submit(self._pre_test_proxy, p, 12): p for p in batch}
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
                return best
            for p in batch:
                pm.mark_failed(p)
        return None

    def _human_delay(self, min_seconds: float = 0.3, max_seconds: float = 1.0):
        """Adiciona delay aleatório para simular comportamento humano."""
        time.sleep(random.uniform(min_seconds, max_seconds))

    def _run_single_attempt(self, proxy_url: str = None) -> Optional[Dict[str, str]]:
        """Executa uma tentativa completa de obtenção de trial."""
        try:
            # Configure proxy on HTTP session if used
            if proxy_url:
                self.session.proxies = {"http": proxy_url, "https": proxy_url}

            # 1. Email Temporário
            self._ui_step(1, "Criando email temporário...")
            logger.info("=== PASSO 1: Criar email temporário ===")
            email = self.email_service.create_inbox()
            logger.info(f"Email criado: {email}")

            # 2. Aceder ao portal de trial
            self._ui_step(2, "Acedendo ao portal de trial Fast CCCam...")
            logger.info("=== PASSO 2: Aceder ao portal de trial ===")
            trial_portal_url = f"{PORTAL_URL}/store/single-users/trial-admin"
            r1 = self.session.get(trial_portal_url)
            
            if r1.status_code != 200 and "confproduct" not in r1.url:
                logger.warning(f"Resposta inesperada no portal: {r1.status_code}")
                return None
            
            soup1 = BeautifulSoup(r1.text, "html.parser")
            token1_el = soup1.find("input", {"name": "token"})
            token1 = token1_el.get("value") if token1_el else ""

            # 3. Configurar Produto de 48h
            self._ui_step(3, "Configurando produto 48h trial...")
            logger.info("=== PASSO 3: Configurar produto ===")
            conf_payload = {
                "token": token1,
                "configure": "true",
                "i": "0",
                "customfield[126]": ""  # Bouquets (vazio = todos)
            }
            r2 = self.session.post(f"{PORTAL_URL}/cart.php?a=confproduct&i=0", data=conf_payload)
            
            # 4. Aceder à página de Checkout
            self._ui_step(4, "Preparando página de checkout...")
            logger.info("=== PASSO 4: Aceder ao checkout ===")
            r3 = self.session.get(f"{PORTAL_URL}/cart.php?a=checkout")
            soup3 = BeautifulSoup(r3.text, "html.parser")
            
            chk_form = soup3.find("form", {"id": "frmCheckout"})
            token3_el = chk_form.find("input", {"name": "token"}) if chk_form else soup3.find("input", {"name": "token"})
            token3 = token3_el.get("value") if token3_el else token1

            # 5. Solicitar Código de Verificação por Email
            self._ui_step(5, "Solicitando código de verificação por email...")
            logger.info("=== PASSO 5: Solicitar código de verificação ===")
            ajax_url = f"{PORTAL_URL}/modules/addons/ValidEmail/ajaxhandler.php"
            r_send = self.session.post(ajax_url, data={"action": "sendvalidcode", "email": email})
            logger.info(f"Resposta envio código: {r_send.text}")

            if "success" not in r_send.text:
                logger.error("Falha ao solicitar código de verificação")
                return None

            # 6. Aguardar Código por IMAP
            self._ui_step(6, "Aguardando código no email...")
            logger.info("=== PASSO 6: Aguardar código por email ===")
            code = self.email_service.get_verification_code()
            if not code:
                logger.error("Código de verificação não recebido a tempo")
                return None

            logger.info(f"✓ Código obtido: {code}")

            # 7. Validar Código no Servidor
            self._ui_step(6, "Validando código no servidor...")
            logger.info("=== PASSO 7: Validar código no servidor ===")
            r_val = self.session.post(ajax_url, data={"action": "validatecode", "email": email, "validatecode": code})
            logger.info(f"Resposta validação código: '{r_val.text.strip()}'")

            if r_val.text.strip() != "1":
                logger.error("Código inválido ou rejeitado pelo servidor")
                return None

            logger.info("✓ Código verificado com sucesso!")

            # 8. Submeter Checkout Completo
            self._ui_step(7, "Finalizando encomenda do trial...")
            logger.info("=== PASSO 8: Finalizar checkout ===")
            suffix = self.email_service.personal_service.generated_suffix or "user123"
            fn = f"User{suffix[:4]}"
            ln = f"Test{suffix[4:]}"
            pw = f"Pass#{suffix}!"

            checkout_payload = {
                "token": token3,
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
                "paymentmethod": "banktransfer",
                "accepttos": "on"
            }

            r_checkout = self.session.post(f"{PORTAL_URL}/cart.php?a=checkout", data=checkout_payload)
            logger.info(f"Checkout submetido. URL: {r_checkout.url}")

            # 9. Extrair Credenciais dos Serviços Activos
            self._ui_step(7, "Extraindo credenciais do serviço IPTV...")
            logger.info("=== PASSO 9: Extrair credenciais ===")
            credentials = self.extract_credentials(email, pw)
            credentials['email_used'] = email

            self._ui_step(7, "Concluído com sucesso!")
            return credentials

        except Exception as e:
            logger.error(f"Erro na automação: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

    def extract_credentials(self, email: str, account_pw: str) -> Dict[str, str]:
        """Extrai credenciais IPTV da área de cliente ou serviço ativo.
        
        Returns:
            Dict com username, password, dns, epg, m3u, url
        """
        credentials = {
            "username": "",
            "password": "",
            "dns": "",
            "epg": "",
            "m3u": "",
            "url": f"{PORTAL_URL}/clientarea.php?action=services"
        }

        try:
            r_services = self.session.get(f"{PORTAL_URL}/clientarea.php?action=services")
            soup_services = BeautifulSoup(r_services.text, "html.parser")
            
            # Procurar link dos detalhes do produto
            detail_url = None
            for row in soup_services.find_all("tr"):
                row_text = row.get_text(strip=True)
                if any(w in row_text for w in ["IPTV", "Trial", "Active", "Pending"]):
                    for a in row.find_all("a", href=True):
                        if "productdetails" in a["href"]:
                            detail_url = f"{PORTAL_URL}/" + a["href"].lstrip('/')
                            break

            if not detail_url:
                # Tentar encontrar qualquer link de productdetails
                for a in soup_services.find_all("a", href=True):
                    if "productdetails" in a["href"]:
                        detail_url = f"{PORTAL_URL}/" + a["href"].lstrip('/')
                        break

            if detail_url:
                logger.info(f"Acedendo aos detalhes do produto: {detail_url}")
                r_detail = self.session.get(detail_url)
                soup_detail = BeautifulSoup(r_detail.text, "html.parser")
                credentials['url'] = detail_url

                # Mapear inputs e labels
                for outer in soup_detail.find_all(["div", "tr", "p"]):
                    text = outer.get_text(separator=" ", strip=True).lower()
                    inp = outer.find(["input", "textarea"])
                    val = inp.get("value") if inp else ""

                    if "username" in text and not credentials["username"]:
                        credentials["username"] = val or self._extract_value_after(text, "username")
                    if ("password" in text or "pass" in text) and not credentials["password"]:
                        credentials["password"] = val or self._extract_value_after(text, "password")
                    if ("host" in text or "dns" in text or "server" in text) and not credentials["dns"]:
                        credentials["dns"] = val or self._extract_value_after(text, "dns")
                    if "epg" in text and not credentials["epg"]:
                        credentials["epg"] = val or self._extract_value_after(text, "epg")
                    if ("m3u" in text or "playlist" in text) and not credentials["m3u"]:
                        credentials["m3u"] = val or self._extract_value_after(text, "m3u")

            # Fallbacks com a conta criada se não encontrou nos campos
            if not credentials["username"]:
                credentials["username"] = email.split('@')[0]
            if not credentials["password"]:
                credentials["password"] = account_pw
            if not credentials["dns"]:
                credentials["dns"] = "http://line.fastip.tv:8080"
            if not credentials["m3u"]:
                credentials["m3u"] = f"{credentials['dns']}/get.php?username={credentials['username']}&password={credentials['password']}&type=m3u_plus&output=ts"
            if not credentials["epg"]:
                credentials["epg"] = f"{credentials['dns']}/xmltv.php?username={credentials['username']}&password={credentials['password']}"

            logger.info("Credenciais extraídas com sucesso!")

        except Exception as e:
            logger.error(f"Erro ao extrair credenciais: {e}")

        return credentials

    def _extract_value_after(self, text: str, keyword: str) -> str:
        """Helper para extrair valor após uma palavra-chave."""
        m = re.search(f"{keyword}[:\\s]+([^\\s]+)", text, re.IGNORECASE)
        return m.group(1) if m else ""

    def run_automation(self) -> Optional[Dict[str, str]]:
        """Executa a automação completa com retries."""
        pm = self._get_proxy_manager()
        max_retries = MAX_PROXY_RETRIES if pm.has_proxies() else 1

        for attempt in range(max_retries):
            if attempt > 0:
                logger.info(f"\n{'=' * 60}")
                logger.info(f"TENTATIVA {attempt + 1}/{max_retries}")
                logger.info(f"{'=' * 60}")

            proxy_url = None
            if pm.has_proxies():
                self._ui_step(0, "A procurar proxy funcional...")
                proxy_url = self._find_working_proxy(pm, max_tests=500)

            result = self._run_single_attempt(proxy_url)

            if result is not None:
                return result

            if proxy_url and pm.has_proxies():
                pm.mark_failed(proxy_url)

        logger.error("Todas as tentativas falharam")
        return None
