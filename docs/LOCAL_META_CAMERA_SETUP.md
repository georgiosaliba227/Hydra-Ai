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

Install the updated signed Hydra build through USB or a previously paired, reachable wireless Xcode connection. An old build does not accept `local_meta`; do not disguise it as hosted Spark or mock mode.

1. In Settings, use `http://<Mac-LAN-IP>:8771`, preserve the owner backend token, and save the connection.
2. Open Camera and tap **Refresh analysis mode**. The screen should mention the trained Meta model on your Mac.
3. Choose or take a photo with the drink name and printed metric size visible. Enable backend-photo consent and tap **Analyze with trained Meta** once.
4. Keep Hydra open while the Mac processes the image. The end-to-end local example took about 50 seconds; the server stops a request after 180 seconds and the client allows 210 seconds. A failed attempt is never automatically repeated.
5. Review the name and **Printed size**. A readable size must agree between the adapter and local label reading. Unknown or conflicting size stays unknown. Metric declarations are used exactly; ambiguous fluid-ounce-only labels remain unknown in this integration.
6. **Confirm** logs only the quantity you approve. A full-container default is explicitly an assumption. **No, edit entry** lets you change name/type and amount in mL, litres or US fl oz. Personal memory remains separate from model output; shared training examples require their own default-off opt-in and remain staged locally.

Canceling the review creates no beverage. A confirmed log uses the existing hydration engine. It does not establish measured water content, nutrients, remaining liquid or actual consumption from a photo.

The 84% held-out benchmark measured the selected adapter's identity plus capacity. This connected pipeline adds conservative OCR corroboration and can return more unknown volumes; it does not inherit a measured 84% end-to-end app accuracy claim.
