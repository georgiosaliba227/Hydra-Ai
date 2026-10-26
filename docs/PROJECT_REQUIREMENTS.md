# Project requirements

Status: proposed, 2026-10-26. Track: Startup, confirmed by the user. Milestone 1 remains blocked until planning PR #1 is reviewed and approved. This first execution covers Milestones 0 and 0B only.

## MVP acceptance criteria after approval
1. SwiftUI user can confirm a beverage and consumed mL, edit/delete it, and see persisted daily beverage totals.
2. Camera recognition uses a verified Meta vision endpoint and returns candidates, container/volume uncertainty, and provenance. Recognition never commits a log without user confirmation. Manual entry works offline or when inference is blocked.
3. Known nutrition comes from a verified product source with serving size, retrieval time, and product identifier. Unknown fields remain unknown; estimates are labeled and never presented as exact manufacturer facts.
4. Dashboard separates consumed beverage volume, estimated water content where available, and estimated needs/ranges. It shows history, explanations, and missing inputs without claiming measured dehydration.
5. HealthKit reads only necessary activity data after permission; declined/unavailable data has a manual fallback. Apple Watch data is accessed through HealthKit initially.
6. Deterministic calculation code supplies every numerical forecast and its assumptions. Meta interprets and explains these results without changing them.
7. AI assistant answers questions about logged intake, exercise, coffee, and creatine using approved evidence and minimal consented context. It cannot prescribe medical treatment or silently change goals.
8. All paid calls go through one tested shared gateway with atomic reservations, cost reconciliation, and fail-closed thresholds.

## Scope priorities
M1: manual logging, persistence, dashboard, backend/client connection. M2: Meta recognition and confirmation, nutrition provenance. M3: conservative forecast ranges, HealthKit, approved weather, grounded explanations. M4: security, budget, integration and evaluation. M5: installation, reproducible demo and submission.

Defer Garmin/WHOOP/Oura/Fitbit direct integrations, learned predictive models, SAM segmentation, complex retention models, and monthly analytics until the core demo works and rules/access are verified. Preserve extension points for all supported drinks: water, sports/electrolyte drinks, coffee/tea, milk, protein shakes, milkshakes, smoothies, juice, coconut water, energy drinks, and unfamiliar homemade drinks.

## Constraints
Wellness scope; no direct dehydration inference from heart rate/HRV, no unsupported creatine or caffeine penalty, no arbitrary beverage multipliers. Personal medical conditions, pregnancy, medications, or fluid restrictions are outside automated personalized guidance pending appropriate review. No health export without specific consent; no keys in the client. Hackathon eligibility, timeline and model choices remain subject to verified official rules.
