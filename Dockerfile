FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir . \
    && useradd --create-home --shell /usr/sbin/nologin appuser

USER appuser

EXPOSE 8000

CMD ["uvicorn", "job_processor_service.main:app", "--host", "0.0.0.0", "--port", "8000"]