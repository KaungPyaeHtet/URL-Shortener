"""
Load test: 50 concurrent users (Locust "users" = concurrent VUs).

Run (Flask must be up: uv run run.py):
  uv run locust -f loadtests/locustfile.py --host http://127.0.0.1:5000 \\
    --users 50 --spawn-rate 50 --run-time 60s --headless

Spawn rate 50 brings all users up immediately = "same second" crowd.
"""

from locust import HttpUser, between, task


class BaselineUser(HttpUser):
    wait_time = between(0.1, 0.4)

    @task(3)
    def health(self):
        self.client.get("/health", name="GET /health")

    @task(1)
    def index(self):
        self.client.get("/", name="GET /")
