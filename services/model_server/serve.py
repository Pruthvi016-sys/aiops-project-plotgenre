"""Model-server supervisor: MLflow model serving + automatic (re)deployment.

* Resolves ``models:/<name>@champion`` in the MLflow Model Registry.
* Starts ``mlflow models serve`` for that exact version on ``SERVE_PORT``.
* Polls the registry every ``POLL_SECONDS``; when the champion alias moves
  (new model promoted, or rolled back), it redeploys the new version.
* If the new version fails its health check, it **rolls back automatically**
  to the version that was running before and records the failure.
* Exposes Prometheus metrics on ``METRICS_PORT`` (deployed version, deploys,
  failed deploys, rollbacks, up).
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from typing import Optional

import httpx
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient
from prometheus_client import Counter, Gauge, start_http_server

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s | %(levelname)-7s | model-server | %(message)s")
log = logging.getLogger("model-server")
logging.getLogger("httpx").setLevel(logging.WARNING)

MODEL_NAME = os.environ.get("MODEL_NAME", "plotgenre-classifier")
MODEL_ALIAS = os.environ.get("MODEL_ALIAS", "champion")
SERVE_PORT = int(os.environ.get("SERVE_PORT", "5001"))
METRICS_PORT = int(os.environ.get("METRICS_PORT", "9102"))
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "30"))
WORKERS = os.environ.get("SERVE_WORKERS", "2")
STARTUP_TIMEOUT = int(os.environ.get("STARTUP_TIMEOUT", "180"))

DEPLOYED_VERSION = Gauge("plotgenre_model_server_deployed_version",
                         "Registry version currently served")
UP = Gauge("plotgenre_model_server_up", "1 if the MLflow scoring server is healthy")
DEPLOYS = Counter("plotgenre_model_server_deployments", "Successful deployments")
FAILED = Counter("plotgenre_model_server_failed_deployments", "Failed deployments")
ROLLBACKS = Counter("plotgenre_model_server_rollbacks", "Automatic rollbacks")


class Supervisor:
    """Keeps exactly one ``mlflow models serve`` process running the champion."""

    def __init__(self) -> None:
        self.client = MlflowClient()
        self.proc: Optional[subprocess.Popen] = None
        self.version: Optional[str] = None

    def champion_version(self) -> Optional[str]:
        """Version currently holding the alias, or None if not yet registered."""
        try:
            return self.client.get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS).version
        except MlflowException as exc:
            log.warning("no '%s' alias for %s yet (%s)", MODEL_ALIAS, MODEL_NAME,
                        str(exc).splitlines()[0])
        except Exception as exc:  # noqa: BLE001 - registry may be starting up
            log.warning("registry unreachable: %s", exc)
        return None

    def _healthy(self) -> bool:
        try:
            return httpx.get(f"http://127.0.0.1:{SERVE_PORT}/ping", timeout=2).status_code == 200
        except httpx.HTTPError:
            return False

    def _start(self, version: str) -> bool:
        uri = f"models:/{MODEL_NAME}/{version}"
        log.info("deploying %s", uri)
        self.proc = subprocess.Popen(  # noqa: S603 - fixed command, no shell
            ["mlflow", "models", "serve", "-m", uri, "--env-manager", "local",
             "-h", "0.0.0.0", "-p", str(SERVE_PORT), "-w", WORKERS],
            stdout=sys.stdout, stderr=sys.stderr,
            start_new_session=True)  # own process group so workers are stopped too
        deadline = time.time() + STARTUP_TIMEOUT
        while time.time() < deadline:
            if self.proc.poll() is not None:
                log.error("scoring server for version %s exited early", version)
                return False
            if self._healthy():
                return True
            time.sleep(2)
        log.error("scoring server for version %s not healthy after %ss", version,
                  STARTUP_TIMEOUT)
        return False

    def _stop(self) -> None:
        """Stop the scoring server and all its worker processes, then free the port."""
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.proc = None
        UP.set(0)
        deadline = time.time() + 15
        while self._healthy() and time.time() < deadline:  # old workers still draining
            time.sleep(0.5)

    def deploy(self, version: str) -> None:
        """Switch to ``version``; on failure roll back to the previous one."""
        previous = self.version
        self._stop()
        if self._start(version):
            self.version = version
            DEPLOYED_VERSION.set(float(version))
            DEPLOYS.inc()
            UP.set(1)
            log.info("version %s is live", version)
            return
        FAILED.inc()
        self._stop()
        if previous:
            log.warning("rolling back to version %s", previous)
            ROLLBACKS.inc()
            if self._start(previous):
                self.version = previous
                UP.set(1)
                return
        self.version = None

    def run(self) -> None:
        """Main loop."""
        failed_version = None
        while True:
            target = self.champion_version()
            if target and target != self.version and target != failed_version:
                self.deploy(target)
                failed_version = None if self.version == target else target
            elif self.proc is not None and self.proc.poll() is not None:
                log.error("scoring server crashed; restarting version %s", self.version)
                UP.set(0)
                if self.version:
                    self.deploy(self.version)
            else:
                UP.set(1 if self._healthy() else 0)
            time.sleep(POLL_SECONDS)


def main() -> None:
    """Start metrics endpoint and the supervisor loop."""
    start_http_server(METRICS_PORT)
    sup = Supervisor()

    def _shutdown(*_):
        sup._stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    sup.run()


if __name__ == "__main__":
    main()
