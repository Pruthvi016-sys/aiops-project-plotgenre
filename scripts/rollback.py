"""Roll the deployed model back (or forward) by moving the ``champion`` alias.

The model-server supervisor notices the alias change within POLL_SECONDS and
redeploys that version - no container restart needed.

Examples:
    python scripts/rollback.py --list
    python scripts/rollback.py                 # back to the 'previous' alias
    python scripts/rollback.py --version 3     # to a specific registry version
"""

import argparse
import os
import sys

from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

NAME = os.environ.get("MODEL_NAME", "plotgenre-classifier")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", help="registry version to make champion")
    parser.add_argument("--list", action="store_true", help="list versions and exit")
    args = parser.parse_args()
    os.environ.setdefault("MLFLOW_TRACKING_URI", "http://localhost:5000")
    client = MlflowClient()
    try:
        versions = [client.get_model_version(NAME, v.version)
                    for v in client.search_model_versions(f"name='{NAME}'")]
    except MlflowException as exc:
        print(f"cannot reach the registry: {exc}", file=sys.stderr)
        return 1
    if args.list or not versions:
        for v in sorted(versions, key=lambda v: int(v.version)):
            print(f"v{v.version:>3}  aliases={list(v.aliases)}  "
                  f"test_micro_f1={v.tags.get('test_micro_f1', '?')}  "
                  f"decision={v.tags.get('promotion_decision', '?')}")
        return 0
    try:
        current = client.get_model_version_by_alias(NAME, "champion").version
    except MlflowException:
        current = None
    target = args.version
    if not target:
        try:
            target = client.get_model_version_by_alias(NAME, "previous").version
        except MlflowException:
            print("no 'previous' alias recorded; pass --version", file=sys.stderr)
            return 1
    client.set_registered_model_alias(NAME, "champion", target)
    if current and current != target:
        client.set_registered_model_alias(NAME, "previous", current)
    print(f"champion: v{current} -> v{target} (model server redeploys automatically)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
