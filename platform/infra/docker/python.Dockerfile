# One image, three roles (api | worker | edge). Build context = repo root.
FROM python:3.12-slim AS base
ARG WITH_VISION=false
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/srv PIP_NO_CACHE_DIR=1
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
COPY ai_core/requirements-vision.txt /tmp/requirements-vision.txt
RUN if [ "$WITH_VISION" = "true" ]; then pip install -r /tmp/requirements-vision.txt; fi

COPY backend/app /srv/app
COPY backend/proto /srv/proto
COPY ai_core /srv/ai_core
COPY security /srv/security
RUN mkdir -p /srv/app/generated && python -m grpc_tools.protoc -I /srv/proto --python_out=/srv/app/generated --grpc_python_out=/srv/app/generated /srv/proto/telemetry.proto

RUN useradd -r -u 10001 aether && chown -R aether /srv
USER aether
EXPOSE 8000 9101 9102 50051
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
