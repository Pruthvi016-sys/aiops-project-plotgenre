# FastAPI gateway - the only backend the UI talks to.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/srv
WORKDIR /srv
COPY services/gateway/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
# Only the dependency-free drift statistics are shared with the ML package.
COPY src/plotgenre/__init__.py /srv/plotgenre/__init__.py
COPY src/plotgenre/monitoring/__init__.py src/plotgenre/monitoring/drift_core.py /srv/plotgenre/monitoring/
COPY services/gateway /srv/gateway
RUN useradd --create-home --uid 1001 app
USER app
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "gateway.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
