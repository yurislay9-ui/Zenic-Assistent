"""
Generador de respuestas conversacionales.

Maneja la generacion de respuestas para cada categoria
de intencion: chat, preguntas, comandos, config, feedback.
"""

from __future__ import annotations

from ..types.session import Session
from ..types.intent import IntentCategory
from ..types.personality import PersonalityProfile


class ResponseGenerator:
    """
    Genera respuestas conversacionales por categoria.

    Cada metodo retorna el contenido de texto (str).
    El formateo (markdown, mixto) se maneja en el engine.
    """

    # ─── Chat general ─────────────────────────────────────────

    def generate_chat(
        self, text: str, profile: PersonalityProfile, session: Session
    ) -> str:
        """Genera respuesta para chat general."""
        greetings = [
            "hola", "hey", "hi", "hello", "buenos", "buenas",
            "que tal", "how are you",
        ]
        if any(g in text for g in greetings):
            lang = session.config.language
            if lang == "es":
                return (
                    f"Hola! Soy {profile.name}, tu asistente. "
                    "Puedo ayudarte con codigo, automatizaciones, "
                    "razonamiento y mas. Que necesitas?"
                )
            return (
                f"Hi! I'm {profile.name}, your assistant. "
                "I can help with code, automations, reasoning and more. "
                "What do you need?"
            )

        thanks = ["gracias", "thanks", "thank you", "ty"]
        if any(t in text for t in thanks):
            return "De nada! Si necesitas algo mas, aqui estoy."

        ok_words = ["ok", "bien", "perfecto", "genial", "great"]
        if any(o in text for o in ok_words):
            return "Perfecto! Algo mas en lo que pueda ayudarte?"

        # Default conversacional
        return (
            "Entiendo. Puedo ayudarte con varias cosas:\n\n"
            "- **Codigo**: Crear, depurar, refactorizar y optimizar\n"
            "- **Preguntas**: Explicar conceptos y responder consultas\n"
            "- **Automatizaciones**: Configurar workflows y triggers\n"
            "- **Razonamiento**: Analisis paso a paso\n\n"
            "Que te gustaria hacer?"
        )

    # ─── Preguntas ────────────────────────────────────────────

    def generate_question(self, message: str, profile: PersonalityProfile) -> str:
        """Genera respuesta para preguntas."""
        return (
            "Esa es una buena pregunta. Basandome en mi conocimiento interno:\n\n"
            f"Tu pregunta fue: *{message}*\n\n"
            "Para una respuesta mas detallada y precisa, puedo consultar "
            "el motor de razonamiento. Necesitas que lo haga?"
        )

    # ─── Comandos ─────────────────────────────────────────────

    def handle_command(self, text: str, session: Session) -> str:
        """Maneja comandos directos."""
        if any(w in text for w in ["limpiar", "clear", "reset"]):
            session.messages = [m for m in session.messages if m.is_system]
            return "Historial limpiado. Empezamos de nuevo!"

        if any(w in text for w in ["ayuda", "help", "comandos"]):
            return (
                "Comandos disponibles:\n\n"
                "- `limpiar` / `reset` — Limpiar historial\n"
                "- `ayuda` / `help` — Mostrar esta ayuda\n"
                "- `cambiar idioma [es|en]` — Cambiar idioma\n"
                "- `cambiar tono [casual|profesional|tecnico]` — Cambiar tono\n"
                "- `personalidad [zenic|logic|nova]` — Cambiar personalidad\n"
                "- `estado` — Ver estado de la sesion\n"
            )

        if "estado" in text:
            return (
                f"Estado de sesion:\n"
                f"- Mensajes: {session.message_count}\n"
                f"- Estado: {session.state.value}\n"
                f"- Idioma: {session.config.language}\n"
                f"- Tono: {session.config.tone}\n"
            )

        return "Comando no reconocido. Escribe `ayuda` para ver los disponibles."

    # ─── Configuracion ────────────────────────────────────────

    def handle_config(self, text: str, session: Session) -> str:
        """Maneja cambios de configuracion."""
        if "idioma" in text or "language" in text:
            if "en" in text or "english" in text or "ingles" in text:
                session.config.language = "en"
                return "Language changed to English."
            elif "es" in text or "spanish" in text or "espanol" in text:
                session.config.language = "es"
                return "Idioma cambiado a espanol."

        if "tono" in text or "tone" in text:
            if "casual" in text:
                session.config.tone = "casual"
                return "Tono cambiado a casual."
            elif "tecnico" in text or "technical" in text:
                session.config.tone = "technical"
                return "Tono cambiado a tecnico."
            elif "profesional" in text or "professional" in text:
                session.config.tone = "professional"
                return "Tono cambiado a profesional."

        if "personalidad" in text or "personality" in text:
            for name in ("zenic", "logic", "nova"):
                if name in text:
                    session.config.personality_name = name
                    return f"Personalidad cambiada a {name.title()}."

        return (
            "Configuracion no reconocida. Opciones:\n"
            "- `cambiar idioma es|en`\n"
            "- `cambiar tono casual|profesional|tecnico`\n"
            "- `personalidad zenic|logic|nova`"
        )

    # ─── Feedback ─────────────────────────────────────────────

    def handle_feedback(self, text: str, profile: PersonalityProfile) -> str:
        """Maneja feedback del usuario."""
        positive = ["bien", "bueno", "correcto", "me gusta", "good", "great"]
        negative = ["mal", "incorrecto", "no me gusta", "wrong", "bad"]

        if any(p in text for p in positive):
            return "Me alegra que te haya sido util! Algo mas?"

        if any(n in text for n in negative):
            return (
                "Lamento que no fue lo que esperabas. "
                "Puedo intentar de nuevo con un enfoque diferente. "
                "Que cambiarias?"
            )

        return "Gracias por tu feedback. Lo tendre en cuenta para mejorar."
