"""Run the test-suite and write docs/test_report.md (counts, per-test results,
acceptance criteria check against reports/metrics.json).

Usage:
    python scripts/generate_test_report.py                # unit + integration
    E2E_FRONTEND_URL=http://localhost:8080 E2E_GATEWAY_URL=http://localhost:8000 \
    E2E_API_KEY=... python scripts/generate_test_report.py --e2e
"""

import argparse
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "reports" / "junit.xml"


def run(markers: str) -> int:
    JUNIT.parent.mkdir(exist_ok=True)
    cmd = [sys.executable, "-m", "pytest", "-m", markers, f"--junitxml={JUNIT}", "-q",
           "-p", "no:cacheprovider", "--cov", "--cov-report=term-missing:skip-covered",
           "--cov-report=xml:reports/coverage.xml"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    (ROOT / "reports" / "pytest_output.txt").write_text(proc.stdout + proc.stderr)
    return proc.returncode


def coverage_total() -> str:
    try:
        root = ET.parse(ROOT / "reports" / "coverage.xml").getroot()
        return f"{float(root.get('line-rate', 0)) * 100:.1f}%"
    except (OSError, ET.ParseError):
        return "n/a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--e2e", action="store_true", help="also run end-to-end tests")
    args = ap.parse_args()
    markers = "unit or integration or e2e" if args.e2e else "unit or integration"
    code = run(markers)
    suite = ET.parse(JUNIT).getroot()
    suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
    rows, counts = [], {"passed": 0, "failed": 0, "skipped": 0}
    for case in suite.iter("testcase"):
        status = "passed"
        if case.find("failure") is not None or case.find("error") is not None:
            status = "failed"
        elif case.find("skipped") is not None:
            status = "skipped"
        counts[status] += 1
        level = case.get("classname", "").split(".")[1] if "." in case.get("classname", "") else ""
        rows.append((level, case.get("classname", "").split(".")[-1], case.get("name"),
                     status, float(case.get("time", 0))))
    metrics_path = ROOT / "reports" / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    total = sum(counts.values())
    lines = [
        "# Test report",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} on {platform.platform()} "
        f"(Python {platform.python_version()}) by `scripts/generate_test_report.py`.",
        "",
        "## Summary",
        "",
        "| Total | Passed | Failed | Skipped | Line coverage |",
        "|---|---|---|---|---|",
        f"| {total} | {counts['passed']} | {counts['failed']} | {counts['skipped']} | "
        f"{coverage_total()} |",
        "",
        "## Acceptance criteria (see docs/test_plan.md)",
        "",
        "| Criterion | Target | Measured | Result |",
        "|---|---|---|---|",
    ]
    if metrics:
        f1, p95 = metrics.get("test_micro_f1"), metrics.get("latency_p95_ms")
        lines += [
            f"| AC-1 Test micro-F1 | >= 0.40 | {f1:.4f} | {'PASS' if f1 >= 0.40 else 'FAIL'} |",
            f"| AC-2 p95 single-prediction latency (model) | < 500 ms | {p95:.1f} ms | "
            f"{'PASS' if p95 < 500 else 'FAIL'} |",
        ]
    lines += [f"| AC-3 All planned test cases pass | 0 failures | {counts['failed']} failures | "
              f"{'PASS' if counts['failed'] == 0 else 'FAIL'} |", ""]
    lines += ["## Test cases", "", "| Level | Module | Test | Result | Time (s) |",
              "|---|---|---|---|---|"]
    lines += [f"| {lv} | {mod} | `{name}` | {st} | {t:.2f} |" for lv, mod, name, st, t in rows]
    out = ROOT / "docs" / "test_report.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"{total} tests: {counts} -> {out}")
    return code


if __name__ == "__main__":
    sys.exit(main())
