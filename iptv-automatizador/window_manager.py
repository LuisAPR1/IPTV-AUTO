"""Gestão de janelas Windows - mantém terminal visível e browser minimizado."""

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Só carregar no Windows
_IS_WINDOWS = False
if __import__('sys').platform == 'win32':
    try:
        import ctypes
        from ctypes import wintypes
        _IS_WINDOWS = True
    except ImportError:
        pass

if _IS_WINDOWS:
    # Constantes Windows
    SW_MINIMIZE = 6
    SW_SHOWMINNOACTIVE = 7
    SW_RESTORE = 9
    SW_SHOW = 5
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_SHOWWINDOW = 0x0040
    GWL_EXSTYLE = -20
    WS_EX_TOPMOST = 0x00000008
    GW_OWNER = 4

    # Tipos
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32


def _get_console_hwnd() -> Optional[int]:
    """Obtém o handle da janela do terminal atual."""
    if not _IS_WINDOWS:
        return None
    try:
        return kernel32.GetConsoleWindow()
    except Exception:
        return None


def _is_window_visible(hwnd: int) -> bool:
    """Verifica se uma janela está visível."""
    if not _IS_WINDOWS:
        return False
    return bool(user32.IsWindowVisible(hwnd))


def _get_window_text(hwnd: int) -> str:
    """Obtém o título de uma janela."""
    if not _IS_WINDOWS:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _get_window_owner(hwnd: int) -> int:
    """Obtém o owner de uma janela."""
    if not _IS_WINDOWS:
        return 0
    return user32.GetWindow(hwnd, GW_OWNER) or 0


def _is_taskbar_window(hwnd: int) -> bool:
    """Verifica se uma janela aparece na taskbar (visível, sem owner)."""
    if not _IS_WINDOWS:
        return False
    return _is_window_visible(hwnd) and _get_window_owner(hwnd) == 0


def set_window_minimized(hwnd: int) -> bool:
    """Minimiza uma janela pelo handle."""
    if not _IS_WINDOWS:
        return False
    try:
        return bool(user32.ShowWindow(hwnd, SW_MINIMIZE))
    except Exception as e:
        logger.debug(f"Erro ao minimizar janela {hwnd}: {e}")
        return False


def set_window_topmost(hwnd: int, topmost: bool = True) -> bool:
    """Coloca ou remove uma janela como sempre-no-topo."""
    if not _IS_WINDOWS:
        return False
    try:
        pos = HWND_TOPMOST if topmost else HWND_NOTOPMOST
        return bool(user32.SetWindowPos(
            hwnd, pos, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        ))
    except Exception as e:
        logger.debug(f"Erro ao alterar topmost: {e}")
        return False


def activate_window(hwnd: int) -> bool:
    """Ativa uma janela (traz para frente)."""
    if not _IS_WINDOWS:
        return False
    try:
        # Restaurar primeiro se minimizada
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.05)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception as e:
        logger.debug(f"Erro ao ativar janela: {e}")
        return False


def _get_window_pid(hwnd: int) -> int:
    """Obtém o PID do processo dono de uma janela."""
    if not _IS_WINDOWS:
        return 0
    try:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    except Exception:
        return 0


def minimize_other_windows(
    exclude_title_substrings: tuple = (),
    protected_hwnd: Optional[int] = None
) -> int:
    """Minimiza todas as janelas da taskbar exceto as excluídas.

    Args:
        exclude_title_substrings: Tuplo de substrings de títulos a não minimizar.
        protected_hwnd: Handle de janela a NUNCA minimizar (ex: o terminal).

    Returns:
        Número de janelas minimizadas.
    """
    if not _IS_WINDOWS:
        return 0

    minimized = 0
    excluded = exclude_title_substrings + ("ConsoleWindowClass",)

    def enum_callback(hwnd, _):
        nonlocal minimized
        # Nunca tocar na janela protegida
        if protected_hwnd and hwnd == protected_hwnd:
            return True
        if not _is_taskbar_window(hwnd):
            return True
        title = _get_window_text(hwnd)
        # Não minimizar janelas excluídas por título
        if any(exc.lower() in title.lower() for exc in excluded):
            return True
        if set_window_minimized(hwnd):
            minimized += 1
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    except Exception as e:
        logger.debug(f"Erro ao enumerar janelas: {e}")

    logger.info(f"Minimizadas {minimized} janelas")
    return minimized


def minimize_chromium_windows() -> int:
    """Procura e minimiza janelas do Chromium/Chrome/Edge.
    
    Returns:
        Número de janelas minimizadas.
    """
    if not _IS_WINDOWS:
        return 0

    minimized = 0
    chromium_names = ("chrome", "chromium", "edge", "brave", "playwright")

    def enum_callback(hwnd, _):
        nonlocal minimized
        if not _is_taskbar_window(hwnd):
            return True
        title = _get_window_text(hwnd)
        # Verificar classe da janela também
        class_name_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_name_buf, 256)
        class_name = class_name_buf.value

        if any(name in title.lower() for name in chromium_names) or \
           "chrome" in class_name.lower():
            if set_window_minimized(hwnd):
                minimized += 1
                logger.debug(f"Minimizada janela Chromium: '{title}'")
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    except Exception as e:
        logger.debug(f"Erro ao procurar Chromium: {e}")

    return minimized


def prepare_terminal_focus(
    minimize_others: bool = False,
    keep_topmost: bool = True
) -> None:
    """Prepara o terminal para ser a única janela visível.

    Args:
        minimize_others: Se True, minimiza todas as outras janelas da taskbar.
        keep_topmost: Se True, coloca o terminal como topmost temporariamente.
    """
    if not _IS_WINDOWS:
        return

    # Guardar o HWND da janela ativa AGORA — é o nosso terminal
    terminal_hwnd = user32.GetForegroundWindow()
    if not terminal_hwnd:
        logger.warning("Não foi possível obter handle do terminal")
        return

    logger.info("A preparar foco do terminal...")

    # 1. Minimizar outras janelas, protegendo explicitamente o nosso terminal
    if minimize_others:
        minimize_other_windows(protected_hwnd=terminal_hwnd)
        time.sleep(0.2)  # dar tempo às animações

    # 2. Restaurar e ativar o terminal (porque outras apps podem ter roubado foco)
    activate_window(terminal_hwnd)
    time.sleep(0.1)

    # 3. Colocar como topmost (sempre visível)
    if keep_topmost:
        set_window_topmost(terminal_hwnd, True)
        logger.info("Terminal definido como sempre-no-topo")

    # 4. Forçar foco novamente
    user32.SetForegroundWindow(terminal_hwnd)


def restore_terminal_normal() -> None:
    """Restaura o terminal ao comportamento normal (remove topmost)."""
    if not _IS_WINDOWS:
        return

    hwnd = _get_console_hwnd()
    if hwnd:
        set_window_topmost(hwnd, False)
        logger.info("Terminal restaurado ao comportamento normal")


def ensure_terminal_visible() -> None:
    """Garante que o terminal está visível e ativo."""
    if not _IS_WINDOWS:
        return

    hwnd = _get_console_hwnd()
    if hwnd:
        activate_window(hwnd)
        user32.SetForegroundWindow(hwnd)
