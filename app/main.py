import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import config
from app.core.chat import create_chat_client
from app.core.embeddings import Embedder
from app.core.errors import register_error_handlers
from app.core.llm import create_extractor
from app.domains.recruiting.router import router as recruiting_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Shared clients for the app's lifetime (reuse HTTP connections and the embedding cache).
    app.state.extractor = create_extractor()
    use_embeddings = config.SEMANTIC_MATCHING and bool(config.OPENROUTER_API_KEY)
    app.state.embedder = Embedder() if use_embeddings else None
    app.state.chat_client = create_chat_client()
    yield
    await app.state.extractor.aclose()
    if app.state.embedder:
        await app.state.embedder.aclose()
    if app.state.chat_client:
        await app.state.chat_client.close()


app = FastAPI(title="Recruiting Copilot API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=config.CORS_ORIGIN_REGEX,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(recruiting_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    # The interactive API docs double as the demo page.
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
