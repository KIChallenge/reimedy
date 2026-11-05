# SV-Wissensbasis als Online-Service (HTTP-API, read-only SQLite + FTS5 + sqlite-vec)
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_SYSTEM_PYTHON=1 UV_PROJECT_ENVIRONMENT=/usr/local \
    HOST=0.0.0.0 PORT=8765 FASTEMBED_CACHE_PATH=/srv/.fastembed
WORKDIR /srv
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev
COPY . .
# Embedding-Modell vorladen und DB bauen (Embeddings kommen aus build/emb_cache, nur das Delta wird gerechnet)
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('minishlab/potion-multilingual-128M')" \
 && python knowledge/build/build_db.py && ls -lh knowledge/build/lotse.sqlite
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8765\")}/health', timeout=4)" || exit 1
CMD ["sh", "-c", "python knowledge/build/search.py --serve --host $HOST --port $PORT"]
