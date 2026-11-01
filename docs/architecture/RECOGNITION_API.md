> Guarded live-mode and isolated account-budget extensions are specified in [GUARDED_META_API.md](GUARDED_META_API.md). The mock-only limitations below remain the default configuration; earlier shared-credit assumptions are superseded by account-specific controls.

# Beverage recognition contract v1 (Milestone 2)

November 1 additive implementation: [camera confirmation and correction memory](CAMERA_CORRECTIONS_API.md)
adds supported visible-liquid ranges, personal correction suggestions and separately
consented training-example storage after confirmation. Analysis itself still writes
no images or unconfirmed predictions. Earlier statements about no image storage
apply to ordinary analysis/logging; the explicit training opt-in is the sole new
photo-storage exception. It does not activate Meta or automatic model training.

Extends PROTOTYPE_API.md. Existing manual logging stays compatible. The default is mock mode with billable requests disabled; no provider transport or credential is loaded in that mode. The implemented guarded opt-in mode, separate account ledgers, consent fields and recognition receipts are defined in GUARDED_META_API.md. Conflicting mode/billable flags refuse startup; a matching flag pair alone cannot dispatch.

## Analysis

`POST /v1/recognitions`, authenticated like other /v1 routes. JSON fields: `image_base64` (one JPEG, <=1 MiB decoded), `photo_consent: true`, `mock_scenario` (branded, generic, ambiguous, missing_nutrition, failure; default ambiguous). This route permits up to 1,400,000 body bytes. Ordinary other requests remain 16 KiB; explicitly opted-in training-photo confirmations may use up to 1,450,000 bytes under CAMERA_CORRECTIONS_API.md. No URL/file references, HealthKit data, or extra fields. JPEG header/dimensions validated without decoding pixels; dimensions <=2048 per side. iOS redraws to <=1600 pixels, removes metadata and encodes JPEG before consented upload. Backend mock checks the image envelope but does not interpret pixels. Scenario is explicitly user-selected demo data, never a real prediction.

Returns `version: recognition-v1`, `mode: mock`, `model: muse-spark-1.3`, `candidates` (max 3): `identity`, nullable `product_id`, nullable `container_ml`, `confidence` (low/medium/high; uncalibrated model assessment), `uncertainty_reasons`, nullable server-sourced `nutrition` (basis_ml, sodium_mg, carbohydrate_g, water_ml, potassium_mg, provenance). Always `requires_confirmation: true`. Empty candidates = uncertain/no beverage. No log or image is persisted by analysis. Failure returns sanitized retryable 503 `recognition_unavailable`. No automatic analysis retries. Images exist in process memory only for the request; no image/response-body logging, disk writes, Files API, or provider uploads. Runtime memory and OS snapshots are not secure erasure guarantees.

## Confirmation

Extend POST /v1/beverages: source manual or confirmed_recognition. Optional `product_id` (server catalogue key), `container_ml` integer 1..5000. A known container bounds consumed mL; an unknown container stays absent when the user confirms a liquid amount. Optional `beverage_type` stores descriptive type separately from the existing `category` display name. Photo logs may declare `consumption_assumption: entire_liquid` or `full_container`; full-container logging requires equal known capacity and consumed mL. Server provenance records the user assumption explicitly.

The November 1 camera form defaults to the supported whole-liquid estimate under that declared assumption; final Confirm remains required. Unknown liquid needs editing or an explicit full-container choice. Edit offers name/type and volume presets plus mL/US fl oz/L. Identity/type corrections clear the suggested product match. Server rejects a product_id whose exact identity differs from category. Manual records cannot supply recognition fields. Idempotency covers all confirmation fields; retain exact pending payload/key across failures/relaunch. Mock analysis may be repeated independently without logging anything. Guarded Meta analysis remains restricted to a fresh one-use permit and must never be retried after an attempt or ambiguity.

Ordinary confirmed logs persist name/type, optional container, confirmed volume, optional user assumption, source, nutrition/provenance and timestamps. Images and bounded prediction references persist only under the separate correction/training choices in CAMERA_CORRECTIONS_API.md; analysis itself does not persist them. Server retrieves nutrition from a small versioned, reviewed local catalogue with manufacturer URL, verification date, exact US variant and serving basis. Unmatched products/generic beverages remain null; catalogue failure never invents values. No external nutrition fetch at request time. Nutrition is optional and composition passes through the existing deterministic engine; missing water fraction remains unknown. Historical records retain their nutrition snapshot. Normal database deletion/retention policy applies to confirmed logs (see docs/MILESTONE_2.md); no raw HealthKit export is added.

## Live gate

A guarded Responses transport is implemented but live dispatch remains blocked by the verified maximum-cost gate. Follow GUARDED_META_API.md and docs/API_BUDGET.md: verify each account independently, retain one authoritative gateway with isolated account ledgers, establish a whole-request cost bound, verify retention and consent, deliver required notices and obtain explicit approvals. Committed defaults remain mock/false. No configuration flag alone authorizes or bypasses the budget gateway.


## Controlled-test additive label observation (2026-10-27)

Candidates may include nullable `visible_label_text` (at most 600 characters), a verbatim, unverified transcription of visible nutrition/volume labels. This field is untrusted display evidence only; never parse it into verified composition or log nutrients automatically. The current iPhone ignores this additive field. Existing confirmation, curated nutrition selection and receipt-based deterministic logging remain required. The provider JSON schema requires this field with null for unreadable labels; legacy response fixtures can omit it at the backend parser boundary.

The proposed disabled `dual-test-v1` policy binds Georgio to camera and Amine to synthetic hydration explanation, with separate <=$2 explicit approvals. See [controlled test contract and procedure](../META_DUAL_TESTS.md). It does not change recognition-v1 confirmation or authorize requests.

## Client and provider boundary safeguards (2026-10-28)

Provider category, brand, product and uncertainty text are trimmed at parsing; a non-null field that becomes empty is invalid model output. Nullable identity fields must use null for unknown values. Verbatim `visible_label_text` is unchanged. Invalid output never receives a successful recognition receipt; already reported usage remains accounted and the existing quarantine prevents retries.

The iPhone binds verified capabilities, photo consent and recognition receipts to the current backend connection generation. Switching backend, access token or offline mode revokes these states; delayed responses from a previous generation are discarded, including a switch away and back to the same URL. Confirmations must use the backend that produced their receipt. A failed live HTTP request, timeout or invalid response shows fixed no-retry guidance without inheriting generic backend retry text. Mock failures retain their existing local retry behavior.
