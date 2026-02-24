# MyndLens Backend — Production Container
# Built by MyndLens CI, deployed by ObeGee via DAI

FROM python:3.11-slim

WORKDIR /app

# System deps (curl required for health check)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ -r requirements.txt

# Application code
COPY backend/ .

# Non-root user
RUN useradd -m -u 1000 myndlens && chown -R myndlens:myndlens /app
USER myndlens

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8002/api/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002"]
