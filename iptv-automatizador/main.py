#!/usr/bin/env python3
"""
Automatizador IPTV Fiesta Trial

Script que automatiza o processo de obtenção de trials IPTV de 48h
do site myfiestatrial.com.

Fluxo:
1. Gera email temporário
2. Preenche formulário no site
3. Aguarda código de verificação por email
4. Introduz código e acede à página final
5. Extrai credenciais e mostra no terminal
"""

import os
import sys
import io
import argparse
import logging
from typing import Optional

from config import PERSONAL_GMAIL, GMAIL_APP_PASSWORD
from email_service import TempMailService
from scraper import IPTVScraper
from ui import ProgressUI
from window_manager import (
    prepare_terminal_focus,
    restore_terminal_normal,
    ensure_terminal_visible,
    minimize_chromium_windows,
)


# Cores ANSI
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _setup_stdout():
    """Forca UTF-8 e ativa cores ANSI no Windows (apenas uma vez)."""
    if sys.platform == 'win32' and not getattr(sys.stdout, '_iptv_setup', False):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stdout._iptv_setup = True
        os.system('')


def setup_logging(verbose: bool = False):
    """Configura logging. Em modo normal, logs vão só para ficheiro."""
    level = logging.DEBUG if verbose else logging.INFO
    handlers = []

    if verbose:
        handlers.append(logging.StreamHandler(sys.stdout))
    handlers.append(logging.FileHandler('iptv_automatizador.log', encoding='utf-8'))

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S',
        handlers=handlers,
        force=True,
    )


def print_credentials(credentials: dict):
    """Mostra as credenciais no terminal com destaque."""
    # Campos a mostrar (sem email_used)
    fields = [
        ("Username", credentials.get('username', '')),
        ("Password", credentials.get('password', '')),
        ("DNS / Domain", credentials.get('dns', '')),
        ("EPG (TV Guide)", credentials.get('epg', '')),
        ("M3U Playlist", credentials.get('m3u', '')),
    ]
    
    # Filtrar campos vazios
    fields = [(l, v) for l, v in fields if v]
    
    if not fields:
        print("\n  [!] Nenhuma credencial extraida.\n")
        return
    
    # Clear console
    os.system('cls' if os.name == 'nt' else 'clear')
    
    max_label = max(len(f[0]) for f in fields)
    width = max(60, max_label + max(len(str(f[1])) for f in fields) + 7)
    
    # Header com branding
    title_text = f"  Powered by {RED}{BOLD}LuisR{RESET}  --  {RED}github.com/luisapr1{RESET}  "
    # Largura sem os escape codes para padding correto
    title_visual_len = len(f"  Powered by LuisR  --  github.com/luisapr1  ")
    pad = width - title_visual_len
    left_pad = pad // 2
    right_pad = pad - left_pad
    
    print()
    print("+" + "=" * width + "+")
    print("|" + " " * left_pad + title_text + " " * right_pad + "|")
    print("+" + "=" * width + "+")
    
    for label, value in fields:
        line = f"  {label:<{max_label}}  :  {value}"
        print("|" + line.ljust(width) + "|")
    
    print("+" + "-" * width + "+")
    print("|" + "  Trial de 48h -- usa antes que expire!".ljust(width) + "|")
    print("+" + "=" * width + "+")
    print()


def main(headless: bool = False, verbose: bool = False) -> int:
    """Função principal.
    
    Args:
        headless: Executar browser em modo headless
        verbose: Modo verbose com mais logs
        
    Returns:
        int: Código de saída (0 = sucesso, 1 = erro)
    """
    _setup_stdout()
    setup_logging(verbose)

    # Preparar terminal: minimizar outras janelas e manter no topo
    prepare_terminal_focus(minimize_others=True, keep_topmost=True)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("IPTV Fiesta Automatizador - Iniciando...")
    logger.info("=" * 60)
    
    # Atualizar configuração de headless se necessário
    if headless:
        import config
        config.HEADLESS = True

    # UI minimalista
    ui = ProgressUI(total_steps=8)
    ui.update(0, "A preparar...")

    # Inicializar serviço de email (Gmail pessoal)
    logger.info("Usando Gmail pessoal com plus-addressing")
    email_service = TempMailService(
        personal_gmail=PERSONAL_GMAIL,
        app_password=GMAIL_APP_PASSWORD
    )
    scraper = IPTVScraper(email_service, ui=ui)

    try:
        # Executar automação
        credentials = scraper.run_automation()

        if not credentials:
            ui.error("Automação não concluída a 100%. Verifica erros_automacao.log e iptv_automatizador.log")
            logger.error("Automação falhou. Detalhes guardados em erros_automacao.log.")
            return 1

        # Mostrar credenciais no terminal
        print_credentials(credentials)

        return 0

    except KeyboardInterrupt:
        ui.error("Operação cancelada pelo utilizador.")
        logger.info("Operação cancelada pelo utilizador.")
        return 1
    except Exception as e:
        ui.error(str(e))
        logger.error(f"Erro inesperado: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return 1
    finally:
        # Limpar recursos
        try:
            email_service.cleanup()
        except:
            pass
        # Restaurar terminal ao estado normal
        restore_terminal_normal()


def parse_args():
    """Parse argumentos da linha de comandos."""
    parser = argparse.ArgumentParser(
        description="Automatizador de trials IPTV Fiesta",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py                    # Execução normal (browser visível)
  python main.py --headless         # Modo headless (sem interface)
  python main.py --verbose          # Modo debug com mais logs
        """
    )
    
    parser.add_argument(
        '--headless', 
        action='store_true',
        help='Executar browser em modo headless (sem interface gráfica)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Modo verbose com logs detalhados'
    )
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    sys.exit(main(
        headless=args.headless,
        verbose=args.verbose
    ))
