"""DeepSeek Chat Completions API adapter (OpenAI format).

Written from DeepSeek's documentation, read on 2026-11-25:

- https://api-docs.deepseek.com/api/create-chat-completion (request fields,
  ``max_tokens`` default, response and chunk shapes, finish reasons, usage;
  the last chunk before ``data: [DONE]`` carries usage even without
  ``stream_options``)
- https://api-docs.deepseek.com/ (base URL ``https://api.deepseek.com``,
  Bearer auth)
- https://api-docs.deepseek.com/guides/thinking_mode (thinking is on by
  default at effort high; temperature has no effect in thinking mode)
- https://api-docs.deepseek.com/quick_start/error_codes (400, 401, 402, 422,
  429, 500, 503)
- https://api-docs.deepseek.com/quick_start/rate_limit (``: keep-alive``
  comments while waiting; the connection closes if inference has not started
  after 10 minutes)
- https://api-docs.deepseek.com/quick_start/pricing (billing is by total
  input and output tokens)

Request: ``model`` and one user message. No system message, no ``thinking``
or ``reasoning_effort`` (default: thinking on, effort high), no sampling
parameters and no ``max_tokens``. When unset the documented default is "64K"
in thinking mode at the default effort; the ledger reserves models.yaml's
393216, the most any request can produce, which is above that.

Streaming is chosen for a steady sign of life on long generations; the API
allows either.

Usage: ``prompt_tokens`` (equals cache hits plus misses); ``completion_tokens``
includes reasoning: ``completion_tokens_details`` is a "breakdown of tokens
used in a completion", ``total_tokens`` is prompt plus completion, and
billing is by input plus output tokens. Output is billed as at least
``total_tokens - prompt_tokens``. ``reasoning_tokens`` is the reasoning part.
The chain of thought (``reasoning_content``) is not stored. No service tier is
documented, so none is recorded.

Not verified against a live response (no key yet): the whole adapter; the
exact default output limit; whether the server sends an error object inside
a stream (handled if it does); and any request id header (none is
documented, so the completion id is used).
"""

import json

from runner.providers.base import (
    Adapter, ParseError, Prepared, Result, Tokens, billed_output, clip, count,
    events, ok_or_empty, word_or_none,
)
from runner.transport import HttpRequest

URL = "https://api.deepseek.com/chat/completions"
ACCOUNT_CODES = frozenset({"insufficient_balance", "invalid_api_key",
                           "authentication_error"})


class DeepSeekAdapter(Adapter):
    provider = "deepseek"
    docs = (
        ("https://api-docs.deepseek.com/api/create-chat-completion", "2026-11-25"),
        ("https://api-docs.deepseek.com/", "2026-11-25"),
        ("https://api-docs.deepseek.com/guides/thinking_mode", "2026-11-25"),
        ("https://api-docs.deepseek.com/quick_start/error_codes", "2026-11-25"),
        ("https://api-docs.deepseek.com/quick_start/rate_limit", "2026-11-25"),
        ("https://api-docs.deepseek.com/quick_start/pricing", "2026-11-25"),
    )
    request_id_header = "x-request-id"  # used if present; not documented
    account_codes = ACCOUNT_CODES
    reasoning_in_output = True

    def prepare(self, model, prompt, api_key):
        body = {"model": model.id,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True}
        headers = {"authorization": f"Bearer {api_key}",
                   "content-type": "application/json"}
        request = HttpRequest("POST", URL, headers, json.dumps(body).encode("utf-8"))
        return Prepared(request, {"stream": True}, None)

    def parse_stream(self, response):
        request_id = self.header_request_id(response)
        completion_id = model = finish = None
        usage, pieces, done = None, [], False
        for name, data in events(response):
            if data == "[DONE]":
                done = True
                break
            if not isinstance(data, dict):
                raise ParseError(f"event {name!r} is not an object")
            if "error" in data:
                _, code, message = self.error_fields(data.get("error"))
                return Result("failed", request_id=request_id or completion_id,
                              retryable=True,
                              error=clip(f"error in stream: {code}: {message}"))
            completion_id = word_or_none(data.get("id")) or completion_id
            model = word_or_none(data.get("model")) or model
            for choice in data.get("choices") or []:
                if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                    continue
                delta = choice.get("delta") or {}
                if isinstance(delta.get("content"), str):
                    pieces.append(delta["content"])
                finish = choice.get("finish_reason") or finish
            if isinstance(data.get("usage"), dict):
                usage = data["usage"]
        text = "".join(pieces)
        fields = {"request_id": request_id or completion_id,
                  "model_id_returned": model, "stop_reason": finish}
        if finish is None or not (done or usage is not None):
            return Result("failed", text=text or None, retryable=True,
                          error="the stream ended before the completion finished",
                          **fields)
        usage = usage or {}
        details = usage.get("completion_tokens_details") or {}
        prompt = count(usage.get("prompt_tokens"))
        tokens = Tokens(input=prompt,
                        output=billed_output(count(usage.get("completion_tokens")),
                                             count(usage.get("total_tokens")), prompt),
                        reasoning=count(details.get("reasoning_tokens"))
                        if isinstance(details, dict) else None)
        if finish == "stop":
            return ok_or_empty(text, tokens=tokens, **fields)
        if finish == "length":
            return Result("truncated", text=text or None, tokens=tokens, **fields)
        if finish == "content_filter":
            return Result("refused", text=text or None, tokens=tokens,
                          error="content_filter", **fields)
        if finish in ("insufficient_system_resource", "aborted"):
            return Result("failed", text=text or None, tokens=tokens,
                          retryable=True, error=f"finish_reason {finish}", **fields)
        return Result("failed", text=text or None, tokens=tokens, stop="model",
                      error=f"unexpected finish_reason {finish!r}", **fields)
