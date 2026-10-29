# Muse Wonder demo cases — approval package

Two cases give the demo one real Wonder explanation and one real Wonder
assistant selection on Georgio's $30 experiment allocation. Approving them is a
human decision; nothing here sends a request. A test
(`tests/recognition/test_wonder_approval_package.py`) fails if code changes
alter these payloads, so the hashes below always match what would be sent.

| Case | Payload SHA-256 | Input bound (tokens) | Output limit | Worst-case cost |
| --- | --- | ---: | ---: | ---: |
| scenario `complete` | `c2125b019bc3f4193f5df9a60114d6bf1979004d816206d3947eb4f68d9885fd` | 4,127 | 512 | $0.026748 |
| question `hot_weather` | `c92712ed5fa28a3bf165d756a29852905df136408ebded8ecee2a7b9e159bba9` | 1,050 | 512 | $0.014440 |

Worst case for both: about **$0.04**, well inside the $10 Wonder target and the
$0.25 per-attempt cap. Prices: $4 input / $20 output per million tokens, no
cache discount; input bound policy `canonical-payload-bytes-v1`.

What each payload contains: the reviewed prompt, a strict JSON schema of
allowed IDs, and either the server-owned synthetic `complete` workout scenario
or the fixed question "Should I drink more when it's hot?". No personal data,
HealthKit values or free text.

## Steps (after the account freeze question in BLOCKERS.md is resolved)

1. `python -m scripts.wonder_admin prepare --scenario complete` and
   `prepare --question-id hot_weather`; confirm the hashes above.
2. Fill each `approved_case_template` with an expiry and the input-consent,
   live-dispatch and spending references; import with `record-case`.
3. Run each with `run-case ... --confirm-billable`, then record invoice
   finality before the next one. Replay in the app needs
   `HYDRA_WONDER_RESULTS_DIR`.
