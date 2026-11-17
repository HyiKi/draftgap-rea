FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY LICENSE draftgap_model.py validate_fidelity.py ./
COPY web ./web
COPY examples ./examples

RUN mkdir -p /app/data

EXPOSE 8765
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3)" || exit 1

ENTRYPOINT ["python3", "-I", "draftgap_model.py", "--serve", "--host", "0.0.0.0", "--port", "8765"]
