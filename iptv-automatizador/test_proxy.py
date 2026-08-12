#!/usr/bin/env python3
"""Testa proxies e verifica se o site é acessível."""

import sys
import io
import logging
import requests
from proxy_manager import SimpleProxyManager, test_proxy
from config import (
    USE_PROXYSCRAPE, PROXYSCRAPE_TYPES, PROXYSCRAPE_TIMEOUT,
    PROXYSCRAPE_COUNTRY, PROXYSCRAPE_MAX, USE_PROXY_LIST,
    PROXY_LIST_FILE, PROXY_URL
)

# Forcar UTF-8 no Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_real_ip():
    """Obtém o IP real (sem proxy)."""
    try:
        resp = requests.get("https://httpbin.org/ip", timeout=10)
        return resp.json().get("origin", "unknown")
    except:
        return "erro"


def test_site_access(proxy_url: str = None):
    """Testa se o site myfiestatrial.com responde via proxy."""
    try:
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        resp = requests.get(
            "https://myfiestatrial.com",
            proxies=proxies,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
        )
        return resp.status_code, len(resp.text)
    except Exception as e:
        return None, str(e)


def main():
    print("=" * 60)
    print("  TESTE DE PROXIES - IPTV Automatizador")
    print("  Fonte: ProxyScrape (proxies frescas online!)")
    print("=" * 60)
    
    # 1. IP real
    real_ip = get_real_ip()
    print(f"\n[IP] O teu IP real: {real_ip}")
    
    # 2. Testar acesso direto ao site
    print(f"\n[WEB] A testar acesso DIRETO ao site...")
    status, size = test_site_access()
    if status:
        print(f"   Status: {status} | Tamanho: {size} bytes")
        if status == 200:
            print("   [OK] Site acessivel sem proxy!")
        elif status == 403:
            print("   [X] IP BLOQUEADO (403) - precisa de proxy")
        else:
            print(f"   [?] Status inesperado: {status}")
    else:
        print(f"   [X] Erro: {size}")
    
    # 3. Carregar proxies (ProxyScrape - frescas!)
    print(f"\n[PROXY] A buscar proxies frescas do ProxyScrape...")
    manager = SimpleProxyManager(
        proxy_file=PROXY_LIST_FILE if USE_PROXY_LIST else "",
        use_proxyscrape=USE_PROXYSCRAPE,
        proxyscrape_types=PROXYSCRAPE_TYPES,
        proxyscrape_timeout=PROXYSCRAPE_TIMEOUT,
        proxyscrape_country=PROXYSCRAPE_COUNTRY,
        proxyscrape_max=PROXYSCRAPE_MAX,
        direct_proxy=PROXY_URL
    )
    
    if not manager.has_proxies():
        print("\n[X] Nenhum proxy encontrado!")
        print("\nVerifica a tua ligacao a internet.")
        print("A API do ProxyScrape deve ser acessivel em:")
        print("  https://api.proxyscrape.com/v4/free-proxy-list/get")
        return 1
    
    print(f"\n[OK] {len(manager.proxies)} proxies disponiveis")
    
    # 4. Testar cada proxy
    print(f"\n[TEST] A testar proxies...\n")
    working = 0
    site_accessible = 0
    
    for i, proxy in enumerate(manager.proxies):
        masked = manager._mask_proxy(proxy)
        print(f"  [{i+1}/{len(manager.proxies)}] {masked}")
        
        # Teste 1: proxy funciona?
        ip = test_proxy(proxy, timeout=10)
        if not ip:
            print(f"         [X] Proxy nao responde")
            continue
        
        working += 1
        print(f"         [OK] IP via proxy: {ip}")
        
        if ip == real_ip:
            print(f"         [!] MESMO IP que o real - proxy nao funciona corretamente")
            continue
        
        # Teste 2: site acessível via proxy?
        status, size = test_site_access(proxy)
        if status == 200:
            site_accessible += 1
            print(f"         [OK] Site acessivel! (status {status}, {size} bytes)")
        elif status == 403:
            print(f"         [X] Site bloqueou este IP (403)")
        elif status:
            print(f"         [?] Status: {status}")
        else:
            print(f"         [X] Erro: {size}")
    
    # Sumário
    print(f"\n{'=' * 60}")
    print(f"  RESULTADO:")
    print(f"  Total proxies: {len(manager.proxies)}")
    print(f"  Funcionam:     {working}")
    print(f"  Site OK:       {site_accessible}")
    print(f"{'=' * 60}")
    
    if site_accessible > 0:
        print(f"\n[OK] {site_accessible} proxies funcionam com o site!")
        print("   Podes correr: python main.py")
    elif working > 0:
        print(f"\n[!] Proxies funcionam mas o site bloqueia esses IPs.")
        print("  Tenta correr de novo (proxies sao diferentes de cada vez).")
    else:
        print(f"\n[X] Nenhum proxy funciona. Tenta de novo mais tarde.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
