# Camera confirmation and correction memory

November 1, 2026 owner assignment: photo → Muse recognition and visibly supported
volume estimate → details → Confirm or Edit entry. Personal correction memory
and separately opted-in training examples were selected explicitly. This
implementation is mock-first and authorizes no additional inference.

`recognition-v1` gains nullable estimated liquid lower/upper mL bounds and a
volume basis. Capacity, liquid present and amount consumed remain distinct.
Unobservable fill or unsupported geometry stays unknown.

November 1 full-drink assignment: default the confirmation form to the user's
assumption that they drank all the liquid. Use an exact-photo corrected liquid
amount or the rounded midpoint of a supported model range; show its uncertainty.
If fill is unknown, do not silently substitute capacity. Offer an explicit
"use full container" action when capacity is known; otherwise ask for the liquid
amount or a photo showing its size label. Confirm/Edit remains required before
logging. Users can turn off the assumption and enter a partial amount.

November 2 printed-size correction: inspect and show readable net-contents labels first (for example “1 LITER” → 1000 mL capacity). A label-backed capacity may prefill the full container under a visible `full_container` assumption accepted with Confirm, when fill is unknown or the supported range includes full capacity. This explicitly stated assumption replaces the midpoint default in that case; it is not a measurement or training target. An exact-photo user liquid correction, clearly partial supported range or contradictory label/range keeps precedence. Unlabeled inferred capacity alone still never prefills consumption. Printed capacity is visible on the initial review, not only in Edit. This supersedes the earlier instruction requiring a separate full-container action for label-backed capacity; manual edits and partial entry remain available.

Confirmed logs optionally carry `consumption_assumption: entire_liquid` or
`full_container`, with corresponding user-assumption provenance. Full-container
logging requires a known capacity equal to consumed mL. When capacity is unknown,
an explicitly confirmed liquid amount can still be logged without inventing a
container capacity. A later correction to consumed mL clears the old assumption.
This supersedes the earlier mandatory manual consumed-mL entry in the form; it
does not authorize model-inferred consumption or analysis without confirmation.

November 3 finished-drink UX clarification: **Confirm means the user finished the
drink**. The normal scan review does not ask how much was drunk or ask the user
to affirm the whole-drink default. A known supported size/whole-drink quantity
prefills the review; an unknown size gets an inline **Drink size** field with
explicit units. The copy says **Confirm logs the whole drink**. Logging a different
amount is available only as an optional action in Edit. Raw visible-liquid
estimates belong in secondary photo details. Existing quantity validation,
user-assumption provenance, personal corrections and training consent remain;
this clarification does not invent capacity or authorize automatic logging.

The server separately extracts unambiguous mL/L capacity from model-transcribed
label text as `label_capacity_ml`. This remains unverified label evidence,
distinct from the model's visual capacity and user corrections. Serving-size or
conflicting volume text is not treated as container capacity. No new lookup
service, photo recipient, model, spending permission or financial policy is added.

The owner expanded this assignment to a compact, automatically presented review
with Confirm/Edit. Edit exposes drink name, type, volume presets and mL / US fl oz
/ litre selection. Converted amounts round to the nearest mL. Capacity and raw
recognition details are secondary; learning preferences are collapsed. The user
can explicitly use full container capacity when fill is unknown. Name/type are
stored separately (`category` retains the existing display-name role;
`beverage_type` is bounded descriptive metadata, never a hydration multiplier).
Confirmed corrections remember type as well as name. A larger corrected liquid
amount clears a contradictory inferred capacity instead of inventing a new one.

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
