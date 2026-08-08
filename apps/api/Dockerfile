FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
  fastapi uvicorn[standard] pydantic pydantic-settings httpx python-multipart \
  sqlalchemy asyncpg geoalchemy2 shapely redis orjson structlog tenacity pytest pytest-asyncio
COPY landsignal ./landsignal
COPY tests ./tests
COPY pyproject.toml ./
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "landsignal.main:app", "--host", "0.0.0.0", "--port", "8000"]
