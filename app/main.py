import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.core.errors import register_error_handlers
from app.core.llm import create_extractor
from app.domains.recruiting.router import router as recruiting_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One shared client for the app's lifetime (reuses HTTP connections).
    app.state.extractor = create_extractor()
    yield
    await app.state.extractor.aclose()


app = FastAPI(title="Recruiting Copilot API", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(recruiting_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    # The interactive API docs double as the demo page.
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
