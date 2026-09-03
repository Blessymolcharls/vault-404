"""FastAPI Application Entry Point for The Inconvenient Vault.

Provides REST control endpoints, WebSocket telemetry streaming, CORS,
static asset serving for the web dashboard, and lifespan dependency injection.
"""

from contextlib import asynccontextmanager
import logging
import os
from typing import AsyncGenerator
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.factory import get_hardware_adapter
from app.adapters.mock_audio import MockAudioAdapter
from app.adapters.mock_camera import MockCameraAdapter
from app.adapters.mock_hardware import MockHardwareAdapter
from app.api.routes import router
from app.api.websocket_manager import WebSocketManager
from app.audio.voice_verifier import VoiceVerifier
from app.core.engine import EngineConfig, StateTransitionEvent, VaultAuthEngine
from app.core.types import HardwareEvent
from app.database.repository import SqliteVaultRepository
from app.database.session import (
    create_database_engine,
    create_session_factory,
    init_db,
)
from app.vision.face_verifier import FaceVerifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vault.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager initializing database, hardware, and engine services."""
    logger.info("Initializing The Inconvenient Vault Backend Services...")

    # 1. Database & Persistence Layer
    db_engine = create_database_engine(
        getattr(app.state, "db_url", "sqlite+aiosqlite:///vault.db")
    )
    await init_db(db_engine)
    session_factory = create_session_factory(db_engine)
    repository = SqliteVaultRepository(session_factory=session_factory)

    # 2. Hardware & Virtual Biometric Peripherals
    hardware = getattr(app.state, "hardware", None) or get_hardware_adapter()
    camera = MockCameraAdapter()
    audio = MockAudioAdapter()
    face_verifier = FaceVerifier(default_threshold=0.90)
    voice_verifier = VoiceVerifier(default_threshold=0.85)

    # 3. Real-Time WebSocket Hub
    ws_manager = WebSocketManager()

    # 4. Central Authentication FSM Engine
    engine = VaultAuthEngine(hardware=hardware, repository=repository)
    await engine.initialize()

    # Default synthetic enrolled biometrics for Subject 777 / Speaker 1
    enrolled_face = face_verifier.extract_embeddings(
        camera.generate_synthetic_face_frame(subject_seed=777)
    )
    enrolled_voice = voice_verifier.extract_voice_print(
        audio.generate_synthetic_utterance(speaker_seed=1)
    )
    if enrolled_face is not None:
        engine.set_face_verifier(verifier=face_verifier, enrolled_embedding=enrolled_face, threshold=0.90)
    if enrolled_voice is not None:
        engine.set_voice_verifier(
            verifier=voice_verifier,
            enrolled_voice_print=enrolled_voice,
            expected_phrase="OPEN SESAME OVERENGINEERED",
            threshold=0.85,
        )

    # 5. Wire FSM State Change Broadcaster to WebSocket Hub
    async def on_state_transition(event: StateTransitionEvent) -> None:
        await ws_manager.broadcast_event("STATE_CHANGE", event.model_dump())

    engine.register_state_listener(on_state_transition)

    # 6. Wire Hardware Event Broadcaster to WebSocket Hub
    async def on_hardware_event(hw_event: HardwareEvent) -> None:
        await ws_manager.broadcast_event("HARDWARE_EVENT", hw_event.model_dump())

    hardware.register_event_listener(on_hardware_event)

    # 7. Seed Default Operator Record if not present
    try:
        existing_user = await repository.get_user_by_rfid("E2806894")
        if not existing_user and enrolled_face is not None and enrolled_voice is not None:
            ph = PasswordHasher()
            pwd_hash = ph.hash("VaultMasterKey#2026!")
            await repository.create_user(
                username="OPERATOR_001",
                rfid_uid="E2806894",
                password_hash=pwd_hash,
                face_embedding=enrolled_face,
                voice_print=enrolled_voice,
                voice_passphrase="OPEN SESAME OVERENGINEERED",
            )
            logger.info("Default operator 'OPERATOR_001' seeded into database.")
    except Exception as ex:
        logger.warning(f"Operator seeding skipped or failed: {ex}")

    # Store singletons on app state for dependency injection
    app.state.db_engine = db_engine
    app.state.session_factory = session_factory
    app.state.repository = repository
    app.state.hardware = hardware
    app.state.camera = camera
    app.state.audio = audio
    app.state.face_verifier = face_verifier
    app.state.voice_verifier = voice_verifier
    app.state.ws_manager = ws_manager
    app.state.engine = engine

    logger.info("Vault services ready. Starting application...")
    yield

    logger.info("Shutting down The Inconvenient Vault Backend Services...")
    await db_engine.dispose()
    hardware.release()
    camera.release()
    audio.release()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    """FastAPI Application Factory."""
    app = FastAPI(
        title="The Inconvenient Vault API",
        description="REST & WebSocket API for the 5-Stage Over-Engineered Sequential Authentication System.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Configure CORS for UI / Web clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include REST & WebSocket API Routes
    app.include_router(router)

    # Mount Static Directory for Web Dashboard
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/", response_class=FileResponse, include_in_schema=False)
        async def serve_dashboard() -> FileResponse:
            """Serve the single-page Web Dashboard."""
            index_path = os.path.join(static_dir, "index.html")
            return FileResponse(index_path)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
