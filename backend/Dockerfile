# Use official slim Python image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GCP_PROJECT_ID=gn-saarthi \
    GCP_REGION=us-central1 \
    VERTEX_AI_LOCATION=us-central1 \
    QDRANT_COLLECTION_NAME=college_docs_v2 \
    FIRESTORE_DATABASE_ID=default \
    ALLOWED_DOMAIN=iitgn.ac.in \
    FASTEMBED_CACHE_PATH=/app/.fastembed_cache

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Qdrant BM42 sparse model files during build phase to prevent runtime latency and filesystem permission issues
RUN python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding(model_name='Qdrant/bm42-all-minilm-l6-v2-attentions')"

# Copy application source code
COPY app/ app/

# Expose port
EXPOSE 8080

# Run FastAPI app using uvicorn
CMD exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
