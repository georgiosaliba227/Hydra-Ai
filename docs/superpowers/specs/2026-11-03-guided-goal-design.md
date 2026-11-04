# Guided goal setup

The owner wants the app to ask birthday/age, height, weight and supplements, then
calculate a goal. Implement an adult published beverage starting reference with
editable confirmation, under [the numerical/privacy policy](../../architecture/GUIDED_GOAL_POLICY.md).
This is an engineering choice under the standing autonomous implementation request,
not a new medical validation or inferred approval of arbitrary multipliers.

Considered approaches: a body-weight/creatine formula has no reviewed coefficients;
an LLM-generated number would bypass numerical authority. The selected published
beverage table has a traceable basis and can supply an approximate starting goal
while the requested body/supplement answers remain transparently optional context.

Use a pure Swift profile/reference calculator, a protected connection-scoped local
profile store, and SwiftUI guided setup. Preserve current API/Meta contracts and
the new US/automatic-context experience. No third-party dependencies or automatic
paid calls. No profile upload. Only explicit goal confirmation reaches the backend.

Home and Settings offer the guided flow, with an explicit custom-goal alternative.
Age-only entry is allowed for privacy; birthday computes and displays age locally.
Body inputs use ft/in/lb or cm/kg. The review screen explains which answers chose
the source row and which did not alter the number. Unsupported/missing cases show
no automatic number and preserve custom entry. Confirming saves the local profile
and attempts the existing goal update; it never revives an old Meta preview.

Test eligibility/birthday boundaries, exact reference and US conversion, absent or
invalid optional inputs, no body/supplement adjustment, file protection/isolation/
corruption/export/delete, exact outgoing goal-only JSON, stale connection replies,
network failure, fresh goal/Home score and actual Simulator guided/custom flows.
Use synthetic profiles in tests; actual owner measurements stay on the phone.
