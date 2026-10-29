# Hydration assistant — contract (v1, local rules)

Implements MVP criterion 7 (PROJECT_REQUIREMENTS.md): answer questions about
logged intake, exercise, coffee and creatine from reviewed evidence, with
minimal consented context, never prescribing treatment or changing goals.
Written by Amine on 2026-10-29 before implementation.

## Principles

- Answers are reviewed text from `ai/assistant`, each with evidence references
  taken from [HYDRATION_MODEL.md](../HYDRATION_MODEL.md). Nothing is generated.
- A question maps to topic IDs. In v1 a deterministic local matcher does this;
  no question text is sent to any provider, stored or logged.
- Urgent-symptom wording always returns the escalation answer first, decided
  by local rules, never by a model. Medical-condition wording adds the
  medical-scope answer.
- Numbers come only from the deterministic engine (today's logged total), and
  only when the request explicitly consents to that context.
- Wonder may later choose topic IDs for the fixed suggested questions only.
  Each has a deterministic payload that can be pre-approved under the
  experiment case manifest (WONDER_HYDRATION_API.md). Free-text questions stay
  local because their exact payload cannot be approved in advance.

## GET /v1/assistant/questions

`{"version":"assistant-v1","questions":[{"id":"coffee_counts","text":"..."}...]}`

## POST /v1/assistant

Request (extra fields forbidden), exactly one of `question` or `question_id`:

```json
{"question": "Does coffee count?", "context_scope": "none"}
{"question_id": "creatine_water", "context_scope": "today_logged_total",
 "date": "2026-10-29", "timezone": "Europe/Paris"}
```

- `question`: 1–300 characters after trimming.
- `question_id`: one of the suggested IDs.
- `context_scope`: `none` (default) or `today_logged_total`, which requires
  `date` (YYYY-MM-DD) and an IANA `timezone`; both are rejected otherwise.

Response:

```json
{"version": "assistant-v1", "question_id": "creatine_water",
 "topics": ["creatine"], "escalation": false,
 "answers": [{"topic": "creatine", "text": "...",
              "evidence": [{"title": "...", "url": "https://...", "kind": "research"}]}],
 "intake_context": {"local_date": "...", "timezone": "...", "beverage_total_ml": 750.0,
                    "note": "Confirmed beverage volume, not a hydration measurement."},
 "provenance": {"mode": "local_rules", "provider": null, "model": null,
                "answer_origin": "reviewed_text"},
 "limitations": ["Wellness information, not medical advice.", "..."]}
```

`intake_context` is null unless consented. At most four answers; `scope` is
returned when nothing matches. Errors follow the prototype envelope; invalid
input returns 422 without echoing the question.

## Muse Wonder topic selection (suggested questions only)

`backend/wonder_assistant.py` builds one deterministic Wonder payload per
suggested question. Its strict schema offers only that question's allowed
topics (`ALLOWED`), never `urgent`, `medical_scope` or `scope`. The reply must
select 1+ allowed topics, including at least one of the question's reviewed
topics, with no other fields; anything else is rejected without repair.
Answers are still the reviewed texts in priority order. Provenance reads
`mode: meta_live`, `topic_selection: muse-wonder-1.0`,
`answer_origin: reviewed_text`, Georgio's account and the attempt ID, plus
tokens, latency and usage-derived cost.

`WonderHydrationGateway.answer(question_id, case_id, quote, input_reference)`
uses the same ledger flow as hydration explanations: approved case for the
exact payload, $0.25 per attempt, $30 aggregate, one in flight, settlement,
quarantine on any failure. `WonderMetaTransport` accepts exact scenario or
suggested-question payloads only. The /v1/assistant route still answers from
local rules; nothing dispatches from HTTP.

## Not in v1

No conversation memory, free-text generation, HealthKit context or
personalized targets. Free-text questions never reach Wonder.
