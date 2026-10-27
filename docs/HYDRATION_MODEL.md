# Hydration calculation design and evidence

Status: deterministic accounting is implemented in ai/hydration and used by the manual prototype. Personalized physiological requirement modeling remains an evidence-informed proposal, not a validated or implemented model. Scope proposal: generally healthy adults. Individualized guidance for minors, pregnancy/lactation, fluid restrictions or clinically managed conditions needs separate review.

## Accounting first
Sum confirmed consumed beverage mL as **beverage volume**, including coffee, milk, shakes and sports drinks. Keep estimated physical water content separate and unknown when composition is unavailable. Nutrients use a verified source and explicit serving conversions. Electrolytes do not create water; short-term retention is not a universal hydration multiplier.

Population adequate intake covers food moisture and beverages; it is not an exact personal requirement. Do not compare beverage-only logs directly with a total dietary-water target without a compatible, documented basis. The MVP should support a user-confirmed goal while the automated baseline method awaits review. [National Academies, Dietary Reference Intakes](https://www.nationalacademies.org/read/10925/chapter/2)

Moderate coffee intake contributed fluid comparably to water in a study of habitual male coffee drinkers; this does not establish an unrestricted dose/population rule. Do not subtract an arbitrary caffeine penalty. [Killer et al., 2014](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0084154)

The beverage hydration index studied short-term retention under specific conditions, not extra physical fluid or a universal multiplier. [Maughan et al., 2016](https://pubmed.ncbi.nlm.nih.gov/26702122/)

## Exercise and forecast proposal
For carefully measured comparable workouts, approximate sweat loss as `(pre_mass_kg - post_mass_kg) * 1000 + consumed_ml - urine_ml`; divide by duration for mL/hour. Record measurement quality, assumptions and environmental context. Mass-to-water conversion is approximate; invalid measurements produce insufficient_data, not confident advice. Avoid double counting activity already in a baseline. Never convert this into a forced drinking prescription or invent a universal safe upper limit. [NATA position statement, 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5634236/)

Weather, heart rate, HRV, sleep and steps may supply context; no independent numerical coefficients are approved. HR/HRV cannot be treated as direct dehydration measurements. Creatine does not automatically warrant extra water; reviewed research does not establish dehydration from supplementation. [Creatine research review, 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC7871530/)

Future core outputs: versioned range or insufficient_data; consumed totals; distinct baseline/exercise components; source inputs; uncertainty and reasons for changes. Actual activity replaces planned activity rather than being added twice. Missing biomarkers never become zeros. Meta explains these outputs and cannot recalculate or inflate targets. Track correction history before considering learned personalization.

## Existing starter audit
`Hydra-Ai-Starter/ai/forecast.py` uses 30 mL/kg + 6 mL/exercise-minute + 250 mL for heat. No supporting validation is recorded; it lacks uncertainty and excessive-intake safeguards. The exercise field also includes heat. Three passing tests confirm demo behavior only. Preserve it during planning; replace or explicitly isolate it after scientific and architecture review.

## Required validation before release
Reviewed baseline/population policy, compatible units, food-versus-beverage basis, no arbitrary beverage/creatine/HRV adjustments, missing data, invalid/negative/NaN inputs, duplicate activity, extreme exercise, and transparent uncertainty. Evaluate numeric core independently of AI. Do not describe logged intake as a measured hydration state.

## HealthKit privacy
Request only used data types and purpose strings, publish a privacy policy, and treat empty reads as no accessible data (read denial is intentionally indistinguishable). Apple requires express permission and a qualifying health/fitness purpose for third-party disclosures; consent alone is not sufficient for arbitrary AI export. Keep raw biometrics on device pending documented policy review. [Apple privacy guidance](https://developer.apple.com/documentation/HealthKit/protecting-user-privacy)
