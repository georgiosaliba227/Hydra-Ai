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

Use a persistent `HYDRA_DATABASE_PATH` and the same token after restarting. SQLite schema initializes automatically. A missing/short token or contradictory mode/billable flags reject startup. Keep mock/false for this demonstration; guarded live mode requires separately reviewed account, price, permit, consent and budget evidence. `GET /health` is public; beverage/history/summary routes require Bearer authentication. The only identity is `local-demo`: this is a single-user development prototype, not a multi-user identity system. No public hosting is configured. SQLite stores confirmed logs on the backend host and is not encrypted by the app; use synthetic demo data and OS disk protection. Back up the database if needed; no silent purge/migration is performed.

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

This demonstrates logged volume accounting and descriptive history. The dashboard's previous-seven-days range describes logged intake only; missing days are unknown, and daily requirements remain unavailable. No Meta request or HealthKit export is needed.

## Automated verification

From repository root:
```sh
python -m pytest tests -q
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

## Muse Wonder hydration intelligence

Muse Wonder 1.0 is the only hydration-intelligence model; camera recognition
stays on Muse Spark 1.3. The Workout forecast screen has a "Muse Wonder ·
recorded live result" section. It replays a saved real Wonder result through
`POST /v2/hydration-context-comparison` with `mode: "recorded"`, which never
sends a Meta request.

To serve a recording, start the backend with `HYDRA_WONDER_RESULTS_DIR` set to an
absolute, owned directory with mode 0700 that holds `complete.json`. Without it
the section shows "No recorded Muse Wonder result is available yet."

Creating a recording is billable and gated; follow the operator procedure in
[WONDER_HYDRATION_API.md](architecture/WONDER_HYDRATION_API.md): finality
migration, `wonder_admin.py migrate-schema`, allocation and case import, then one
`run-case --confirm-billable` on Georgio's account after invoice finality for
every earlier request. No recording exists yet.

## Offline mock rehearsal

From the maintained backend environment, run:

```sh
python scripts/rehearse_demo.py
```

This one-shot command creates a temporary synthetic beverage database and an in-process backend, clears inherited provider configuration, and blocks network/provider/financial-ledger operations. It never reads the permanent financial ledger. It checks authentication, a 250 mL manual log and idempotent replay, known/unknown/ambiguous/refused mock photo paths, separate 150 mL confirmation, persistence across app recreation, descriptive seven-day history, unknown water composition and the documented 645–755 mL conditional exercise-loss arithmetic. The synthetic illustration is a structural mock JPEG, not a real-image recognition test. Results print compact JSON without tokens, photos or raw calibration inputs; the temporary database is removed. This verifies software behavior, not scientific future coverage.

## Demonstration narrative for review

1. Show Today and explicitly identify the connected **mock** backend. Log a consumed 250 mL beverage; explain that all beverage volume counts while unsourced physical water content stays unknown.
2. Open Camera, select an owned nonsensitive image, inspect the prepared JPEG export option and consent only to the local mock backend. Analyze and show the mock-source label; correct identity and consumed quantity before confirming. Never present mock results as real Meta inference.
3. Refresh Today/History, relaunch, and verify persistence. Show previous-seven-days descriptive totals, missing days and unavailable daily requirements. The native screen does not request raw calibration data or HealthKit records.
4. Run the offline rehearsal to show the separately tested conditional workout-loss interval. State its assumptions and that it is not a drinking target, deficit, diagnosis or validated prediction. Native workout-entry UI is not implemented.
5. Show the fail-closed budget policy and explain the pending account/provider/consent gates. Preserve the real ledger and mock/false settings. Do not switch live modes for a recording.

The script is a proposed rehearsal sequence, not a recorded final demo or verified submission. Physical camera/share destinations, HealthKit permissions, participant eligibility, portal-specific video requirements and truthful real Meta use remain separate human gates in PROJECT_STATUS.md and BLOCKERS.md.
