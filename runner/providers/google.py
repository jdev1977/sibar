"""Google Gemini Interactions API adapter.

Written from Google's documentation, read on 2026-11-25:

- https://aistudio.google.com/api-reference/interactions-api/create-interaction
  (endpoint, request fields, Interaction resource, statuses, usage, stream
  event types)
- https://aistudio.google.com/docs/text-generation (``x-goog-api-key``,
  ``Api-Revision: 2026-05-20``, ``?alt=sse`` with ``"stream": true``; Gemini 4
  and 3.6+ ignore temperature, top_p and top_k)
- https://aistudio.google.com/docs/streaming (event flow;
  ``interaction.completed`` has usage but no steps; ``error`` events)
- https://aistudio.google.com/docs/long-decode (with ``background`` false and
  no ``max_output_tokens``, Gemini 4 output is limited to 65,536 tokens of
  thinking and output; non-streamed requests get 10 minutes, streamed ones 20)
- https://aistudio.google.com/docs/api-errors (error codes, blocked codes)
- https://aistudio.google.com/docs/troubleshooting (retry 429, 408, 5xx)
- https://aistudio.google.com/docs/pricing (output price includes thinking)

Request: ``model`` and ``input`` (a string). No ``system_instruction``, no
``generation_config`` (default thinking level and output limit), no
``background`` and no ``max_output_tokens``, so long decode never starts and
models.yaml's 65536 bounds the request. The generateContent API is labelled
legacy, so it is not used. The ``Api-Revision`` header pins the API
behaviour; it sets no model parameter.

Streaming is chosen because a non-streamed hop is cut at 10 minutes and a
streamed one at 20.

Usage: ``total_output_tokens`` excludes thinking (the documented example has
``total = input + output + thought``), so output here is
``total_output_tokens + total_thought_tokens``, and reasoning is
``total_thought_tokens``. Input is ``total_input_tokens`` plus
``total_tool_use_tokens`` (none expected without tools). Output is billed as
at least ``total_tokens`` minus both, since ``total_tokens`` also counts
"other internal tokens".

Serving: the interaction's ``service_tier`` is recorded; ``flex`` or
``priority`` is priced differently, so the runner stops calling Google.

Not verified against a live response (no key yet): the whole adapter; whether
Gemini 3.5 Flash-Lite also stops at 65,536 when no limit is sent (its model
page gives that output limit); and the request id (no header is documented,
so the interaction id is used).
"""

import json

from runner.providers.base import (
    Adapter, ParseError, Prepared, Result, Tokens, add, billed_output, clip,
    count, events, join_text, ok_or_empty, serving, word_or_none,
)
from runner.transport import HttpRequest

URL = "https://generativelanguage.googleapis.com/v1beta/interactions?alt=sse"
API_REVISION = "2026-05-20"
REFUSED_CODES = frozenset({
    "safety", "recitation", "language", "prohibited_content", "spii",
    "blocklist", "content_blocked", "image_safety", "image_prohibited_content",
    "image_recitation", "image_other",
})
RETRYABLE_CODES = frozenset({
    "rate_limit_exceeded", "too_many_requests", "api_error",
    "service_unavailable", "deadline_exceeded", "gateway_timeout", "aborted",
    "internal", "unavailable", "resource_exhausted",
})
# Service tiers are flex, standard and priority; only standard is billed at
# the list rates in models.yaml.
STANDARD_SERVING = {"service_tier": {"standard"}}
ACCOUNT_CODES = frozenset({"quota_exceeded", "payment_required",
                           "authentication", "permission_denied",
                           "failed_precondition"})


class GoogleAdapter(Adapter):
    provider = "google"
    docs = (
        ("https://aistudio.google.com/api-reference/interactions-api/create-interaction",
         "2026-11-25"),
        ("https://aistudio.google.com/docs/text-generation", "2026-11-25"),
        ("https://aistudio.google.com/docs/streaming", "2026-11-25"),
        ("https://aistudio.google.com/docs/long-decode", "2026-11-25"),
        ("https://aistudio.google.com/docs/api-errors", "2026-11-25"),
        ("https://aistudio.google.com/docs/troubleshooting", "2026-11-25"),
    )
    account_codes = ACCOUNT_CODES
    reasoning_in_output = False  # the provider's output count excludes thinking

    def prepare(self, model, prompt, api_key):
        body = {"model": model.id, "input": prompt, "stream": True}
        headers = {"x-goog-api-key": api_key, "content-type": "application/json",
                   "api-revision": API_REVISION}
        settings = {"stream": True, "alt": "sse", "api-revision": API_REVISION}
        request = HttpRequest("POST", URL, headers, json.dumps(body).encode("utf-8"))
        return Prepared(request, settings, None)

    def error_fields(self, error):
        kind, code, message = super().error_fields(error)
        return kind, code.lower() if code else code, message

    def parse_stream(self, response):
        interaction_id = model = status = tier = None
        usage, steps, texts, finished = None, {}, {}, False
        for name, data in events(response):
            if data == "[DONE]":
                break
            if not isinstance(data, dict):
                raise ParseError(f"event {name!r} is not an object")
            kind = data.get("event_type", name)
            if kind in ("interaction.created", "interaction.completed"):
                interaction = data.get("interaction") or {}
                interaction_id = word_or_none(interaction.get("id")) or interaction_id
                model = word_or_none(interaction.get("model")) or model
                status = interaction.get("status") or status
                tier = interaction.get("service_tier") or tier
                if kind == "interaction.completed":
                    usage = interaction.get("usage") or {}
                    finished = True
            elif kind == "interaction.status_update":
                status = data.get("status") or status
            elif kind == "step.start":
                steps[data.get("index")] = (data.get("step") or {}).get("type")
            elif kind == "step.delta":
                delta = data.get("delta") or {}
                index = data.get("index")
                if (delta.get("type") == "text"
                        and steps.get(index, "model_output") == "model_output"):
                    texts[index] = texts.get(index, "") + (delta.get("text") or "")
            elif kind == "error":
                return self._stream_error(data.get("error"), interaction_id)
            # step.stop and later additions are ignored
        order = sorted(texts, key=lambda index: (not isinstance(index, int), str(index)))
        text = join_text(texts[index] for index in order)
        reported, premium = serving({"service_tier": tier}, STANDARD_SERVING)
        fields = {"request_id": interaction_id, "model_id_returned": model,
                  "stop_reason": status, "reported": reported, "premium": premium}
        if not finished:
            return Result("failed", text=text or None, retryable=True,
                          error="the stream ended before interaction.completed",
                          **fields)
        prompt = count(usage.get("total_input_tokens"))
        tool_use = count(usage.get("total_tool_use_tokens")) or 0
        tokens = Tokens(
            input=add(prompt, tool_use),
            output=billed_output(
                add(count(usage.get("total_output_tokens")),
                    count(usage.get("total_thought_tokens")) or 0),
                count(usage.get("total_tokens")), prompt, tool_use),
            reasoning=count(usage.get("total_thought_tokens")))
        if status == "completed":
            return ok_or_empty(text, tokens=tokens, **fields)
        if status in ("incomplete", "requires_continuation"):
            return Result("truncated", text=text or None, tokens=tokens, **fields)
        if status == "requires_action":
            return Result("failed", text=text or None, tokens=tokens, stop="model",
                          error="the interaction asked for a tool call", **fields)
        return Result("failed", text=text or None, tokens=tokens, retryable=True,
                      error=f"the interaction ended with status {status!r}", **fields)

    def _stream_error(self, error, request_id):
        _, code, message = self.error_fields(error)
        if code in REFUSED_CODES:
            return Result("refused", request_id=request_id, stop_reason=code,
                          error=clip(f"blocked: {code}: {message}"))
        account = code in ACCOUNT_CODES
        return Result("failed", request_id=request_id,
                      error=clip(f"error in stream: {code}: {message}"),
                      retryable=not account and code in RETRYABLE_CODES,
                      stop="provider" if account else None)
