"""Locust load/stress test suite for the Strata backend API.

Targets read-only endpoints only — no LLM calls (cost) and no data mutation,
so the suite is safe to run against any environment, including CI.

Local usage (interactive UI):
    locust -f loadtest/locustfile.py --host http://localhost:8000

Headless (as run in .github/workflows/load-test.yml):
    locust -f loadtest/locustfile.py --host http://localhost:8000 \
        --headless -u 20 -r 5 -t 2m --html report.html --csv results
"""

from locust import HttpUser, between, task


class BrowseUser(HttpUser):
    """Simulates a analyst browsing reference data — the dominant read path."""

    wait_time = between(0.1, 0.5)

    @task(5)
    def health(self) -> None:
        self.client.get("/api/health")

    @task(3)
    def sectors(self) -> None:
        self.client.get("/api/sectors")

    @task(3)
    def geographies(self) -> None:
        self.client.get("/api/geographies")

    @task(1)
    def llm_providers(self) -> None:
        self.client.get("/api/llm/providers")
