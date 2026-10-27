# Local end-to-end prototype

## Backend

Use Python 3.10+ with IANA timezone data; current verification uses Python 3.14. Run from repository root, **not** the preserved nested starter:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m pip install pytest httpx
```

Create an ignored local `.env` from `.env.example`. Generate a random development token with `python -c 'import secrets; print(secrets.token_urlsafe(32))'` and enter it as `HYDRA_API_TOKEN` in that local file. Do not commit/share this credential in issues or logs. It is a local backend credential, never a Meta provider key.

```sh
set -a
source .env
set +a
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Use a persistent `HYDRA_DATABASE_PATH` and the same token after restarting. SQLite schema initializes automatically. A missing/short token or non-mock AI setting rejects startup. `GET /health` is public; beverage/history/summary routes require Bearer authentication. The only identity is `local-demo`: this is a single-user development prototype, not a multi-user identity system. No public hosting is configured. SQLite stores confirmed logs on the backend host and is not encrypted by the app; use synthetic demo data and OS disk protection. Back up the database if needed; no silent purge/migration is performed.

## iOS

Open `ios/HydraAI.xcodeproj`, select the HydraAI scheme and an available iPhone simulator. Configure the backend URL and local development credential in the app's connection settings. The credential stays in Keychain. Use `http://127.0.0.1:8000` for the simulator; a physical iPhone's loopback is the phone itself. Physical-device use needs a reachable private development address, local-network permission, signing and an explicitly trusted network; use HTTPS outside local development. Never put a Meta key in the app.

The app retains a pending request and its UUID idempotency key before sending. If a connection fails, retry the pending request instead of creating a new one. The server returns the original record for an identical replay and rejects reuse with different data. Explicit offline mock mode, if selected, is separate from server history and never silently substitutes for a failed backend. Existing mock records are not automatically uploaded.

## Demonstration

1. Start the backend with an empty **test** database, then open the iPhone simulator app.
2. Configure the server, refresh Today and verify connected state.
3. Log a beverage with the actual consumed amount, for example 250 mL coffee.
4. Verify Today and History show the saved entry; daily beverage volume rises by 250 mL. Water content remains unknown, not an invented coffee multiplier.
5. Terminate and relaunch the app; refresh from the backend and verify the same entry remains.
6. Restart the backend using the same database path; verify the same history and total.
7. Stop the backend, try a new log, and verify an actionable error/pending state. Restart and retry; verify exactly one entry.

This demonstrates logged volume accounting, not personalized requirement forecasting, photo inference or HealthKit-based targets. No Meta network request is needed.

## Automated verification

From repository root:
```sh
python -m pytest tests/hydration tests/database tests/backend -q
xcodebuild -project ios/HydraAI.xcodeproj -scheme HydraAI \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro,OS=26.5' \
  -derivedDataPath /tmp/hydra-prototype-derived CODE_SIGN_IDENTITY=- CODE_SIGNING_ALLOWED=YES test
```
Run preserved starter tests separately from `Hydra-Ai-Starter/` to avoid its `ai` package name collision. No scientific validation or physical-device verification is implied by passing tests. See the integration report for actually executed build/runtime checks and limitations.

Use ad-hoc signing for simulator builds (`CODE_SIGN_IDENTITY=- CODE_SIGNING_ALLOWED=YES`); unsigned builds can launch but cannot save Keychain credentials. Debug defines DEBUG for runtime test configuration; Release does not include those overrides.

### Opt-in real backend UI test

Start a separate synthetic-data backend first. With its `HYDRA_API_TOKEN` in the environment, run:

```sh
HYDRA_E2E_BACKEND_URL=http://127.0.0.1:8000 python scripts/run_ios_e2e.py
```

Use `--destination 'platform=iOS Simulator,id=YOUR-SIMULATOR-UUID'` to select another installed simulator. This test writes a 125 mL beverage to the configured test database, saves the local connection in the simulator's Keychain, and relaunches without injected credentials to verify the persisted total. It is not a read-only test: use a dedicated simulator and synthetic database. Generated private test configuration is mode 0600 and removed after execution; test result bundles remain local and may contain test configuration, so never publish them without review. The ordinary unit scheme is `HydraAI`; the opt-in UI scheme is `HydraAIEndToEnd` and skips when its required runtime test environment is absent.
