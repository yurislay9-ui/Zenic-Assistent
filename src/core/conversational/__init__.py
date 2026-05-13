"""
Zenic-Agents Conversational Layer

Capa conversacional multi-turno con session management,
traduccion LLM, confirm manager y adaptadores de canal.
"""

__all__ = [
    "SessionManager",
    "ConversationManager",
    "ConversationEngine",
    "ZenicBridge",
    "LLMTranslator",
    "LLMDrafter",
    "ConfirmManager",
    "TelegramAdapter",
    "DiscordAdapter",
]

def __getattr__(name):
    if name == "SessionManager":
        from src.core.conversational.session_manager import SessionManager
        return SessionManager
    if name == "ConversationManager":
        from src.core.conversational.conversation.manager import ConversationManager
        return ConversationManager
    if name == "ConversationEngine":
        from src.core.conversational.conversation_engine import ConversationEngine
        return ConversationEngine
    if name == "ZenicBridge":
        from src.core.conversational.zenic_bridge import ZenicBridge
        return ZenicBridge
    if name == "LLMTranslator":
        from src.core.conversational.llm_translator import LLMTranslator
        return LLMTranslator
    if name == "LLMDrafter":
        from src.core.conversational.llm_drafter import LLMDrafter
        return LLMDrafter
    if name == "ConfirmManager":
        from src.core.conversational.confirm_manager import ConfirmManager
        return ConfirmManager
    if name == "TelegramAdapter":
        from src.core.conversational.adapters.telegram import TelegramAdapter
        return TelegramAdapter
    if name == "DiscordAdapter":
        from src.core.conversational.adapters.discord import DiscordAdapter
        return DiscordAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
