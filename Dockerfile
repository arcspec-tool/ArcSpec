FROM python:3.13.16-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libharfbuzz-subset0 \
    libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info \
    curl gettext \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -r appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/media /app/staticfiles && chown -R appuser:appuser /app/media /app/staticfiles

USER appuser

EXPOSE 27415

CMD python manage.py collectstatic --noinput \
    && python manage.py compress \
    && exec uvicorn config.asgi:application --host 0.0.0.0 --port 27415 \
        --lifespan off --timeout-graceful-shutdown 5
