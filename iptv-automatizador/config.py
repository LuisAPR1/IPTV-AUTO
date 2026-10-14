"""Configurações do automatizador IPTV."""

import os
from pathlib import Path

# Carregar variáveis de ambiente do ficheiro .env se existir
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv não instalado, ignorar

# URLs do site
BASE_URL = "https://www.fastcccam.com/iptv-free-trial-service"
PORTAL_URL = "https://serviceportal.store"

# Configurações de email temporário

# Opção 1: Gmail pessoal (RECOMENDADO - mais fiável)
# Cria emails como: tua_conta+abc123@gmail.com
# Requer App Password (não a password normal!)
# Como criar: https://myaccount.google.com/apppasswords
PERSONAL_GMAIL = os.getenv("PERSONAL_GMAIL", "").strip().strip('"\'')  # ex: "tua_conta@gmail.com"
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip().strip('"\'')  # App Password de 16 caracteres

# Usar Gmail pessoal (única opção - mais fiável)
USE_PERSONAL_GMAIL = bool(PERSONAL_GMAIL and GMAIL_APP_PASSWORD)

# Timeouts
EMAIL_TIMEOUT = 120  # segundos para aguardar email
EMAIL_POLL_INTERVAL = 5  # segundos entre verificações

# Proxy (opcional - para mudar IP)
# Formato: "http://user:pass@host:port" ou "http://host:port"
PROXY_URL = os.getenv("PROXY_URL", "")

# === ProxyScrape (GRATUITO - centenas de proxies frescas!) ===
# API pública sem necessidade de API key
# Site: https://proxyscrape.com/free-proxy-list
# API: https://api.proxyscrape.com/v4/free-proxy-list/get
USE_PROXYSCRAPE = os.getenv("USE_PROXYSCRAPE", "true").lower() == "true"

# Tipos de proxy: 'http', 'socks4', 'socks5', ou 'all'
# SOCKS5 recomendado! Funciona como VPN (sem headers de proxy detectáveis)
PROXYSCRAPE_TYPES = os.getenv("PROXYSCRAPE_TYPES", "socks5")

# Timeout máximo das proxies em ms (filtro de velocidade)
# Valor mais baixo = proxies mais rápidas, mas menos disponíveis
PROXYSCRAPE_TIMEOUT = int(os.getenv("PROXYSCRAPE_TIMEOUT", "200"))

# Filtro por país (código ISO: 'US', 'DE', 'PT', etc). Vazio = todos
PROXYSCRAPE_COUNTRY = os.getenv("PROXYSCRAPE_COUNTRY", "")

# Máximo de proxies a buscar de cada vez
PROXYSCRAPE_MAX = int(os.getenv("PROXYSCRAPE_MAX", "500"))

# Tor Browser (alternativo - usa exit nodes conhecidos, pode ser bloqueado)
USE_TOR = os.getenv("USE_TOR", "false").lower() == "true"
TOR_PROXY = "socks5://127.0.0.1:9050"

# Lista de proxies manual (ficheiro free-proxy-list.txt)
USE_PROXY_LIST = os.getenv("USE_PROXY_LIST", "false").lower() == "true"
PROXY_LIST_FILE = "free-proxy-list.txt"

# Retry com proxies diferentes se IP bloqueado
MAX_PROXY_RETRIES = int(os.getenv("MAX_PROXY_RETRIES", "15"))

# Configurações do scraper
HEADLESS = False  # False = mostra o browser (mais fiável contra deteção)
DEFAULT_TIMEOUT = 30000  # ms
NAVIGATION_TIMEOUT = 60000  # ms

# Pasta de output
OUTPUT_DIR = "trash"
OUTPUT_FILE = "output.html"
ERROR_LOG_FILE = os.getenv("ERROR_LOG_FILE", "erros_automacao.log")

# Diagnóstico web: só dados sanitizados, últimas 10 execuções.
DIAGNOSTICS_TOKEN = os.getenv("DIAGNOSTICS_TOKEN", "").strip()
DIAGNOSTICS_DB_PATH = os.getenv(
    "DIAGNOSTICS_DB_PATH", str(Path(__file__).parent / "data" / "diagnostics.sqlite3")
)

# User agent realista
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
