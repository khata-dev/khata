FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY khata ./khata

RUN pip install .

# data/ is a volume mount, not baked in
VOLUME ["/app/data"]

EXPOSE 8000

CMD ["khata", "--help"]
