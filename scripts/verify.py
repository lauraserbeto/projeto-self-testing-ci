import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ARTIFACTS.mkdir(exist_ok=True)
    commands = [
        ("lint", ["-m", "ruff", "check", "src", "tests", "scripts"]),
        ("format", ["-m", "ruff", "format", "--check", "src", "tests", "scripts"]),
        (
            "tests",
            [
                "-m",
                "pytest",
                "tests/unit",
                "tests/integration",
                "tests/e2e",
                "--cov=src",
                "--cov-branch",
                "--cov-report=term-missing",
                "--cov-report=json:artifacts/coverage.json",
                "--cov-report=xml:artifacts/coverage.xml",
                "--cov-report=html:artifacts/coverage_html",
                "--junitxml=artifacts/tests.xml",
            ],
        ),
        ("coverage-gate", ["scripts/check_coverage.py", "artifacts/coverage.json"]),
    ]
    for name, arguments in commands:
        result = subprocess.run(
            [sys.executable, *arguments],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONUTF8="1"),
        )
        (ARTIFACTS / f"{name}.log").write_bytes(result.stdout)
        print(result.stdout.decode("utf-8", errors="replace"), flush=True)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
