"""OpenAI Responses API adapter.

Written from OpenAI's documentation, read on 2026-11-25:

- https://developers.openai.com/api/reference/resources/responses/methods/create
  (request fields and defaults, response object, statuses, usage)
- https://developers.openai.com/api/reference/resources/responses/streaming-events
  (``response.completed`` / ``.incomplete`` / ``.failed`` carry the whole
  response; ``error`` events)
- https://developers.openai.com/api/reference/overview (Bearer auth,
  ``x-request-id``)
- https://developers.openai.com/api/docs/guides/error-codes (429 codes that
  retrying cannot fix, 503 overload, Retry-After)
- https://developers.openai.com/api/docs/guides/reasoning (reasoning tokens
  are billed as output tokens; ``max_output_tokens`` covers them)
- https://developers.openai.com/api/docs/models/gpt-6.2-sol (128,000 max
  output tokens)

Request: ``model`` and ``input`` (a plain string is "equivalent to a text
input with the user role"). No ``instructions``, no ``reasoning`` (default
effort), no ``temperature``/``top_p``, no ``max_output_tokens`` (optional;
the request is then bounded by the model's documented maximum output, which
the ledger reserves). ``store`` is left at its default (true).

Streaming is chosen, not required: the API documents no limit for a
non-streamed response, but an uncapped reasoning response can run for many
minutes and a stream keeps the connection active. The final event holds the
complete response object, which is parsed as a non-streamed one would be.

Usage: ``input_tokens`` (cached included); ``output_tokens`` includes
reasoning (the documented example has ``total = input + output`` with
reasoning inside output); ``output_tokens_details.reasoning_tokens`` is the
reasoning part. Output is billed as at least ``total_tokens - input_tokens``.
Cache writes (``input_tokens_details.cache_write_tokens``) are priced above
plain input and are not modelled by the ledger.

Serving: the response's ``service_tier`` is recorded; anything but
``default`` (or ``auto``) is priced differently, so the runner stops calling
OpenAI. The project must stay on the default tier.

Not verified against a live response (no key yet): the whole adapter, and
the output bound that applies when ``max_output_tokens`` is omitted (stated
neither way; models.yaml's 128000 is assumed).
"""

import json

from runner.providers.base import (
    Adapter, ParseError, Prepared, Result, Tokens, billed_output, clip, count,
    events, join_text, ok_or_empty, serving, word_or_none,
)
from runner.transport import HttpRequest

URL = "https://api.openai.com/v1/responses"
TERMINAL = frozenset({"response.completed", "response.incomplete",
                      "response.failed"})
REFUSED_CODES = frozenset({"invalid_prompt", "bio_policy",
                           "misalignment_policy_violation"})
RETRYABLE_CODES = frozenset({"server_error", "rate_limit_exceeded", "slow_down",
                             "server_is_overloaded"})
# The response's service_tier is "the processing mode actually used". Only
# "default" is billed at the list rates in models.yaml; "auto" is accepted as
# the project default (which must be left at "default").
STANDARD_SERVING = {"service_tier": {"default", "auto"}}
ACCOUNT_CODES = frozenset({
    "insufficient_quota", "credit_balance_exhausted",
    "organization_spend_limit_exceeded", "project_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
})


class OpenAIAdapter(Adapter):
    provider = "openai"
    docs = (
        ("https://developers.openai.com/api/reference/resources/responses/methods/create",
         "2026-11-25"),
        ("https://developers.openai.com/api/reference/resources/responses/streaming-events",
         "2026-11-25"),
        ("https://developers.openai.com/api/reference/overview", "2026-11-25"),
        ("https://developers.openai.com/api/docs/guides/error-codes", "2026-11-25"),
        ("https://developers.openai.com/api/docs/guides/reasoning", "2026-11-25"),
    )
    request_id_header = "x-request-id"
    account_codes = ACCOUNT_CODES
    reasoning_in_output = True

    def prepare(self, model, prompt, api_key):
        body = {"model": model.id, "input": prompt, "stream": True}
        headers = {"authorization": f"Bearer {api_key}",
                   "content-type": "application/json"}
        request = HttpRequest("POST", URL, headers, json.dumps(body).encode("utf-8"))
        return Prepared(request, {"stream": True}, None)

    def parse_stream(self, response):
        request_id = self.header_request_id(response)
        final = None
        for name, data in events(response):
            if not isinstance(data, dict):
                continue  # a "[DONE]" marker, if one is ever sent
            kind = data.get("type", name)
            if kind in TERMINAL:
                final = data.get("response")
                if not isinstance(final, dict):
                    raise ParseError(f"{kind} has no response object")
                break
            if kind == "error":
                code, message = data.get("code"), data.get("message")
                account = code in ACCOUNT_CODES
                return Result("failed", request_id=request_id,
                              error=clip(f"error in stream: {code}: {message}"),
                              retryable=not account and code not in REFUSED_CODES,
                              stop="provider" if account else None)
            # deltas and other events: the terminal event repeats everything
        if final is None:
            return Result("failed", request_id=request_id, retryable=True,
                          error="the stream ended before the response finished")
        return self.parse_response(final, request_id)

    def parse_response(self, final, request_id=None):
        """A :class:`Result` from a complete Response object."""
        texts, refusals = [], []
        for item in final.get("output") or []:
            if isinstance(item, dict) and item.get("type") == "message":
                for part in item.get("content") or []:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "output_text":
                        texts.append(part.get("text") or "")
                    elif part.get("type") == "refusal":
                        refusals.append(part.get("refusal") or "")
        text = join_text(texts)
        usage = final.get("usage") or {}
        details = usage.get("output_tokens_details") or {}
        input_tokens = count(usage.get("input_tokens"))
        tokens = Tokens(input=input_tokens,
                        output=billed_output(count(usage.get("output_tokens")),
                                             count(usage.get("total_tokens")),
                                             input_tokens),
                        reasoning=count(details.get("reasoning_tokens")))
        status = final.get("status")
        incomplete = (final.get("incomplete_details") or {}).get("reason")
        reported, premium = serving({"service_tier": final.get("service_tier")},
                                    STANDARD_SERVING)
        fields = {"request_id": request_id or word_or_none(final.get("id")),
                  "model_id_returned": word_or_none(final.get("model")),
                  "stop_reason": incomplete or status, "tokens": tokens,
                  "reported": reported, "premium": premium}
        if status == "completed":
            if refusals and not text.strip():
                return Result("refused", text=join_text(refusals) or None,
                              error="refused", **fields)
            return ok_or_empty(text, **fields)
        if status == "incomplete":
            if incomplete == "max_output_tokens":
                return Result("truncated", text=text or None, **fields)
            if incomplete == "content_filter":
                return Result("refused", text=text or None,
                              error="incomplete: content_filter", **fields)
            return Result("failed", text=text or None, stop="model",
                          error=f"incomplete: {incomplete}", **fields)
        if status == "failed":
            error = final.get("error") or {}
            code, message = error.get("code"), error.get("message")
            if code in REFUSED_CODES:
                return Result("refused", text=text or None,
                              error=clip(f"failed: {code}: {message}"), **fields)
            return Result("failed", text=text or None,
                          retryable=code in RETRYABLE_CODES,
                          error=clip(f"failed: {code}: {message}"), **fields)
        return Result("failed", text=text or None, retryable=True,
                      error=f"the response ended with status {status!r}", **fields)
