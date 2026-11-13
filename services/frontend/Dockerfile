# Web UI: static single-page app + allow-listed REST proxy + telemetry metrics.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/srv
WORKDIR /srv
COPY services/frontend/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
COPY services/frontend /srv/frontend
RUN useradd --create-home --uid 1001 app
USER app
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/health')"
CMD ["uvicorn", "frontend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
