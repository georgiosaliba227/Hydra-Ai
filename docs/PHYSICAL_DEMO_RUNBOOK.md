# Physical iPhone demo runbook

Target: approximately **3 minutes**, entirely recorded on the physical iPhone.
Signed build and isolation tests passed. Installation, rehearsal, source freeze
and actual video review are tracked in [source verification](DEMO_SOURCE_VERIFICATION.md).
The owner has set an **8:30 PM ET** submission target; the event-page deadline
is November 4, 2026, 9 PM ET. The signed-in portal's
video limit/format and eligibility checks still require owner review.

## Prepare and rehearse

Use **Hydra Demo**, bundle `com.georgiosaliba.hydraai.demo`, alongside the owner's
normal Hydra app. Check the visible **DEMO · simulated data** label. This is a
fictional local account; do not seed the production app or full backend. Its
explicit demo-only reset restores fourteen days, today's 2250 mL and a 3000 mL
goal. Ordinary relaunch preserves changes. Reset explicitly after rehearsal;
do not expect reopening to reseed. Do not delete the owner's normal app/data.

The orchestrator provisions a dedicated stateless features backend and fresh
demo runtime token privately. In Settings, keep **On this iPhone** enabled and
enable **Connect backend features** for this demo connection only. Use
`http://MAC_PRIVATE_IP:DEMO_PORT` on the trusted private LAN. Enter the token
only at runtime in the secure field; never put it in source, screenshots or
this document. **Save connection**, then **Check backend features**. Provision
and check before recording so connection fields stay off camera. The runtime
opens no owner database/historical ledger and cannot dispatch hosted AI.

Rehearse all screens once. Use a real drink with a clearly readable,
single-container 500 mL declaration, plain background and good light. A wrong
or uncertain suggestion is acceptable: use Edit and explain the correction.
Do not substitute fabricated app output, test-fixture photos, simulator screens
or generated screenshots for physical capture.

Keep the goal at 3000 mL throughout. Guided setup can show the adult reference
and source without adopting a different value; custom confirmation remains
available. Use only the fictional profile. If rehearsal changes the goal/logs,
use the guarded demo-only reset and verify 2250/3000 again. Choose **US** under Settings → Display units, as requested by the owner.
The underlying sample amounts remain 2250/3000 mL, displayed as about
**76.1/101.4 US fl oz**. Printed label evidence keeps its original units. Complete camera permission prompts during rehearsal;
do not request real Apple Health records.

## Freeze source before the final take

The orchestrator builds/signs/verifies the exact demo bundle, checks bundled
model bytes/hashes/notices and remote Git blobs, installs it alongside Hydra,
and completes new demo tests. Push **all source, setup and docs** to
[`codex/physical-demo-submission`](https://github.com/georgiosaliba227/Hydra-Ai/tree/codex/physical-demo-submission)
before filming. The app code commit and verification evidence are in
[source verification](DEMO_SOURCE_VERIFICATION.md). Do not cite `main`, claim a merge or claim a PR exists: previous PR
creation failed with HTTP 403. A source change after freeze requires a new
verified freeze before the final take.

The November 4 pre-demo baseline was 1457 pytest passed/5 skipped/58 subtests,
202 native XCTest and 7 relevant simulator UI flows. It does not replace the
new demo-isolation tests or final physical rehearsal.

## Start the phone recorder

The owner performs physical taps and camera operation. Stop **all Mac screen
sharing/Device Hub interaction** before capture; sharing can disable the camera.
Keep the phone unlocked and check its own camera preview during rehearsal.
Enable Focus/Do Not Disturb and hide unrelated notifications. Use portrait
orientation and sufficient battery/storage. Start the iPhone's built-in
**Control Center → Screen Recording**; enable its microphone if narrating live.
Return to Hydra Demo after the countdown. No Mac screen capture is used.

## Three-minute tap order and narration

Timings are rehearsal targets; keep real model processing visible. Use the
current Today, History, Insights, Camera and Settings tabs.

| Time | Physical taps / visible proof | Narration copy |
| --- | --- | --- |
| 0:00–0:15 | Today: show **DEMO · simulated data**, 76.1 fl oz, 101.4 fl oz goal and partial circle. | “This is Hydra on a real iPhone. These fourteen days are simulated demo records. The circle tracks logged drinks against a goal the user confirms.” |
| 0:15–0:35 | Today goal setup → fictional adult profile → **Review adult starting reference** → source/disclosure. Show custom-goal option; return without changing 3000. | “Guided setup labels the published adult starting reference and source. I can confirm a reference or my own goal. It is not a measured personal requirement; body and supplement answers add no invented adjustment.” |
| 0:35–1:15 | Control Center: airplane mode on and explicitly Wi-Fi off. Return → Camera → **Take photo** → capture/use real printed label → **Analyze** → **Your drink**. Show uncertainty/size; **Edit** if necessary → 16.91 US fl oz (500 mL) → **Confirm**. | “Bundled Meta DINOv2 and Apple label reading run offline. This is a suggestion. A printed 500 mL size is capacity, not proof of what I drank. For this simulated entry I confirm the whole drink; I can correct type, size or amount.” |
| 1:15–1:30 | Today: show about 93 fl oz. Tap the **Water 8.5 fl oz** quick-add once → about 101.4 fl oz and a full circle. | “Only confirmation adds the photo entry. Another simulated 8.5 fl oz fills the goal. This is beverage volume, not a hydration measurement.” |
| 1:30–1:45 | History → swipe left on a today's simulated drink → **Edit** → change volume → **Save**. Show changed daily total. | “I can correct the record later. History and totals follow the confirmed amount; the original photo suggestion stays separate.” |
| 1:45–2:10 | Control Center: airplane mode off, Wi-Fi on. Insights → **Your trends** → **Summary to share** → **Send summary & show trends** → result/provenance. | “I review the phone's aggregate summary before sharing it with this stateless backend. Hydra calculates these patterns. No AI provider is called; missing logs mean unknown intake.” |
| 2:10–2:30 | Back → **Ask Hydra** → “Does coffee count?” → optionally **Include today's logged total** → ask → reviewed answer/source. | “Ask Hydra returns reviewed answers with evidence. I choose whether to include today's simulated total. It does not infer dehydration from heart rate.” |
| 2:30–2:48 | Back → **Plan a workout** → demo example → **Run the demo workout** → simulated range/result. | “This is a labelled simulated workout. Its conditional loss estimate is separate from consumption and never becomes a daily drinking target.” |
| 2:48–3:00 | Close → Insights → **Apple Health** privacy screen only, no access request → Today with demo label. Stop from phone. | “Health access is optional; this demo reads no real Health records. Photos and confirmed logs stay on this iPhone. Suggestions, corrections and consumption stay distinct.” |

After History editing, the displayed total can differ from 101.4 fl oz (3000 mL). Say the actual value
or leave it unspoken; do not claim the final circle remains full. If capacity
is unknown, enter the visibly supported 500 mL as a **user correction**, retaining
the unknown original suggestion. If a feature fails, fix/rehearse/reset and
record another real take. Preserve the takes; do not fabricate success.

## Source references for rehearsal

These identifiers were inspected at the pre-demo baseline; verify final labels
on the installed demo during rehearsal. They are developer references, not
narration or proof of an unverified new screen.

| Flow | Accessibility identifiers |
| --- | --- |
| Today / goal | `dailyTotal`, `goalProgress`, `todayGoalSetup`, `calculateGoalReference`, `goalStartingReference`, `goalAdultReferenceDisclosure`, `guidedCustomGoal`, `guidedConfirmCustomGoal` |
| Camera / review | `analyzePhoto`, `reviewDrinkName`, `photoVolume`, `photoLabelCapacity`, `editRecognitionEntry`, `photoContainerCapacity`, `photoConsumed`, `photoVolumeUnit`, `savePhotoBeverage` |
| Quick-add / History | `quickAddConfirmation`, `editVolume`, `saveBeverageEdit`; quick-add buttons use `quickAdd-<preset id>` |
| Insights / Trends | `insightsTrends`, `deviceTrendsPreviewTotal`, `sendDeviceTrends`, `trendsSummary` |
| Ask / Workout / Health | `insightsAsk`, `assistantQuestion`, `assistantIncludeToday`, `assistantAsk`, `insightsWorkout`, `openWorkoutDemo`, `runWorkoutDemo`, `closeWorkoutDemo`, `insightsHealth` |

Do not load **Recorded Muse explanation** or enable recorded Wonder picks in
this take. Historical recordings must not be narrated as fresh phone inference.
The small phone model's held-out category result is 50/75 (66.7%), with
uncalibrated scores. The Mac-only 30B adapter's 63/75 joint identity/capacity
result is separate; neither establishes nutrition or medical validity. See
[submission claims](SUBMISSION_DRAFT.md).

## Transfer, edit and deliver the actual file

After stopping, the owner AirDrops the original recording from Photos to the
Mac. Preserve the unmodified original privately. Inspect the entire actual
recording for readable UI, real capture/analysis/confirmation, demo disclosure,
correct provenance, clear audio and absence of tokens/personal data. Trim dead
lead/tail time and add accurate captions using that file. Preserve model
uncertainty; do not imply edited processing time measures latency. Export a
playable MP4 at the portal's confirmed length/format, then verify duration,
playback, audio, captions and privacy. Keep the original beside the export,
record the source commit and capture/export times, and deliver the actual
video for owner review. A runbook/script alone does not complete the video.
No external publishing, terms acceptance or paid calls are part of this handoff.

Recording controls follow [Apple’s iPhone screen-recording guide](https://support.apple.com/en-lamr/guide/iphone/iph52f6e1987/27/ios/27). The recording is saved to Photos; microphone audio is optional.
