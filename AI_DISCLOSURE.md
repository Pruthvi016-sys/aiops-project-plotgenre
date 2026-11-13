# AI disclosure

Required by the DA3408 *Fair and Responsible Use of AI* code of conduct.

## Tools used

- Claude (Anthropic), used through the Claude app.

## How they were used

- The problem statement, dataset choice and overall approach (Ray, DVC, MLflow, FastAPI, Prometheus/Grafana, Docker Compose) are from my approved project statement.
- Claude generated most of the first version of the code, configuration files (Dockerfiles, `docker-compose.yml`, `dvc.yaml`, `MLproject`, Prometheus/Grafana/Alertmanager configs), tests and documentation, working from that statement and the course guideline documents.
- I then ran the whole system myself on Ubuntu: set up the environment, ran the DVC pipeline, the Docker Compose stack, the tests, the drift/retraining and rollback flows, and took all the evidence screenshots from those runs.
- I used Claude to check the code against the evaluation rubric, to explain parts of the code I did not understand, and to debug errors I hit while running it.

## Impact

AI tools sped up the writing of boilerplate and configuration a lot. Every metric, MLflow run, Grafana panel and screenshot in this repository comes from actually running the pipeline and services on my machine, not from AI output. I have gone through each component so that I can explain and change it in the viva.
