# Backend image: FastAPI + LangGraph agent over CockroachDB.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (declared in pyproject.toml) for better layer caching.
# The project itself is namespace-package only (py-modules = []), so this pulls in
# the dependency set without needing the source yet.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# App source. Modules resolve via pythonpath = ["."] from this dir (see pyproject).
COPY . .

EXPOSE 8000

# CockroachDB uses sslmode=verify-full, so the root cert must be present at
# ~/.postgresql/root.crt inside the container — mount it (see docker-compose.yml).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
