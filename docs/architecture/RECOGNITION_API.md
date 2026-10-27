> Guarded live-mode and isolated account-budget extensions are specified in [GUARDED_META_API.md](GUARDED_META_API.md). The mock-only limitations below remain the default configuration; earlier shared-credit assumptions are superseded by account-specific controls.

# Beverage recognition contract v1 (Milestone 2)

Extends PROTOTYPE_API.md for the authorized mock-only milestone. Existing manual logging stays compatible. Backend startup still rejects live/billable flags. No provider transport or provider credential is loaded.

## Analysis

`POST /v1/recognitions`, authenticated like other /v1 routes. JSON fields: `image_base64` (one JPEG, <=1 MiB decoded), `photo_consent: true`, `mock_scenario` (branded, generic, ambiguous, missing_nutrition, failure; default ambiguous). Only this route permits up to 1,400,000 body bytes; other routes remain 16 KiB. No URL/file references, HealthKit data, or extra fields. JPEG header/dimensions validated without decoding pixels; dimensions <=2048 per side. iOS redraws to <=1600 pixels, removes metadata and encodes JPEG before consented upload. Backend mock checks the image envelope but does not interpret pixels. Scenario is explicitly user-selected demo data, never a real prediction.

Returns `version: recognition-v1`, `mode: mock`, `model: muse-spark-1.3`, `candidates` (max 3): `identity`, nullable `product_id`, nullable `container_ml`, `confidence` (low/medium/high; uncalibrated model assessment), `uncertainty_reasons`, nullable server-sourced `nutrition` (basis_ml, sodium_mg, carbohydrate_g, water_ml, potassium_mg, provenance). Always `requires_confirmation: true`. Empty candidates = uncertain/no beverage. No log or image is persisted by analysis. Failure returns sanitized retryable 503 `recognition_unavailable`. No automatic analysis retries. Images exist in process memory only for the request; no image/response-body logging, disk writes, Files API, or provider uploads. Runtime memory and OS snapshots are not secure erasure guarantees.

## Confirmation

Extend POST /v1/beverages: source manual or confirmed_recognition. Optional `product_id` (server catalogue key), `container_ml` integer 1..5000. Photo confirmation requires container_ml and consumed_ml <= container_ml. User explicitly edits/confirms identity, container and consumed mL; no automatic fill for amount consumed. Unknown values require entry or manual fallback. Corrections clear the product ID if identity changes. Server rejects a product_id whose exact identity differs from category. Manual records cannot supply product_id/container_ml. Idempotency covers all confirmation fields; retain exact pending payload/key across failures/relaunch. Analysis may be repeated independently without logging anything.

Persist only confirmed identity, container, consumed amount, source, nutrition/provenance and existing timestamps. No image, filename, EXIF, prompt, or unconfirmed model candidates persist. Server retrieves nutrition from a small versioned, reviewed local catalogue with manufacturer URL, verification date, exact US variant and serving basis. Unmatched products/generic beverages remain null; catalogue failure never invents values. No external nutrition fetch at request time. Nutrition is optional and composition passes through the existing deterministic engine; missing water fraction remains unknown. Historical records retain their nutrition snapshot. Normal database deletion/retention policy applies to confirmed logs (see docs/MILESTONE_2.md); no raw HealthKit export is added.

## Live gate

Model/payload builder is offline-only. Before a separately reviewed live transport is introduced, reconcile shared gross usage and credits; verify account model access, complete image/token charge bound, provider data retention and consent; wire every attempt through the single authoritative ledger; deliver durable $75 notices to both developers; obtain initial and $100 further-spend approval as applicable. There is no live enable flag in this implementation.
