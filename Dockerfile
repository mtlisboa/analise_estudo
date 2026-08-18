FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system django \
    && adduser --system --ingroup django django \
    && mkdir /data \
    && chown django:django /data

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=django:django src ./src

USER django
WORKDIR /app/src

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
