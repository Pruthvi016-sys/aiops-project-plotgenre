# MLflow model server (+ supervisor that redeploys when the champion alias moves).
# The same image also runs the MLflow tracking server / model registry.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    MLFLOW_DISABLE_AGENT_HINT=1
WORKDIR /srv
COPY services/model_server/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt httpx==0.28.1 prometheus-client==0.26.0
COPY services/model_server/serve.py /srv/serve.py
RUN useradd --create-home --uid 1001 app && mkdir -p /mlflow && chown app /mlflow
USER app
EXPOSE 5001 9102
CMD ["python", "/srv/serve.py"]
