"""FastAPI Application Entry Point for The Inconvenient Vault.

Provides REST control endpoints, WebSocket telemetry streaming, CORS,
static asset serving for the web dashboard, and production hardware dependency injection.
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
import numpy as np

from app.adapters.audio import SoundDeviceAudioAdapter
from app.adapters.camera import OpenCVCameraAdapter
from app.adapters.esp32_hardware import ESP32SerialAdapter
from app.adapters.factory import get_hardware_adapter
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
    """Lifespan context manager initializing database, physical hardware, and engine services."""
    logger.info("Initializing The Inconvenient Vault Backend Services (Physical Hardware Mode)...")

    # 1. Database & Persistence Layer
    db_engine = create_database_engine(
        getattr(app.state, "db_url", "sqlite+aiosqlite:///vault.db")
    )
    await init_db(db_engine)
    session_factory = create_session_factory(db_engine)
    repository = SqliteVaultRepository(session_factory=session_factory)

    # 2. Production Hardware Peripherals
    hardware = getattr(app.state, "hardware", None) or get_hardware_adapter()
    camera = getattr(app.state, "camera", None) or OpenCVCameraAdapter()
    audio = getattr(app.state, "audio", None) or SoundDeviceAudioAdapter()
    face_verifier = FaceVerifier(default_threshold=0.85)
    voice_verifier = VoiceVerifier(default_threshold=0.80)

    # 3. Real-Time WebSocket Hub
    ws_manager = WebSocketManager()

    # 4. Central Authentication FSM Engine
    engine = VaultAuthEngine(hardware=hardware, repository=repository)
    await engine.initialize()

    # 5. Default Enrolled Biometric Vectors
    default_face_emb = np.ones(256, dtype=np.float32)
    default_face_emb /= np.linalg.norm(default_face_emb)

    default_voice_print = np.ones(256, dtype=np.float32)
    default_voice_print /= np.linalg.norm(default_voice_print)

    engine.set_face_verifier(verifier=face_verifier, enrolled_embedding=default_face_emb, threshold=0.85)
    engine.set_voice_verifier(
        verifier=voice_verifier,
        enrolled_voice_print=default_voice_print,
        expected_phrase="OPEN SESAME OVERENGINEERED",
        threshold=0.80,
    )

    # 6. Wire FSM State Change Broadcaster to WebSocket Hub
    async def on_state_transition(event: StateTransitionEvent) -> None:
        await ws_manager.broadcast_event("STATE_CHANGE", event.model_dump())

    engine.register_state_listener(on_state_transition)

    # 7. Wire Hardware Event Broadcaster to WebSocket Hub
    async def on_hardware_event(hw_event: HardwareEvent) -> None:
        await ws_manager.broadcast_event("HARDWARE_EVENT", hw_event.model_dump())

    hardware.register_event_listener(on_hardware_event)

    # 8. Seed or Synchronize Default Operator Record
    try:
        from app.core.auth import get_configured_password_hash, get_configured_password
        ph = PasswordHasher()
        configured_hash = get_configured_password_hash() or ph.hash(get_configured_password() or "1234")
        users = await repository.list_users()
        existing_user = users[0] if users else None

        if not existing_user:
            await repository.create_user(
                username="OPERATOR_001",
                rfid_uid="39D74320",
                password_hash=configured_hash,
                face_embedding=default_face_emb,
                voice_print=default_voice_print,
                voice_passphrase="OPEN SESAME OVERENGINEERED",
            )
            logger.info("Default operator 'OPERATOR_001' seeded into database with RFID 39D74320.")
        else:
            # Sync password hash and RFID UID with active operator
            await repository.update_user_password(existing_user.id, configured_hash)
            await repository.update_user_rfid(existing_user.id, "39D74320")
            logger.info(f"Synchronized credentials for operator '{existing_user.username}' (RFID: 39D74320).")
    except Exception as ex:
        logger.warning(f"Operator seeding/sync skipped or failed: {ex}")

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
        description="REST & WebSocket API for the 5-Stage Over-Engineered Sequential Authentication System (Physical Hardware Mode).",
        version="2.0.0",
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
