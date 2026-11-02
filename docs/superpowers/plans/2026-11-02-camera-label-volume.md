# Printed beverage size implementation plan

**Request:** Read printed container-size labels, such as the attached DASANI image's “1 LITER”, rather than present a conflicting guessed size.

**Investigation:** Existing metric conversion already returns 1000 for “1 LITER”. A real reproduction read that text and returned container1000 with a visual liquid range900–1000. The app currently prefills950 from that range and hides printed capacity in Edit. This is principally presentation/default selection, not a missing litre conversion.

**Decision:** Tell Muse to inspect printed net contents first and transcribe the size, independently of visible fill. Show label-derived capacity prominently in Confirm/Edit. A readable label may prefill its full capacity under an explicit full-container assumption when fill is unknown or the model range includes full capacity; Confirm accepts that assumption. An exact-photo user liquid correction or supported clearly partial range keeps priority. Unlabeled visual capacity alone never becomes liquid volume. Unknown/unreadable/conflicting labels stay unknown; no new lookup, OCR dependency, retry or financial-policy change.

- [x] Add failing Swift regressions for the one-litre example, hidden fill, partial fill, exact-photo correction and full/partial toggling.
- [x] Implement draft priority, visible label-size UI and label-first Muse instruction; add API label regression.
- [x] Run Python and Swift suites plus focused native review UI; independently review the change.
- [x] Verify one real request returns1000mL label evidence via the guarded app endpoint; install the updated phone build and verify label/full-container review.

No personal screenshot, provider raw response or consumption history is committed. Real verification remains through the active $120 cutoff controller and existing owner photo-disclosure authorization; no automatic retries or automatic logging.

## Verified evidence

- Four new Swift cases first reproduced the incorrect default; the full native unit result contains98passed,0skipped,0failed.
- Full Python1156passed/32subtests/1skipped; offline rehearsal passed without provider dispatch.
- One real guarded app-endpoint request for the supplied example returnedcontainer_ml1000,label_capacity_ml1000 and literal1LITER. Its raw response/photo remain private; this was analysis only and created no consumption entry.
- The signed physical iPhone27.2 label-review case executed and passed: printed1000mL, explicit full-container assumption, Confirm/Edit available, exactly1000mL confirmed into the isolated mock hydration store. Teardown restored the owner's normal live backend. The installed production app includes the fix.
- Test-harness setup problems (a gated skip, an incorrect mock return type, a localized thousands separator and an asynchronous Settings wait) were identified separately and corrected; no production workaround was added for them.
- Independent review found no Critical/Important issue. Minor deferred: Edit relies on collapsed Photo details for explicit unverified-label wording, while initial review shows the nearby verification disclaimer.
