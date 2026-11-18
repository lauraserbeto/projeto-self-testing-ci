import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    Path("artifacts").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
        gateway_port, api_port = free_port(), free_port()
        env = dict(
            os.environ,
            PYTHONUTF8="1",
            DATABASE_PATH=str(Path(temporary) / "load.db"),
            ANTIFRAUD_URL=f"http://127.0.0.1:{gateway_port}/check",
        )
        for name, app, port in (
            ("gateway", "scripts.fake_gateway:app", gateway_port),
            ("api", "src.main:app", api_port),
        ):
            log = stack.enter_context(open(f"artifacts/load-{name}.log", "wb"))
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    app,
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            stack.callback(process.wait, timeout=10)
            stack.callback(process.terminate)
            deadline = time.monotonic() + 20
            while True:
                try:
                    with urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=1):
                        break
                except (URLError, TimeoutError):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"{name} não iniciou") from None
                    time.sleep(0.1)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "locust",
                "-f",
                "scripts/locustfile.py",
                "--headless",
                "--users",
                "50",
                "--spawn-rate",
                "50",
                "--run-time",
                "20s",
                "--stop-timeout",
                "10",
                "--host",
                f"http://127.0.0.1:{api_port}",
                "--csv",
                "artifacts/load",
                "--csv-full-history",
                "--only-summary",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        Path("artifacts/load.log").write_bytes(result.stdout)
        print(result.stdout.decode("utf-8", errors="replace"))
        return result.returncode


if __name__ == "__main__":
    sys.exit(main())
