"""Send traffic to the gateway to exercise monitoring and drift detection.

Modes:
  normal  - plots of pre-2000 films (same distribution as training)
  newer   - plots of films from 2000 onwards (mild temporal drift)
  ood     - out-of-domain text (product reviews / news style) -> strong live drift,
            fires the PlotGenreLiveInputDrift alert -> Alertmanager -> retraining

Example: python scripts/simulate_traffic.py --mode ood --n 300
"""

import argparse
import os
import random
import sys
import time

import httpx
import pandas as pd

OOD = [
    "The battery lasts two days and the screen is bright but the charger broke in a week",
    "Quarterly revenue grew eight percent while margins narrowed due to logistics costs",
    "Preheat the oven, whisk the eggs with sugar, fold in the flour and bake for an hour",
    "The committee approved the budget amendment after a debate about road maintenance",
    "Customer support answered quickly and replaced the faulty headphones for free",
    "Rainfall this season was below average and farmers expect a smaller wheat harvest",
]


def texts_for(mode: str, n: int) -> list:
    if mode == "ood":
        rnd = random.Random(0)
        return [" ".join(rnd.sample(OOD, 3)) for _ in range(n)]
    path = "data/processed/movies.parquet"
    if not os.path.exists(path):  # pipeline not run yet -> small Git LFS sample
        path = "data/sample/movies_sample.parquet"
    df = pd.read_parquet(path)
    df = df[df["year"] >= 2000] if mode == "newer" else df[df["year"] < 2000]
    texts = df.sample(min(n, len(df)), random_state=1)["text"].str.slice(0, 3000).tolist()
    return (texts * (n // max(len(texts), 1) + 1))[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["normal", "newer", "ood"], default="normal")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--url", default=os.environ.get("GATEWAY_URL", "http://localhost:8000"))
    ap.add_argument("--rps", type=float, default=10.0, help="requests per second")
    args = ap.parse_args()
    key = os.environ.get("API_KEY")
    if not key and os.path.exists(".env"):
        key = next((ln.split("=", 1)[1].strip() for ln in open(".env")
                    if ln.startswith("API_KEY=")), None)
    ok = fail = 0
    lat = []
    with httpx.Client(base_url=args.url, headers={"X-API-Key": key or ""}, timeout=30) as c:
        for text in texts_for(args.mode, args.n):
            t0 = time.perf_counter()
            r = c.post("/api/v1/predict", json={"text": text, "explain": False})
            lat.append((time.perf_counter() - t0) * 1000)
            ok, fail = (ok + 1, fail) if r.status_code == 200 else (ok, fail + 1)
            time.sleep(max(0.0, 1 / args.rps - lat[-1] / 1000))
        drift = c.get("/api/v1/monitoring/drift").json()
    lat.sort()
    print(f"sent {ok + fail} ({ok} ok, {fail} failed); p50 {lat[len(lat)//2]:.0f} ms, "
          f"p95 {lat[int(len(lat)*0.95)-1]:.0f} ms")
    print(f"live drift: {drift}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
