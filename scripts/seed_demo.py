#!/usr/bin/env python3
"""Fill a LOCAL backend with a synthetic week of drinks and a goal for recording the demo.

Synthetic data only: say so in any video. Stable idempotency keys make reruns
add nothing new. Refuses non-loopback backends; reads HYDRA_API_TOKEN from the
environment and never prints it.
"""
import argparse
from datetime import datetime, time, timedelta
import json
import os
from urllib.parse import urlparse
import urllib.request
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

# (days ago, local time, category, mL). Today keeps a little room under the goal.
PLAN = (
    (6, "08:10", "water", 400), (6, "13:00", "coffee", 250), (6, "19:30", "water", 500),
    (5, "07:45", "water", 300), (5, "12:15", "tea", 300), (5, "18:00", "sports drink", 500),
    (4, "09:00", "coffee", 250), (4, "15:30", "water", 600),
    (2, "08:30", "water", 350), (2, "12:45", "milk", 250), (2, "17:10", "water", 750), (2, "21:00", "tea", 200),
    (1, "07:50", "coffee", 250), (1, "11:30", "water", 500), (1, "16:20", "juice", 200),
    (0, "07:30", "water", 350), (0, "09:15", "coffee", 250),
)
GOAL_ML = 2000


def entries(now: datetime, zone: ZoneInfo) -> list[tuple[str, dict]]:
    today = now.astimezone(zone).date()
    result = []
    for days_ago, clock, category, milliliters in PLAN:
        local = datetime.combine(today - timedelta(days=days_ago), time.fromisoformat(clock), tzinfo=zone)
        if local > now:
            continue  # never create a future-dated log
        key = str(uuid5(NAMESPACE_URL, f"hydra-demo-seed/{local.date()}/{clock}/{category}"))
        result.append((key, {"category": category, "consumed_ml": milliliters, "timezone": zone.key,
                             "consumed_at": local.isoformat(timespec="seconds"), "source": "manual"}))
    return result


def seed(send, now: datetime, zone: ZoneInfo) -> dict:
    """`send(method, path, body, headers) -> status` performs one authenticated request."""
    created = replayed = 0
    for key, body in entries(now, zone):
        status = send("POST", "/v1/beverages", body, {"Idempotency-Key": key})
        if status == 201:
            created += 1
        elif status == 200:
            replayed += 1
        else:
            raise RuntimeError(f"seed request refused with HTTP {status}")
    if send("PUT", "/v1/settings", {"daily_beverage_goal_ml": GOAL_ML}, {}) != 200:
        raise RuntimeError("goal could not be saved")
    return {"created": created, "already_present": replayed, "goal_ml": GOAL_ML, "synthetic": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--timezone", default=os.environ.get("TZ", "UTC"),
                        help="IANA timezone of the phone used for the demo, e.g. Europe/Paris")
    args = parser.parse_args()
    url = urlparse(args.backend)
    if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1") or url.path not in ("", "/"):
        parser.error("Seeding is restricted to a loopback development backend.")
    token = os.environ.get("HYDRA_API_TOKEN", "")
    if len(token) < 32:
        parser.error("Set HYDRA_API_TOKEN to the local development credential.")
    zone = ZoneInfo(args.timezone)

    def send(method, path, body, headers):
        request = urllib.request.Request(args.backend.rstrip("/") + path, method=method, data=json.dumps(body).encode(),
                                         headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    print(json.dumps(seed(send, datetime.now(zone), zone)))


if __name__ == "__main__":
    main()
