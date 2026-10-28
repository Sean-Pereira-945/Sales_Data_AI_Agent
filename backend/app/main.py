"""FastAPI application entry point.

Run (dev):  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dashboard import router as dashboard_router

app = FastAPI(
    title="Sales Intelligence Platform API",
    version="0.1.0",
    description="Dashboard + (later) LangGraph agent over the Olist sales dataset.",
)

# The Vite dev server runs on 5173; allow it (and localhost variants) in dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router, prefix="/api")


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
