# Run the trained camera adapter with Hydra

This is a local development mode. The Meta Muse Glimmer base and selected LoRA run on the owner's Mac; the iPhone sends its prepared JPEG to that Mac after photo consent. Keep the Mac awake and both devices on a network that permits device-to-device traffic. Hosted Spark requests, credentials and budget records are not used by this mode.

## Mac setup

Build the existing native runner using `ai/beverage_training/MetaAdapter/README.md`. The current local camera profile pins the measured executable SHA, base provenance, encoder configuration and selected adapter SHA `71a361e862c5e1399b25098601fd7d974253a5f5d285e9ad194f90e38028d48f`. A different build must receive a reviewed profile update; do not disable fingerprint checks.

Compile the local label reader:

```sh
xcrun swiftc -O scripts/local_label_ocr.swift -o /private/tmp/hydra-local-label-ocr
```

Create a private JSON runtime configuration with these absolute paths, outside Git:

```json
{
  "binary": "/absolute/path/to/pinned/meta-beverage",
  "model": "/absolute/path/to/Muse-Glimmer-30B-4bit",
  "adapter": "/absolute/path/to/adapter-train-v2-1024-e1-001",
  "encoder": "/absolute/path/to/selected/encoder-config.json",
  "ocr": "/private/tmp/hydra-local-label-ocr",
  "work_root": "/absolute/private/path/to/runtime"
}
```

Use the existing owner backend session token and separate beverage database. Configure `HYDRA_AI_MODE=local_meta`, `HYDRA_LOCAL_META_CONFIG` to that JSON, `META_BILLABLE_REQUESTS_ENABLED=false`, `HYDRA_META_HYDRATION_ENABLED=false`, `HYDRA_WONDER_LIVE=false`. No Meta API key is needed. Keep the financial ledger path unchanged. Start `backend.main:app` with Uvicorn on the Mac's current LAN address, with access logging disabled. Startup checks all base-weight bytes and can take tens of seconds. `/v1/recognition-capabilities` must report `local_meta` and `muse-glimmer-30b-beverage-lora-v1`; `/health` must report billable requests disabled.

## iPhone test

For the combined hydration branch only, an operator can explicitly set
`HYDRA_LOCAL_META_ALLOW_WONDER=true` alongside `HYDRA_WONDER_LIVE=true`,
`META_BILLABLE_REQUESTS_ENABLED=true` and legacy hydration disabled. This permits
the independently guarded Wonder routes to coexist with the local camera;
comprehensive dispatch retains its own flag. It changes no budget, account,
freshness, exact-preview or consent requirement. Camera photos still select only
the local recognizer, with no hosted fallback. Default local-only configuration
above remains unchanged. Keep the existing saved backend URL/token and beverage
store when combining builds; a second backend database is not silently merged.

Install the updated signed Hydra build through USB or a previously paired, reachable wireless Xcode connection. An old build does not accept `local_meta`; do not disguise it as hosted Spark or mock mode.

1. In Settings, use `http://<Mac-LAN-IP>:8771`, preserve the owner backend token, and save the connection.
2. Open Camera and tap **Refresh analysis mode**. The screen should mention the trained Meta model on your Mac.
3. Choose or take a photo with the drink name and printed metric size visible. Enable backend-photo consent and tap **Analyze with trained Meta** once.
4. Keep Hydra open while the Mac processes the image. The end-to-end local example took about 50 seconds; the server stops a request after 180 seconds and the client allows 210 seconds. A failed attempt is never automatically repeated.
5. Review the name and **Printed size**. A readable size must agree between the adapter and local label reading. Unknown or conflicting size stays unknown. Metric declarations are used exactly; ambiguous fluid-ounce-only labels remain unknown in this integration.
6. **Confirm logs the whole drink**, following the owner’s declared logging convention. A supported size/whole-drink quantity prefills the review. If size is unclear, enter only **Drink size**, directly on the review, in mL, litres or US fl oz. **Edit** changes name/type/size and optionally offers **Log a different amount**. The whole-drink default remains a user assumption, not a photo measurement. Personal memory remains separate from model output; shared training examples require their own default-off opt-in and remain staged locally.

Canceling the review creates no beverage. A confirmed log uses the existing hydration engine. It does not establish measured water content, nutrients, remaining liquid or actual consumption from a photo.

The 84% held-out benchmark measured the selected adapter's identity plus capacity. This connected pipeline adds conservative OCR corroboration and can return more unknown volumes; it does not inherit a measured 84% end-to-end app accuracy claim.

## Cable-ready handoff (November 3)

The verified development build from commit `130f9039b85376b3086f1abd60ea2f24bd784973` has a durable private staging copy on the owner's Mac, outside temporary build storage. Its signature is valid, its provisioning profile includes the owner's iPhone, and no owner backend token is embedded in the bundle. The private `device-ready-manifest.json` records its executable fingerprint and signing expiry. This build remains a rollback copy. The owner subsequently requested the finished-drink review described above; its updated signed build is recorded separately in the private manifest.

An owner-only helper is prepared at `~/Library/Application Support/HydraAI/private/local-adapter-camera-20261103/cable_test.py`. It contains no credentials. It reads the established private connection configuration, verifies the staged app and requires the existing owner phone. It never uninstalls Hydra or clears app data. It performs no image inference, automatic retries, logging of a drink, financial-ledger changes or hosted-provider calls.

Once the cable is connected, the operator runs:

```sh
/Users/georgiosaliba/Desktop/Hydra-Ai/.venv/bin/python \
  "$HOME/Library/Application Support/HydraAI/private/local-adapter-camera-20261103/cable_test.py" --install
```

The helper checks connectivity before changing anything. It detects the Mac's current Wi-Fi address, refreshes only its owned local-model backend when needed, confirms local mode with billing disabled, then updates and opens the app. It uses a launch-only URL override while leaving the existing owner token in iOS Keychain. On the phone, tap **Save connection** once in Settings to retain the home-network URL across future launches.

At home:

1. Connect the iPhone by USB-C, unlock it, and accept Trust if prompted. Developer Mode was already enabled; do not reset pairing or uninstall the app.
2. Keep Mac and phone on the same home Wi-Fi. USB installs the app; photos still reach the Mac backend through the configured network connection.
3. Run the helper, save the connection in Settings, and verify **Refresh analysis mode** shows the trained Meta model.
4. Take a new bottle photo with brand, variant and metric net size visible. Use backend-photo consent and run one local analysis. Verify recognition and exact label capacity; use **Cancel** for a test that should create no entry.
5. For the logging check, **Confirm** declares the whole drink finished. If its size is unknown, enter **Drink size** on the review. Verify Today/History, reopen the app and check persistence. **Edit** offers optional name/type/size correction or a different amount. Shared training remains separately opted in and off by default.

The verified simulator and local API remain the backup. Existing cases include a one-litre Dasani photo with 1000mL returned, BODYARMOR LYTE Dragonfruit Berry with unknown size when no metric declaration was read, and an iced-coffee photo whose cup text was proposed as an unverified brand. Do not fill unknown volumes from product memory or claim the physical-phone test is complete before it runs.

Physical verification subsequently completed recognition, Edit/Confirm and deterministic volume accounting on the owner's iPhone. The owner also confirmed the saved entry and trained-model connection survived a normal app restart. Confirm uses the whole-drink assumption without asking how much was drunk; a readable supported size can prefill it. If size remains unknown, the review exposes Drink size directly using explicit units. This remains a user assumption/correction rather than a model measurement. Use the installed **HydraAI** application; a separately installed development app may have different settings and recognition mode.

The November 3 finished-drink review update is installed in place and opens normally on the physical phone. Its two new synthetic UI checks passed, including inline unknown size and US fl oz conversion. The updated flow has not initiated a new physical analysis; recognition/logging and restart persistence were owner-verified before this UI-only change.
