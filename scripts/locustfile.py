import json
from pathlib import Path
from uuid import uuid4

from gevent.event import Event
from locust import HttpUser, constant, events, task

ready = Event()
started = 0
active = 0
peak = 0


class WalletUser(HttpUser):
    wait_time = constant(0)

    def on_start(self):
        global started
        self.accounts = []
        for balance in (10**9, 0):
            response = self.client.post(
                "/accounts",
                json={
                    "name": "Carga",
                    "document": str(uuid4()),
                    "initial_balance_cents": balance,
                },
                name="setup /accounts",
            )
            response.raise_for_status()
            self.accounts.append(response.json()["id"])
        started += 1
        if started == 50:
            ready.set()

    @task
    def transfer(self):
        global active, peak
        ready.wait(timeout=30)
        active += 1
        peak = max(peak, active)
        try:
            with self.client.post(
                "/transfers",
                json={
                    "source": self.accounts[0],
                    "target": self.accounts[1],
                    "amount_cents": 1,
                },
                headers={"Idempotency-Key": str(uuid4())},
                name="POST /transfers",
                catch_response=True,
            ) as response:
                if response.status_code != 201:
                    response.failure(f"HTTP {response.status_code}")
        finally:
            active -= 1


@events.quitting.add_listener
def record_results(environment, **kwargs):
    stat = environment.stats.get("POST /transfers", "POST")
    result = {
        "users": started,
        "peak_in_flight_transfers": peak,
        "requests": stat.num_requests,
        "failures": stat.num_failures,
        "error_rate": stat.fail_ratio,
        "mean_latency_ms": stat.avg_response_time,
        "p95_latency_ms": stat.get_response_time_percentile(0.95),
    }
    Path("artifacts/load-summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if started < 50 or peak < 50 or stat.num_requests == 0 or stat.num_failures:
        environment.process_exit_code = 1
