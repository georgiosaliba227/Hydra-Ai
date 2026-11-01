# Camera confirmation and correction memory

November 1, 2026 owner assignment: photo → Muse recognition and visibly supported
volume estimate → details → Confirm or Edit entry. Personal correction memory
and separately opted-in training examples were selected explicitly. This
implementation is mock-first and authorizes no additional inference.

`recognition-v1` gains nullable estimated liquid lower/upper mL bounds and a
volume basis. Capacity, liquid present and amount consumed remain distinct.
Unobservable fill or unsupported geometry stays unknown. No photo estimates
consumption; confirmation includes the actual consumed amount before logging.

Responses include a normalized JPEG SHA256 and an optional personal correction
beside each original candidate. Original Muse output is retained as its own
suggestion. Exact-image memory may suggest corrected identity/capacity and an
explicitly corrected liquid amount for that same photo; matching
specific brand/product/label text can suggest identity only. Generic cups and
similar front labels do not establish capacity or fill. Mock and live memories
are isolated. No correction silently becomes a provider prediction or verified
nutrition source.

`POST /v1/beverages` accepts optional `recognition_feedback` on confirmed photo
logs. It binds the image fingerprint, source mode and bounded original candidate,
personal-memory choice, optional explicitly corrected visible liquid amount,
and separate training consent. Corrected identity/capacity come from the confirmed
log. Beverage, memory and optional training example commit in one transaction
with the same idempotency key. A retry never logs or contributes twice. An
unconfirmed edit, canceled form or analysis alone writes no correction.

Personal memory stores details only. Training contribution defaults off and
requires consent version `hydra-training-photo-correction-v1` plus the selected
photo. The server validates its fingerprint, strips JPEG metadata again and
stages photo plus original/corrected beverage details as `pending_review`.
Actual consumed volume, HealthKit data and unrelated history are excluded from
training labels. Mock examples are labeled synthetic. Nothing automatically
trains Muse, sends a dataset to Meta or shares across computers. The latest 20
opted-in examples are retained locally for reviewed future training; older
staged examples are removed. The UI discloses photo storage and this retention.

Pending confirmation retains a photo on device only when training was expressly
selected; existing protected-file/idempotent delivery applies. Ordinary personal
corrections retain no photo. Export includes owned correction records and
opted-in training examples; deleting a beverage or all user data removes the
associated correction and training copy. Financial history is excluded from
these operations. Financial databases are never automatically migrated with
feedback tables: use a separate beverage database and the existing financial
authority through a backend-only `HYDRA_META_LEDGER_PATH` setting.
