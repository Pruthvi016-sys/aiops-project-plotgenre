#!/usr/bin/env bash
# One-time local setup on Ubuntu.
#   bash scripts/setup.sh            # secrets + folders + Git LFS + Python virtualenv (.venv)
#   bash scripts/setup.sh --no-venv  # only what Docker Compose needs (no Python on the host)
set -euo pipefail
cd "$(dirname "$0")/.."

WITH_VENV=1
[ "${1:-}" = "--no-venv" ] && WITH_VENV=0

# ---------------------------------------------------------------- secrets (.env is git-ignored)
if [ ! -f .env ]; then
  API_KEY=$(openssl rand -hex 24)
  # Fernet key = URL-safe base64 of 32 random bytes
  MODEL_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
  sed -e "s|^API_KEY=.*|API_KEY=${API_KEY}|" \
      -e "s|^PLOTGENRE_MODEL_KEY=.*|PLOTGENRE_MODEL_KEY=${MODEL_KEY}|" \
      -e "s|^UID=.*|UID=$(id -u)|" -e "s|^GID=.*|GID=$(id -g)|" .env.example > .env
  chmod 600 .env
  echo "created .env with a fresh API key and model encryption key (keep it private)"
else
  echo ".env already exists - keeping your keys"
fi
mkdir -p .secrets
grep '^API_KEY=' .env | cut -d= -f2- > .secrets/api_key
chmod 644 .secrets/api_key   # read by the alertmanager container

# ---------------------------------------------------------------- folders
mkdir -p ../plotgenre-dvc-storage reports logs models   # DVC local remote lives next to the repo

# ---------------------------------------------------------------- Git LFS
if command -v git-lfs >/dev/null 2>&1; then
  git lfs install >/dev/null && echo "git lfs ready"
else
  echo "WARNING: git-lfs not installed -> sudo apt install git-lfs && git lfs install"
fi

# ---------------------------------------------------------------- Python virtualenv (optional)
if [ "$WITH_VENV" = 1 ]; then
  PY=${PYTHON:-python3.12}
  command -v "$PY" >/dev/null 2>&1 || PY=python3
  if [ ! -d .venv ]; then
    "$PY" -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --upgrade pip wheel
  pip install -r requirements-dev.txt
  pip install -e .
  echo "virtualenv ready: source .venv/bin/activate"
fi
echo "setup complete"
