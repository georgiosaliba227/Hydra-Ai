# Hydra AI — submission draft

Draft for the Meta Global AI Developer Hackathon 2026 (Startup track), due
November 4, 9 PM ET. Items marked **[pending]** depend on steps in
[NEXT_ACTIONS.md](NEXT_ACTIONS.md) and must be confirmed or removed before
submitting. Portal fields and video length are still unverified
([HACKATHON_COMPLIANCE.md](HACKATHON_COMPLIANCE.md)).

## One line

Hydra AI is an iPhone hydration assistant that keeps the numbers honest and
uses Meta's Muse models to explain them: Muse Spark reads the drink in your
photo, and Muse Wonder decides which evidence-backed explanations apply to you.

## Problem

Hydration apps hand out a fixed "8 glasses" target, count coffee as
dehydrating, and turn heart rate or a hot day into made-up adjustments. People
end up with false precision and advice the evidence does not support.

## What Hydra does

- **Log what you actually drank.** Manual entry or a photo; the photo only
  suggests a drink, and nothing is saved until you confirm the amount. Edit or
  delete entries any time.
- **Count every drink honestly.** All beverages contribute their full volume.
  Water content and electrolytes appear only when a verified source provides
  them. No caffeine penalty and no beverage multipliers.
- **Your goal, not ours.** An optional daily goal you choose, with progress on
  the Today screen. Hydra does not prescribe an amount.
- **Workout sweat-loss range.** From comparable measured workouts, shown as a
  range, never a drinking target.
- **Ask Hydra.** Questions about coffee, creatine, sweat, milk and sports
  drinks, heat, heart rate and daily needs get reviewed answers with sources.
  Urgent symptoms always get "seek care" first.

## How we use Meta AI (25%)

| Model | Job | Guardrails |
| --- | --- | --- |
| Muse Spark 1.3 Standard | Identify beverages in a consented photo | Candidates only; user confirms the amount; no nutrition guessing |
| Muse Wonder 1.0 Standard | Choose which reviewed explanations apply to a workout scenario, and which reviewed answers fit a suggested question | Strict JSON schema of allowed IDs; server validates against the scenario; Wonder never writes advice or numbers |

Why this split: numbers come from deterministic, testable code, while the
models do what they are good at, reading images and reasoning about which
context matters. A malformed or ungrounded model reply is rejected, never
repaired or shown.

Evidence of real use: one Muse Spark camera request ran (HTTP 200, correctly
read a synthetic "WATER 250 mL" image). **[pending]** One Muse Wonder
explanation and one Wonder assistant selection, recorded and replayed in the
app with token counts and cost.

## Technical depth (20%)

- SwiftUI client, FastAPI backend, SQLite, deterministic Python engine.
- Every billable request passes one authoritative ledger: per-account $120
  cutoff, $75/$100 checkpoints, a pre-approved exact payload per request, a
  one-use dispatch ticket, settlement from provider usage and an account
  freeze on anything unexpected. Wonder requests are bounded at about $0.03.
- Offline research models on public exercise studies, reported honestly:
  SpectroPhon test MAE 71.79 mL; on PhysioNet QDE our model (331.60 mL) did not
  beat its baseline (314.22 mL). These are study-specific proxies, not daily
  requirements.
- About 790 automated Python tests, 64 XCTest and 6 end-to-end UI tests; CI on
  every pull request.

## Impact (30%)

Hydra's audience is everyday athletes and health-conscious people who want to
understand their drinking habits without pseudo-science. It turns a log into
explanations they can trust because every claim is sourced and every number is
reproducible. It works offline for logging, keeps raw HealthKit data on the
device, and never sends a free-text question to an AI provider.

## Demo script (about 2 minutes)

1. **Today (10 s).** Show logged total and goal progress: "your own goal, not
   a recommendation."
2. **Log by photo (25 s).** Camera → suggested drink → confirm 330 mL → total
   updates. Point out that nothing is logged without confirmation. This uses
   mock recognition unless another live Spark request is approved **[pending]**.
3. **Fix a mistake (10 s).** History → swipe → Edit to 250 mL; total updates.
4. **Ask Hydra (25 s).** "Does coffee count?" → reviewed answer with source.
   Then type "I fainted after my run" → "seek urgent care" first.
5. **Muse Wonder (30 s).** Workout forecast → run the simulated workout →
   "Muse Wonder · recorded live result": the explanations Wonder chose, with
   tokens and cost. **[pending real recording]**
6. **Close (15 s).** Numbers from tested code, explanations from Meta models,
   every claim sourced.

## Limitations to state

Wellness tool, not medical advice. Sweat-loss ranges come from limited study
data and personal measurements, not clinical validation. Simulator-tested;
**[pending]** physical-iPhone pass of the newest screens.
