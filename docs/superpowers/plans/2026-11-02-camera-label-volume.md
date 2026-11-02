# Printed beverage size implementation plan

**Request:** Read printed container-size labels, such as the attached DASANI image's “1 LITER”, rather than present a conflicting guessed size.

**Investigation:** Existing metric conversion already returns 1000 for “1 LITER”. A real reproduction read that text and returned container1000 with a visual liquid range900–1000. The app currently prefills950 from that range and hides printed capacity in Edit. This is principally presentation/default selection, not a missing litre conversion.

**Decision:** Tell Muse to inspect printed net contents first and transcribe the size, independently of visible fill. Show label-derived capacity prominently in Confirm/Edit. A readable label may prefill its full capacity under an explicit full-container assumption when fill is unknown or the model range includes full capacity; Confirm accepts that assumption. An exact-photo user liquid correction or supported clearly partial range keeps priority. Unlabeled visual capacity alone never becomes liquid volume. Unknown/unreadable/conflicting labels stay unknown; no new lookup, OCR dependency, retry or financial-policy change.

- [ ] Add failing Swift regressions for the one-litre example, hidden fill, partial fill, exact-photo correction and full/partial toggling.
- [ ] Implement draft priority, visible label-size UI and label-first Muse instruction; add API label regression.
- [ ] Run Python and Swift suites plus focused native review UI; independently review the change.
- [ ] Verify one real request returns1000mL label evidence via the guarded app endpoint; install the updated phone build and verify label/full-container review.

No personal screenshot, provider raw response or consumption history is committed. Real verification remains through the active $120 cutoff controller and existing owner photo-disclosure authorization; no automatic retries or automatic logging.
