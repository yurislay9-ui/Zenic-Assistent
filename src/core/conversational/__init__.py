"""
Zenic-Agents Conversational Layer

Capa conversacional multi-turno con session management,
traduccion LLM, confirm manager.

Removed (external API connections deleted):
  - TelegramAdapter, DiscordAdapter (adapters directory deleted)
"""

__all__ = []  # Lazy-loaded via __getattr__

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
    # TelegramAdapter and DiscordAdapter removed — external API connections deleted
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
