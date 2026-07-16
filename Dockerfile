FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        gdal-bin \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

RUN groupadd --gid 10001 openskagit \
    && useradd --uid 10001 --gid 10001 --create-home openskagit

COPY --chown=openskagit:openskagit . .
USER openskagit

CMD ["sh", "-c", "python manage.py migrate && python manage.py sync_public_intelligence && python manage.py collectstatic --noinput && python -m uvicorn config.asgi:application --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
