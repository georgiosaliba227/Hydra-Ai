# Rewarding drink progress

Make the existing Today progress feel satisfying each time a consumed drink is confirmed. Keep SwiftUI, the existing teal palette, user-chosen goals, and deterministic beverage accounting.

Use a glass-like circular water gauge with a gradient fill, a short settling wave and gentle pulse after confirmation. Pair it with a percentage, four quarter-goal markers, and a clear completed state. Quick-add buttons should visibly press and show a compact saved receipt. Feedback celebrates recording, with no streak penalties or prompts to drink more.

The alternative of adding points, streaks, or game mechanics adds persistence and incentives that this request does not need. A static cosmetic ring would not provide the requested satisfying fill interaction. The implementation choice is native, finite SwiftUI animation with no dependencies or generated assets.

- Fill is clamped to 0–100%; the actual total remains visible above the goal.
- The optional goal remains explicitly user-chosen; no goal means no implied fill target.
- Confirmation feedback follows a successful creation and durable acknowledgement, never a tap, failed save, refresh, edit, or goal change.
- Initial loading and navigation must not replay a save celebration.
- Reduce Motion disables the wave, pulse, and burst; readable saved feedback remains.
- VoiceOver retains numeric total and goal information. Support large text and light/dark appearances.
- Show actual simulator captures at partial fill and goal completion. Haptics can be implemented but cannot be physically assessed in a simulator.
- No backend, AI, ledger, privacy, or nutrition changes.
