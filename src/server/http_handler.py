"""
ZENIC-AGENTS v16 - Unified HTTP Handler

Handler HTTP compatible con la API de OpenAI. Unifica la logica
que antes estaba duplicada entre main.py (TUI/Textual) y main_headless.py (Termux).
"""

from .http_parts import *  # noqa: F401,F403
from .http_parts import ZenicHTTPHandler  # explicit

__all__ = ["ZenicHTTPHandler"]
