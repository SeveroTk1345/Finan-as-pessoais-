# Imagem única: site estático (Next.js) + API (FastAPI), servidos na mesma origem.
# Construção:  docker build -t financas .
#
# Atrás de um proxy com certificado próprio (ex.: ambiente de testes), passe o
# certificado como segredo opcional:  docker build --secret id=ca,src=/caminho/ca.crt ...
# Sem o segredo, nada muda.

# --- 1. site estático ---------------------------------------------------------------
FROM node:22.22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=ca,required=false \
    sh -c '[ -f /run/secrets/ca ] && export NODE_EXTRA_CA_CERTS=/run/secrets/ca; npm ci --no-audit --no-fund'
COPY frontend/ ./
# O build baixa a fonte Inter uma vez; depois ela é servida pelo próprio app.
RUN --mount=type=secret,id=ca,required=false \
    sh -c '[ -f /run/secrets/ca ] && export NODE_EXTRA_CA_CERTS=/run/secrets/ca; npm run build'

# --- 2. API ---------------------------------------------------------------------------
FROM python:3.13-slim AS api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN --mount=type=secret,id=ca,required=false \
    sh -c '[ -f /run/secrets/ca ] && export PIP_CERT=/run/secrets/ca; pip install --no-cache-dir uv==0.11.32'
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=secret,id=ca,required=false \
    sh -c '[ -f /run/secrets/ca ] && export SSL_CERT_FILE=/run/secrets/ca; uv sync --frozen --no-dev --no-install-project'
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
RUN --mount=type=secret,id=ca,required=false \
    sh -c '[ -f /run/secrets/ca ] && export SSL_CERT_FILE=/run/secrets/ca; uv sync --frozen --no-dev'
COPY --from=web /web/out ./static
RUN useradd --system --uid 10001 --home /app financas && chown -R financas /app
USER financas
ENV PATH="/app/.venv/bin:$PATH" FIN_STATIC_DIR=/app/static FIN_ENVIRONMENT=production
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000')).status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "2"]
