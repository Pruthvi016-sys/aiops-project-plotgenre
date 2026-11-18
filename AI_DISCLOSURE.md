# AI Usage


* The problem, the dataset and the tool stack (Ray, DVC, MLflow, FastAPI, Prometheus/Grafana/Alertmanager, Docker Compose) come from my approved project statement.
* Claude generated most of the first version of the code, configuration files (Dockerfiles, `docker-compose.yml`, `dvc.yaml`, `MLproject`, Prometheus/Grafana/Alertmanager configs), tests and documentation, working from that statement and the course guideline documents.

After that, Claude was used mainly for correct syntax, exact command sequences, and debugging build, networking and monitoring issues as they came up. These included the port clashes, the Alertmanager restarts, the two false alerts, the UI telemetry bug and the MLproject quoting bug.

I ran every build, pipeline run, drift test, rollback and test suite myself on my laptop, took all the screenshots, and checked each result before it went into the report. Claude helped me draft the report and this README from those results, and I reviewed and edited them.

AI assistance had more impact on boilerplate, syntax reference and troubleshooting than on the design choices, which come from my project statement. Most of the hands-on work was done by hand: running the stack, triggering drift and rollback, and reading and verifying the evidence.
