"""
Aplicacion FastAPI del Asistente.

Crea y configura la app con rutas, middleware,
WebSocket y health checks.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from ..config.env import AgentsConfig, get_config
from ..config.constants import APP_NAME, APP_VERSION
from ..session_manager import SessionManager
from ..conversation_engine import ConversationEngine
from ..personality_manager import PersonalityManager
from ..zenic_bridge import ZenicBridge

logger = logging.getLogger("zenic_agents.conversational.server")


class AgentsApp:
    """
    Contenedor de la aplicacion de agentes.

    Inicializa todos los componentes y los conecta:
      - SessionManager → ConversationEngine
      - PersonalityManager → ConversationEngine
      - ZenicBridge → ConversationEngine
      - FastAPI app → routes → engine
    """

    def __init__(
        self,
        config: Optional[AgentsConfig] = None,
        orchestrator: Any = None,
    ) -> None:
        self.config = config or get_config()
        self.start_time = time.time()

        # Inicializar componentes core
        self.sessions = SessionManager(
            max_sessions=self.config.max_sessions,
        )
        self.personalities = PersonalityManager()
        self.bridge = ZenicBridge(orchestrator=orchestrator)
        self.engine = ConversationEngine(
            session_manager=self.sessions,
            personality_manager=self.personalities,
            zenic_bridge=self.bridge,
        )

        # Crear app FastAPI
        self._app = self._build_fastapi_app()

    @property
    def app(self):
        """Retorna la instancia de FastAPI."""
        return self._app

    def _build_fastapi_app(self):
        """Construye la aplicacion FastAPI con todas las rutas."""
        from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel

        app = FastAPI(
            title=APP_NAME,
            version=APP_VERSION,
            description="Asistente conversacional basado en Zenic-Agents",
        )

        # CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.config.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # ─── Modelos Pydantic ────────────────────────────────

        class ChatRequest(BaseModel):
            message: str
            session_id: str = ""
            personality: str = ""
            stream: bool = False

        class ChatResponse(BaseModel):
            session_id: str
            content: str
            format: str = "markdown"
            intent_category: str = ""
            latency_ms: float = 0.0
            source: str = "deterministic"
            metadata: dict = {}

        class SessionResponse(BaseModel):
            session_id: str
            state: str
            message_count: int = 0

        # ─── Referencia al self ─────────────────────────────

        agents = self

        # ─── Rutas ───────────────────────────────────────────

        @app.get("/health")
        async def health():
            """Health check del agente."""
            uptime = time.time() - agents.start_time
            return {
                "status": "healthy",
                "app": APP_NAME,
                "version": APP_VERSION,
                "uptime_seconds": round(uptime, 1),
                "sessions": agents.sessions.active_count,
                "engine_available": agents.bridge.is_available,
            }

        @app.get("/ready")
        async def ready():
            """Readiness probe."""
            return {"ready": True}

        @app.post("/v1/chat", response_model=ChatResponse)
        async def chat(request: ChatRequest):
            """Endpoint principal de chat."""
            # Obtener o crear sesion
            session = agents.sessions.get_or_create(
                session_id=request.session_id or None,
            )

            # Procesar mensaje
            response = await agents.engine.process_message(
                session_id=session.session_id,
                user_message=request.message,
                personality=agents.personalities.get(request.personality),
            )

            return ChatResponse(
                session_id=session.session_id,
                content=response.content,
                format=response.format.value,
                intent_category=response.metadata.intent_category,
                latency_ms=response.metadata.latency_ms,
                source=response.metadata.source,
                metadata={
                    "engine_used": response.metadata.engine_used,
                    "tools_used": response.metadata.tools_used,
                },
            )

        @app.post("/v1/sessions", response_model=SessionResponse)
        async def create_session():
            """Crea una nueva sesion."""
            session = agents.sessions.create_session()
            return SessionResponse(
                session_id=session.session_id,
                state=session.state.value,
                message_count=session.message_count,
            )

        @app.get("/v1/sessions/{session_id}", response_model=SessionResponse)
        async def get_session(session_id: str):
            """Obtiene info de una sesion."""
            session = agents.sessions.get_session(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Sesion no encontrada")
            return SessionResponse(
                session_id=session.session_id,
                state=session.state.value,
                message_count=session.message_count,
            )

        @app.delete("/v1/sessions/{session_id}")
        async def end_session(session_id: str):
            """Termina una sesion."""
            ended = agents.sessions.end_session(session_id)
            if not ended:
                raise HTTPException(status_code=404, detail="Sesion no encontrada")
            return {"status": "ended", "session_id": session_id}

        @app.get("/v1/personalities")
        async def list_personalities():
            """Lista personalidades disponibles."""
            return {
                "personalities": agents.personalities.list_profiles(),
                "default": agents.personalities._default_name,
            }

        @app.get("/v1/stats")
        async def get_stats():
            """Estadisticas del agents."""
            return {
                "engine": agents.engine.stats,
                "bridge": agents.bridge.stats,
                "sessions": agents.sessions.stats,
            }

        @app.get("/v1/models")
        async def list_models():
            """Lista modelos disponibles (OpenAI-compatible)."""
            return {
                "object": "list",
                "data": [
                    {
                        "id": "zenic-agents",
                        "object": "model",
                        "created": int(agents.start_time),
                        "owned_by": "zenic-agents",
                    }
                ],
            }

        # ─── WebSocket para streaming ────────────────────────

        @app.websocket("/ws/chat")
        async def ws_chat(websocket: WebSocket):
            """WebSocket para chat con streaming."""
            await websocket.accept()
            session = agents.sessions.create_session()
            try:
                await websocket.send_json({
                    "type": "session",
                    "session_id": session.session_id,
                })
                while True:
                    data = await websocket.receive_json()
                    message = data.get("message", "")
                    if not message:
                        continue

                    async for chunk in agents.engine.stream_message(
                        session.session_id, message
                    ):
                        await websocket.send_json({
                            "type": "chunk",
                            "content": chunk.content,
                            "is_final": chunk.is_final,
                        })
            except WebSocketDisconnect:
                agents.sessions.end_session(session.session_id)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                try:
                    await websocket.send_json({"type": "error", "message": str(e)})
                except Exception:
                    pass

        return app


def create_app(
    config: Optional[AgentsConfig] = None,
    orchestrator: Any = None,
) -> Any:
    """
    Factory para crear la app FastAPI.

    Uso:
        app = create_app()
        uvicorn.run(app, host="0.0.0.0", port=5000)
    """
    agents = AgentsApp(config=config, orchestrator=orchestrator)
    return agents.app
