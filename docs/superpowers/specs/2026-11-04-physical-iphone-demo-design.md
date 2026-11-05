# Physical iPhone submission demo

## Owner's objective and selected approach

Verify that the recognition model is stored locally, prepare a demo account with
simulated sample records, walk through the features, push all source/setup work
to GitHub before recording, and produce a live app demo video. The owner selected
**the entire recording on the physical iPhone**.

Approaches considered: a simulator recording is repeatable but omits physical
camera operation; a hybrid adds a physical camera segment but mixes devices; an
entire physical recording shows the actual installed app throughout. The owner
chose the third approach. Mac screen sharing stays off during recording because
it interferes with the iPhone camera.

## Demo account and isolation

Build a separate **Hydra Demo** application with bundle identifier
`com.georgiosaliba.hydraai.demo`, using the same functional app code and bundled
Core ML model. Its sandbox and Keychain access group are separate from the owner's
Hydra app. Do not replace, reset or seed the owner's existing app or backend.
This is a fictional local demo identity, not an externally registered account.

The demo app visibly says **DEMO · simulated data**. Seed fourteen days of varied
drink records using stable IDs and a persisted seed anchor. Today's initial
total is 2250 mL against a 3000 mL confirmed demo goal. A fictional adult profile
illustrates source review; body/supplement answers receive no numerical
adjustment. No actual HealthKit data is requested or displayed. An explicit
demo-only reset restores the simulated account for rehearsal. Ordinary relaunch
preserves edits, confirmations and the seed anchor.

Optional insights use a separate stateless demo backend and a fresh development
token entered only at runtime/Keychain, never source. No owner credentials,
private database, financial ledger, provider dispatch or paid requests are used.
Phone logs, camera inference and saved goals remain local.

## Walkthrough to rehearse, then record

Target roughly three minutes; the signed-in submission portal's video length
limit still needs confirmation before final export.

1. Demo identity and Today: show the synthetic-data label and water progress.
2. Guided goal review: show the labelled published adult starting reference and
   its source; explain that confirmation is a choice, not a measured requirement.
3. Camera offline: disable Wi-Fi/internet for this segment, photograph a drink
   with a readable size label, tap Analyze, inspect/edit the suggestion, and
   confirm 500 mL as a simulated entry. Keep uncertainty visible when applicable.
4. Today: the confirmed photo changes the total; add 250 mL manually to reach the
   demo goal and visibly fill the circle.
5. History: edit a simulated entry and show that totals respond to corrections.
6. Reconnect Wi-Fi for backend features. Trends: review the phone aggregates,
   send them, and show the calculated patterns with their actual provenance.
7. Ask Hydra: ask whether coffee counts, optionally include today's demo total,
   and show the reviewed answer and evidence.
8. Workout: run the clearly labelled simulated workout. Its loss estimate does
   not become logged consumption or a daily drinking target.
9. Privacy: briefly show optional Apple Health/data controls without requesting
   real records. Close on Today and the demo identity.

Use the phone's built-in screen recorder, with Mac sharing off. The owner will
operate the physical camera and recorder directly. After recording, transfer
the actual file to the Mac for trimming, captions and export. Preserve the
original. The final footage remains entirely from the physical iPhone; no
generated app screens, fabricated model results or simulated footage substitutes.

## Source and release sequence

Verify model package hashes/byte counts and its presence in the signed demo
bundle. Verify the installed demo app can run bundled inference with networking
off. Update the stale submission draft to distinguish the local Meta DINOv2
model/Apple OCR from deterministic summaries, reviewed answers, research models
and historical hosted-provider experiments.

Test isolation, seed idempotency/resume/reset and the real feature flows. Push
the source, setup, runbook and current submission draft; verify the remote commit
and model blob before the owner starts the final recording. Link the exact
submission branch/commit because `main` currently lacks these feature commits.
PR creation previously failed due GitHub integration/CLI permissions; do not
claim a merge or submit/accept event terms on the owner's behalf.

## Completion evidence

Local model hash/bundle/runtime report; isolated seeded account and rehearsal;
verified GitHub source commit predating recording; original physical footage;
playable reviewed MP4 with truthful captions and no personal records or visible
tokens; final runbook/source/video links. A script or recording plan alone does
not complete the requested video.
