"""Gestor de proxies com suporte a ProxyScrape (proxies grátis online) e lista manual."""

import random
import os
import logging
import requests
import time
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class ProxyScrapeProvider:
    """Obtém proxies gratuitos via ProxyScrape API (proxies frescas, sempre a rodar).
    
    API pública: https://api.proxyscrape.com/v4/free-proxy-list/get
    Não precisa de API key - retorna centenas/milhares de proxies grátis.
    """
    
    API_URL = "https://api.proxyscrape.com/v4/free-proxy-list/get"
    
    def __init__(self, proxy_types: str = "http", timeout_ms: int = 5000, country: str = ""):
        """
        Args:
            proxy_types: Tipos de proxy a buscar ('http', 'socks4', 'socks5', ou 'all')
            timeout_ms: Timeout máximo das proxies (em ms) - filtra por velocidade
            country: Filtrar por país (código ISO, ex: 'US', 'DE', 'PT'). Vazio = todos.
        """
        self.proxy_types = proxy_types
        self.timeout_ms = timeout_ms
        self.country = country
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    
    def fetch_proxies(self, max_proxies: int = 100) -> List[str]:
        """Busca lista de proxies frescas da API ProxyScrape.
        
        Args:
            max_proxies: Número máximo de proxies a retornar
            
        Returns:
            Lista de proxies no formato protocol://ip:port
        """
        try:
            logger.info("🔄 A obter proxies frescas do ProxyScrape...")
            
            params = {
                "request": "display_proxies",
                "proxy_format": "protocolipport",
                "format": "text",
            }
            
            # Filtro por tipo de protocolo
            if self.proxy_types and self.proxy_types != "all":
                params["protocol"] = self.proxy_types
            
            # Filtro por timeout (velocidade)
            if self.timeout_ms:
                params["timeout"] = self.timeout_ms
            
            # Filtro por país
            if self.country:
                params["country"] = self.country
            
            resp = self.session.get(
                self.API_URL,
                params=params,
                timeout=20
            )
            
            if resp.status_code != 200:
                logger.error(f"❌ ProxyScrape API erro {resp.status_code}: {resp.text[:200]}")
                return []
            
            # Parse da resposta (uma proxy por linha)
            raw_text = resp.text.strip()
            if not raw_text:
                logger.warning("⚠️ ProxyScrape retornou lista vazia")
                return []
            
            all_proxies = []
            for line in raw_text.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    # Garantir que tem protocolo
                    if not line.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                        line = f"http://{line}"
                    all_proxies.append(line)
            
            # Baralhar e limitar
            random.shuffle(all_proxies)
            proxy_list = all_proxies[:max_proxies]
            
            logger.info(f"✅ {len(proxy_list)} proxies obtidas do ProxyScrape (de {len(all_proxies)} disponíveis)")
            return proxy_list
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro ao contactar ProxyScrape API: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Erro inesperado ProxyScrape: {e}")
            return []


class SimpleProxyManager:
    """Gestor de proxies com múltiplas fontes.
    
    Prioridade:
    1. ProxyScrape API (proxies grátis online - sempre frescas!)
    2. Ficheiro manual (free-proxy-list.txt)
    3. Proxy direto (.env)
    
    Vantagens vs Webshare:
    - Sem API key necessária
    - Centenas de proxies disponíveis (vs 10 do Webshare)
    - Proxies sempre novas a cada chamada (sem bans!)
    - Pode refrescar automaticamente durante a execução
    """
    
    def __init__(self, proxy_file: str = "free-proxy-list.txt", 
                 use_proxyscrape: bool = True,
                 proxyscrape_types: str = "http",
                 proxyscrape_timeout: int = 5000,
                 proxyscrape_country: str = "",
                 proxyscrape_max: int = 100,
                 direct_proxy: str = ""):
        self.proxy_file = proxy_file
        self.use_proxyscrape = use_proxyscrape
        self.proxyscrape_types = proxyscrape_types
        self.proxyscrape_timeout = proxyscrape_timeout
        self.proxyscrape_country = proxyscrape_country
        self.proxyscrape_max = proxyscrape_max
        self.direct_proxy = direct_proxy
        self.proxies: List[str] = []
        self.used_proxies: List[str] = []  # Proxies já usados nesta sessão
        self.failed_proxies: List[str] = []  # Proxies que falharam
        self.current_index = 0
        self._proxyscrape_provider: Optional[ProxyScrapeProvider] = None
        self._load_all_proxies()
    
    def _load_all_proxies(self) -> None:
        """Carrega proxies de todas as fontes disponíveis."""
        
        # Fonte 1: ProxyScrape API (proxies frescas online!)
        if self.use_proxyscrape:
            self._proxyscrape_provider = ProxyScrapeProvider(
                proxy_types=self.proxyscrape_types,
                timeout_ms=self.proxyscrape_timeout,
                country=self.proxyscrape_country
            )
            ps_proxies = self._proxyscrape_provider.fetch_proxies(max_proxies=self.proxyscrape_max)
            if ps_proxies:
                self.proxies.extend(ps_proxies)
                logger.info(f"✅ {len(ps_proxies)} proxies do ProxyScrape carregadas")
        
        # Fonte 2: Ficheiro manual
        file_proxies = self._load_from_file()
        if file_proxies:
            self.proxies.extend(file_proxies)
            logger.info(f"✅ {len(file_proxies)} proxies do ficheiro carregadas")
        
        # Fonte 3: Proxy direto
        if self.direct_proxy:
            self.proxies.append(self.direct_proxy)
            logger.info(f"✅ Proxy direto adicionado: {self._mask_proxy(self.direct_proxy)}")
        
        # Remover duplicados mantendo ordem
        seen = set()
        unique = []
        for p in self.proxies:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        self.proxies = unique
        
        # Baralhar para não usar sempre a mesma ordem
        random.shuffle(self.proxies)
        
        if self.proxies:
            logger.info(f"✅ Total: {len(self.proxies)} proxies disponíveis")
        else:
            logger.warning("⚠️ Nenhum proxy disponível!")
    
    def refresh_proxies(self) -> int:
        """Refresca a lista de proxies buscando novas do ProxyScrape.
        
        Útil quando todas as proxies atuais foram usadas/falharam.
        
        Returns:
            Número de novas proxies adicionadas
        """
        if not self._proxyscrape_provider:
            logger.warning("ProxyScrape não está configurado, não é possível refrescar")
            return 0
        
        logger.info("🔄 A refrescar lista de proxies do ProxyScrape...")
        new_proxies = self._proxyscrape_provider.fetch_proxies(max_proxies=self.proxyscrape_max)
        
        # Filtrar proxies que já falharam antes
        fresh_proxies = [p for p in new_proxies if p not in self.failed_proxies]
        
        if fresh_proxies:
            # Adicionar apenas as novas (que não estão já na lista)
            existing = set(self.proxies)
            added = 0
            for p in fresh_proxies:
                if p not in existing:
                    self.proxies.append(p)
                    added += 1
            
            logger.info(f"✅ {added} proxies novas adicionadas ({len(self.proxies)} total)")
            return added
        else:
            logger.warning("⚠️ Nenhuma proxy nova encontrada")
            return 0
    
    def _load_from_file(self) -> List[str]:
        """Carrega proxies do ficheiro."""
        if not self.proxy_file or not os.path.exists(self.proxy_file):
            return []
        
        proxies = []
        try:
            with open(self.proxy_file, 'r') as f:
                lines = f.readlines()
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    if not line.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                        line = f"http://{line}"
                    proxies.append(line)
            
        except Exception as e:
            logger.error(f"Erro ao carregar {self.proxy_file}: {e}")
        
        return proxies
    
    def _mask_proxy(self, proxy: str) -> str:
        """Mascara credenciais do proxy para logs."""
        if '@' in proxy:
            # http://user:pass@host:port -> http://***@host:port
            parts = proxy.split('@')
            return f"***@{parts[-1]}"
        return proxy
    
    def get_random_proxy(self) -> Optional[str]:
        """Retorna proxy aleatório da lista."""
        if not self.proxies:
            # Tentar refrescar antes de desistir
            if self.use_proxyscrape:
                self.refresh_proxies()
            if not self.proxies:
                return None
        proxy = random.choice(self.proxies)
        logger.info(f"Proxy selecionado: {self._mask_proxy(proxy)}")
        return proxy
    
    def get_next_proxy(self) -> Optional[str]:
        """Retorna próximo proxy não usado. Para retry sequencial."""
        available = [p for p in self.proxies if p not in self.used_proxies]
        
        if not available:
            # Tentar refrescar do ProxyScrape antes de resetar
            if self.use_proxyscrape:
                added = self.refresh_proxies()
                if added > 0:
                    available = [p for p in self.proxies if p not in self.used_proxies]
            
            if not available:
                # Se ainda não há, resetar e tentar de novo
                logger.warning("Todos os proxies já foram tentados, a reiniciar lista...")
                self.used_proxies.clear()
                available = self.proxies
        
        if not available:
            return None
        
        proxy = available[0]
        self.used_proxies.append(proxy)
        logger.info(f"Próximo proxy: {self._mask_proxy(proxy)} ({len(available)-1} restantes)")
        return proxy
    
    def mark_failed(self, proxy: str) -> None:
        """Marca proxy como falhado (remove da lista ativa)."""
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            self.failed_proxies.append(proxy)
            logger.info(f"Proxy removido (falhou): {self._mask_proxy(proxy)} ({len(self.proxies)} restantes)")
    
    def has_proxies(self) -> bool:
        """Verifica se há proxies disponíveis."""
        return len(self.proxies) > 0
    
    def remaining_count(self) -> int:
        """Quantos proxies ainda não foram tentados."""
        return len([p for p in self.proxies if p not in self.used_proxies])


def test_proxy(proxy_url: str, timeout: int = 10) -> Optional[str]:
    """Testa se um proxy funciona.
    
    Args:
        proxy_url: URL do proxy (http://host:port ou http://user:pass@host:port)
        timeout: Timeout em segundos
        
    Returns:
        IP público se funcionar, None se falhar
    """
    try:
        resp = requests.get(
            "https://httpbin.org/ip",
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=timeout
        )
        if resp.status_code == 200:
            ip = resp.json().get("origin", "unknown")
            return ip
        return None
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    import io
    
    # Forcar UTF-8 no Windows
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    from config import (
        USE_PROXYSCRAPE, PROXYSCRAPE_TYPES, PROXYSCRAPE_TIMEOUT,
        PROXYSCRAPE_COUNTRY, PROXYSCRAPE_MAX, USE_PROXY_LIST, 
        PROXY_LIST_FILE, PROXY_URL
    )
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    manager = SimpleProxyManager(
        proxy_file=PROXY_LIST_FILE if USE_PROXY_LIST else "",
        use_proxyscrape=USE_PROXYSCRAPE,
        proxyscrape_types=PROXYSCRAPE_TYPES,
        proxyscrape_timeout=PROXYSCRAPE_TIMEOUT,
        proxyscrape_country=PROXYSCRAPE_COUNTRY,
        proxyscrape_max=PROXYSCRAPE_MAX,
        direct_proxy=PROXY_URL
    )
    
    if manager.has_proxies():
        print(f"\n[OK] {len(manager.proxies)} proxies disponiveis\n")
        
        for i, proxy in enumerate(manager.proxies[:5]):
            print(f"  [{i+1}] {manager._mask_proxy(proxy)}")
            ip = test_proxy(proxy)
            if ip:
                print(f"      [OK] Funciona! IP: {ip}")
            else:
                print(f"      [X] Nao funciona")
        
        if len(manager.proxies) > 5:
            print(f"  ... e mais {len(manager.proxies) - 5}")
    else:
        print("[X] Nenhum proxy encontrado")
        print("\nVerifica a tua ligacao a internet.")
        print("A API do ProxyScrape deve ser acessivel em:")
        print("  https://api.proxyscrape.com/v4/free-proxy-list/get")
