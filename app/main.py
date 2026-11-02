"""FastAPI entrypoint for Reelwala."""

import logging

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.api.videos import router as videos_router
from app.api.webhooks import router as webhooks_router
from app.logging_utils import SensitiveDataFilter

# Install sensitive data masking filter for logging privacy
logging.getLogger().addFilter(SensitiveDataFilter())

app = FastAPI(
    title="Reelwala",
    description="WhatsApp-first short video ad creation for local food businesses",
    version="0.1.0",
)

app.include_router(webhooks_router)
app.include_router(videos_router)
app.include_router(admin_router)



@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint returning system status."""
    return {"status": "ok"}

