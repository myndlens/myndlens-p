# MyndLens Backend — Production Container
# Built by MyndLens CI, deployed by ObeGee via DAI

FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY backend/ .

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8002/api/health || exit 1

EXPOSE 8002

# ObeGee injects env vars via compose:
# MONGO_URL, DB_NAME, OBEGEE_API_URL, JWT_SECRET_KEY,
# MYNDLENS_DISPATCH_TOKEN, NODE_ENV, PORT
# Secret: MYNDLENS_PRIVATE_KEY_HEX

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002"]
