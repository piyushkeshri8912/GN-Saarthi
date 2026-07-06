from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.routers import auth, chat, documents, quick_links
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GN Saarthi - Backend API",
    description="Backend services for GN Saarthi.",
    version="2.0.1",
)

# CORS Configuration
# Parse whitelisted origins from settings
allowed_origins = []
if settings.ALLOWED_CORS_ORIGINS:
    allowed_origins = [origin.strip() for origin in settings.ALLOWED_CORS_ORIGINS.split(",") if origin.strip()]

# In production, allow Vercel subdomains dynamically to prevent circular dependencies
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["http://localhost:3000"],
    allow_origin_regex=r"^(https://.*\.vercel\.app|http://localhost:3000)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Register routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(quick_links.router)



@app.get("/health", tags=["health"])
def health():
    """
    Service health check endpoint.
    """
    return {
        "status": "healthy",
        "service": "GN Saarthi API"
    }

@app.get("/", tags=["root"])
def read_root():
    return {"message": "Welcome to IITGN College Portal API (GN Saarthi)"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting GN Saarthi API server...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")