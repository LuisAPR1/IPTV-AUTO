"""Interface minimalista para o terminal — passo + barra de progresso."""

import os
import sys


# Cores ANSI
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


class ProgressUI:
    """UI minimalista: limpa consola, mostra passo + barra + branding."""

    STEPS = [
        "Inicializando browser...",
        "Criando email temporário...",
        "Submetendo email no site...",
        "Aguardando página de verificação...",
        "Aguardando código por email...",
        "Submetendo código de verificação...",
        "Aguardando página final...",
        "A extrair credenciais...",
    ]

    def __init__(self, total_steps: int = None):
        self.total = total_steps or len(self.STEPS)
        self.current = 0
        self._last_message = ""
        self._width = 50

    def _clear(self):
        """Limpa a consola."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _bar(self, pct: float) -> str:
        """Barra de progresso com blocos Unicode."""
        filled = int((pct / 100) * self._width)
        empty = self._width - filled
        bar = GREEN + "█" * filled + DIM + "░" * empty + RESET
        return f"{bar}  {pct:.0f}%"

    def _branding(self) -> str:
        return (
            f"{DIM}  Made by {RED}{BOLD}LuisR{RESET}{DIM}  |  "
            f"{RED}github.com/luisapr1{RESET}"
        )

    def _header(self) -> str:
        return f"{CYAN}{BOLD}  IPTV Fiesta Automatizador{RESET}"

    def update(self, step_index: int, message: str = ""):
        """Atualiza a UI com o passo atual e a barra de progresso.

        Args:
            step_index: Índice do passo (0-based).
            message: Mensagem opcional para substituir o STEPS padrão.
        """
        self.current = max(0, min(step_index, self.total))
        pct = (self.current / self.total) * 100 if self.total else 0
        label = message or self.STEPS[min(self.current, len(self.STEPS) - 1)]
        self._last_message = label

        self._clear()
        step_num = self.current + 1

        lines = [
            "",
            self._header(),
            "",
            f"  {BOLD}PASSO {step_num}/{self.total}{RESET}  {label}",
            "",
            f"  {self._bar(pct)}",
            "",
            self._branding(),
            "",
        ]
        print("\n".join(lines))
        sys.stdout.flush()

    def done(self, success: bool = True):
        """Mostra estado final."""
        self._clear()
        status = f"{GREEN}✔ Concluído com sucesso!{RESET}" if success else f"{RED}✗ Falhou{RESET}"
        lines = [
            "",
            self._header(),
            "",
            f"  {status}",
            "",
            self._branding(),
            "",
        ]
        print("\n".join(lines))
        sys.stdout.flush()

    def error(self, msg: str):
        """Mostra mensagem de erro."""
        self._clear()
        lines = [
            "",
            self._header(),
            "",
            f"  {RED}{BOLD}✗ ERRO:{RESET} {msg}",
            "",
            self._branding(),
            "",
        ]
        print("\n".join(lines))
        sys.stdout.flush()
