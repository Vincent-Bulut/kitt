# Image Python officielle (slim) comme base
FROM python:3.12-slim

# Récupère le binaire uv depuis l'image officielle (version épinglée)
COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /uvx /bin/

# Compile le bytecode à l'installation (démarrage plus rapide),
# copie les fichiers au lieu de liens (cache monté), pas de téléchargement de Python
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Installe uniquement les dépendances de prod (couche mise en cache tant que le lock ne change pas)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=backend/uv.lock,target=uv.lock \
    --mount=type=bind,source=backend/pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Utilisateur non-root pour exécuter l'API
RUN useradd --system --no-create-home --uid 1001 app

# Copie le code source (.env exclu via .dockerignore : les secrets sont fournis
# au runtime par docker-compose via ses variables d'environnement)
COPY --chown=app:app backend /app/backend/

# Le venv créé par uv est prioritaire dans le PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

# Apply database migrations, then start the API
CMD ["sh", "-c", "python -m backend.migrate && exec uvicorn backend.api.main:api --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log"]
