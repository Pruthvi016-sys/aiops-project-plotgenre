# Pipeline runner: full training environment (Ray, scikit-learn, MLflow, DVC)
# + the FastAPI console API. The project directory is bind-mounted at /project
# so `dvc repro` works on the same Git/DVC workspace you use on the host.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/srv:/project/src PROJECT_DIR=/project HOME=/tmp \
    MLFLOW_DISABLE_AGENT_HINT=1 RAY_USAGE_STATS_ENABLED=0 \
    USER=plotgenre LOGNAME=plotgenre
RUN apt-get update && apt-get install -y --no-install-recommends git git-lfs \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
COPY services/pipeline_runner /srv/pipeline_runner
WORKDIR /project
EXPOSE 8100
CMD ["uvicorn", "pipeline_runner.app.main:app", "--host", "0.0.0.0", "--port", "8100"]
