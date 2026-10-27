"""Reviewed single-shot Muse Spark 1.3 limits; never a billing authorization.

Sources: dev.meta.ai/docs/models and dev.meta.ai/docs/protocols/responses
(output-token limit), reviewed 2026-10-27. No hosted tools or history allowed.
Preflight counts and image dimensions are NOT a verified billing upper bound.
"""

MODEL_CONTEXT = 1_048_576
OUTPUT_LIMIT = 512  # Includes reasoning AND visible output, not 512 of each.
# The provider rejects input_tokens + max_output_tokens above the context limit.
# Avoid reserving the output budget twice. This still exceeds the $0.25 cap.
MAX_INPUT_TOKENS = MODEL_CONTEXT - OUTPUT_LIMIT
