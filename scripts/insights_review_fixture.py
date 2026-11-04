#!/usr/bin/env python3
"""Nonbillable UI fixture: synthetic trends with a fake available capability.

Run with the existing backend test environment. All trend POSTs are counted and
rejected here, before reaching any provider code. No ledger or credential from
another backend is read. The disposable database is always created by this script.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import uvicorn

from backend.app import create_app
from backend.wonder_trends import build_facts, trend_result


class ReviewFixture:
    def __init__(self, app, token: str, saved_example: bool = False, unavailable_demo: Path | None = None):
        self.app = app
        self.token = token
        self.send_attempts = 0
        self.saved_example = saved_example
        self.unavailable_demo = unavailable_demo

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        if path == "/v2/workout-forecasts" and self.unavailable_demo is not None:
            # Exercise the real server's missing-artifact response without touching repository artifacts.
            with patch("ai.forecasting.predict.ARTIFACT_DIR", self.unavailable_demo):
                return await self.app(scope, receive, send)
        if path in ("/__test__/trend-sends", "/v1/wonder/trends"):
            headers = dict(scope.get("headers", []))
            if headers.get(b"authorization") != ("Bearer " + self.token).encode():
                return await JSONResponse({"code": "unauthorized"}, status_code=401)(scope, receive, send)
        if path == "/__test__/trend-sends":
            return await JSONResponse({"count": self.send_attempts})(scope, receive, send)
        if path == "/v1/wonder/trends" and scope["method"] == "POST":
            self.send_attempts += 1
            return await JSONResponse({"code": "wonder_unavailable"}, status_code=503)(scope, receive, send)
        if path == "/health":
            return await JSONResponse({"status": "ok", "billable_requests_enabled": False,
                                       "test_provider": "fake-no-network-review"})(scope, receive, send)
        if path != "/v1/wonder/trends" or scope["method"] != "GET":
            return await self.app(scope, receive, send)
        messages = []
        async def capture(message):
            messages.append(message)
        await self.app(scope, receive, capture)
        start = next(m for m in messages if m["type"] == "http.response.start")
        if start["status"] != 200:
            for message in messages:
                await send(message)
            return
        value = json.loads(b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body"))
        value.update(live_available=True, account_id="georgiosaliba227")
        if self.saved_example:
            through = date.fromisoformat(value["facts"]["through_date"]) - timedelta(days=1)
            zone = value["facts"]["timezone"]
            at = datetime.combine(through, time(12), tzinfo=ZoneInfo(zone))
            facts = build_facts([{"category": "water", "consumed_ml": 500, "consumed_at": at.isoformat()}], None, zone, through)
            explanation = {"summary": "You logged 500 mL over the last 7 days.", "summary_template": "Fixture summary.",
                "insights": [
                    {"id": "logging_consistency", "template": "Fixture insight.", "text": "You logged drinks on 1 of the last 7 days. Days without logs remain unknown."},
                    {"id": "beverage_mix", "template": "Fixture insight.", "text": "Water is the only drink type in this sample log."},
                    {"id": "timing", "template": "Fixture insight.", "text": "Your sample drink was logged at midday."}]}
            value["latest"] = trend_result(facts, explanation, account="georgiosaliba227", attempt_id=str(uuid4()),
                generated_at=datetime.now(timezone.utc).isoformat(), observations={"latency_ms": 0, "input_tokens": 0,
                "output_tokens": 0, "usage_derived_cost_micro_usd": 0, "billed_cost_usd": None})
        await JSONResponse(value)(scope, receive, send)


def make_fixture(database: Path, token: str, saved_example: bool = False, unavailable_demo: bool = False) -> ReviewFixture:
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith(("HYDRA_", "META_")) and k != "MODEL_API_KEY"}
    clean_env.update(HYDRA_AI_MODE="mock", META_BILLABLE_REQUESTS_ENABLED="false",
                     HYDRA_META_HYDRATION_ENABLED="false", HYDRA_WONDER_LIVE="false",
                     HYDRA_META_LEDGER_PATH=str(database.parent / "unused.sqlite3"))
    with patch.dict(os.environ, clean_env, clear=True):
        app = create_app(api_token=token, db_path=database)
    with TestClient(app) as client:
        response = client.post("/v1/beverages", headers={"Authorization": "Bearer " + token,
            "Idempotency-Key": str(uuid4())}, json={"category": "water", "consumed_ml": 500,
            "source": "manual", "timezone": "UTC", "consumed_at": datetime.now(timezone.utc).isoformat()})
        response.raise_for_status()
    return ReviewFixture(app, token, saved_example, database.parent / "absent-demo-artifacts" if unavailable_demo else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", required=True, type=Path, help="Private JSON file containing a generated local test token")
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--saved-example", action="store_true", help="Include a fabricated saved result for the previous date window")
    parser.add_argument("--unavailable-demo", action="store_true", help="Exercise the server's missing demo artifact response")
    args = parser.parse_args()
    token = json.loads(args.token_file.read_text())["token"]
    with tempfile.TemporaryDirectory(prefix="hydra-review-fixture-") as directory:
        app = make_fixture(Path(directory) / "synthetic.sqlite3", token, args.saved_example, args.unavailable_demo)
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
