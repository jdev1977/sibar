"""Anthropic Messages API adapter.

Written from Anthropic's documentation, read on 2026-11-25:

- https://platform.claude.com/docs/en/api/messages/create (request fields,
  response, stop reasons, usage, stream events)
- https://platform.claude.com/docs/en/api/overview (base URL, headers)
- https://platform.claude.com/docs/en/api/versioning (``2026-10-21``
  removes temperature, top_p and top_k)
- https://platform.claude.com/docs/en/api/errors (statuses, ``request-id``,
  ``x-should-retry``, retry-after, long requests)
- https://platform.claude.com/docs/en/build-with-claude/streaming (events)

Request: ``model``, ``max_tokens`` (required; set to the model's maximum from
models.yaml) and one user message. No ``system``, no ``thinking`` (the
default is adaptive thinking; Opus 5.5 cannot turn it off), no
``output_config`` (default effort), no sampling parameters.

Streaming is required here: the errors page says to avoid a large
``max_tokens`` without streaming, as idle connections can drop.

Usage: input is ``input_tokens + cache_creation_input_tokens +
cache_read_input_tokens`` (the documented total). ``output_tokens`` already
includes thinking ("the inclusive, authoritative total used for billing");
``output_tokens_details.thinking_tokens`` is the reasoning part.

Not verified against a live response (no key yet): the whole adapter; whether
128000 is accepted as ``max_tokens`` (models.yaml reads "128K" as 128000); and
whether a key needs ``anthropic-workspace-id`` (required for keys not scoped to
a workspace; set ANTHROPIC_WORKSPACE_ID to send it).
"""

import json

from runner.providers.base import (
    Adapter, ParseError, Prepared, Result, Tokens, add, clip, count, events,
    join_text, ok_or_empty, word_or_none,
)
from runner.transport import HttpRequest

URL = "https://api.anthropic.com/v1/messages"
VERSION = "2026-10-21"
TRUNCATED = frozenset({"max_tokens", "model_context_window_exceeded"})
OK = frozenset({"end_turn", "stop_sequence"})
RETRYABLE_TYPES = frozenset({"overloaded_error", "api_error", "rate_limit_error",
                             "timeout_error"})
ACCOUNT_CODES = frozenset({
    "enforced_spend_limit_reached", "contract_spend_limit_reached",
    "linked_organization_spend_limit_reached",
    "linked_organization_billing_unavailable", "billing_error",
    "authentication_error", "permission_error", "organization_on_hold",
})


def _index(data):
    index = data.get("index")
    if type(index) is not int:
        raise ParseError("a content block event has no whole-number index")
    return index


class AnthropicAdapter(Adapter):
    provider = "anthropic"
    docs = (
        ("https://platform.claude.com/docs/en/api/messages/create", "2026-11-25"),
        ("https://platform.claude.com/docs/en/api/overview", "2026-11-25"),
        ("https://platform.claude.com/docs/en/api/versioning", "2026-11-25"),
        ("https://platform.claude.com/docs/en/api/errors", "2026-11-25"),
        ("https://platform.claude.com/docs/en/build-with-claude/streaming",
         "2026-11-25"),
    )
    request_id_header = "request-id"
    account_codes = ACCOUNT_CODES
    reasoning_in_output = True  # output_tokens includes thinking

    def __init__(self, workspace_id=None):
        self.workspace_id = workspace_id or None

    def prepare(self, model, prompt, api_key):
        max_tokens = model.defaults.max_output_tokens
        if not max_tokens:
            raise ValueError(f"{model.id}: max_tokens is required by the API but "
                             "models.yaml has no max_output_tokens")
        body = {"model": model.id, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True}
        headers = {"authorization": f"Bearer {api_key}",
                   "anthropic-version": VERSION,
                   "content-type": "application/json"}
        if self.workspace_id:
            headers["anthropic-workspace-id"] = self.workspace_id
        settings = {"max_tokens": max_tokens, "stream": True,
                    "anthropic-version": VERSION}
        request = HttpRequest("POST", URL, headers, json.dumps(body).encode("utf-8"))
        return Prepared(request, settings, max_tokens)

    def parse_stream(self, response):
        request_id = self.header_request_id(response)
        message_id = model = stop_reason = stop_details = None
        usage, blocks, finished = {}, {}, False
        for name, data in events(response):
            if not isinstance(data, dict):
                raise ParseError(f"event {name!r} is not an object")
            kind = data.get("type", name)
            if kind == "message_start":
                message = data.get("message") or {}
                message_id = word_or_none(message.get("id"))
                model = word_or_none(message.get("model"))
                usage.update(message.get("usage") or {})
            elif kind == "content_block_start":
                block = data.get("content_block") or {}
                is_text = block.get("type") == "text"
                blocks[_index(data)] = {
                    "type": block.get("type"),
                    "text": (block.get("text") or "") if is_text else ""}
            elif kind == "content_block_delta":
                delta = data.get("delta") or {}
                if delta.get("type") == "text_delta":
                    block = blocks.setdefault(_index(data),
                                              {"type": "text", "text": ""})
                    if block["type"] == "text":
                        block["text"] += delta.get("text") or ""
            elif kind == "message_delta":
                delta = data.get("delta") or {}
                stop_reason = delta.get("stop_reason") or stop_reason
                stop_details = delta.get("stop_details") or stop_details
                usage.update({key: value for key, value in
                              (data.get("usage") or {}).items() if value is not None})
            elif kind == "message_stop":
                finished = True
                break
            elif kind == "error":
                return self._stream_error(data.get("error"), request_id or message_id)
            # ping and event types added later are ignored, as documented
        text = join_text(blocks[index]["text"] for index in sorted(blocks)
                         if blocks[index]["type"] == "text")
        fields = {"request_id": request_id or message_id, "model_id_returned": model,
                  "stop_reason": stop_reason}
        if not finished:
            return Result("failed", text=text or None, retryable=True,
                          error="the stream ended before message_stop", **fields)
        tokens = self._tokens(usage)
        if stop_reason in OK:
            return ok_or_empty(text, tokens=tokens, **fields)
        if stop_reason in TRUNCATED:
            return Result("truncated", text=text or None, tokens=tokens, **fields)
        if stop_reason == "refusal":
            details = stop_details if isinstance(stop_details, dict) else {}
            note = details.get("explanation") or details.get("category")
            return Result("refused", text=text or None, tokens=tokens,
                          error=clip(f"refused: {note}") if note else "refused",
                          **fields)
        return Result("failed", text=text or None, tokens=tokens, stop="model",
                      error=f"unexpected stop reason {stop_reason!r}", **fields)

    @staticmethod
    def _tokens(usage):
        cached = [count(usage.get(key)) or 0 for key in
                  ("cache_creation_input_tokens", "cache_read_input_tokens")]
        details = usage.get("output_tokens_details") or {}
        return Tokens(input=add(count(usage.get("input_tokens")), *cached),
                      output=count(usage.get("output_tokens")),
                      reasoning=count(details.get("thinking_tokens"))
                      if isinstance(details, dict) else None)

    def _stream_error(self, error, request_id):
        kind, code, message = self.error_fields(error)
        account = code in ACCOUNT_CODES or kind in ACCOUNT_CODES
        label = " ".join(dict.fromkeys(part for part in (kind, code) if part))
        return Result("failed", request_id=request_id,
                      error=clip(f"error in stream: {label}: {message}"),
                      retryable=not account and kind in RETRYABLE_TYPES,
                      stop="provider" if account else None)
