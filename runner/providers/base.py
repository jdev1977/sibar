"""What every provider adapter shares (T0.5).

An adapter turns (model, prompt, key) into one HTTP request with no system
prompt, no sampling parameters and the provider's default reasoning settings,
and turns the streamed response into a :class:`Result`. Every adapter streams:
see each module for why streaming is needed or chosen there.

Token counts in a :class:`Tokens` are normalised across providers:

- ``input``: the whole prompt, cached parts included;
- ``output``: every generated token billed at the output rate, **reasoning
  included**, whatever the provider's own ``output`` field holds;
- ``reasoning``: the reasoning part of ``output``, or None if not reported.
"""

import json
from dataclasses import dataclass
from typing import Mapping, Optional

from runner.record import _is_word
from runner.retry import parse_retry_after
from runner.sse import iter_sse

MAX_ERROR_BODY = 64 * 1024
MAX_ERROR_TEXT = 1000
# Statuses that may succeed when sent again.
RETRYABLE_STATUSES = frozenset({408, 409, 429}) | frozenset(range(500, 600))
# Account-level refusals: no call to this provider can succeed in this run.
PROVIDER_STOP_STATUSES = frozenset({401, 402, 403})
# Request-level refusals that would repeat for every prompt to this model.
MODEL_STOP_STATUSES = frozenset({400, 404, 405, 413, 415, 422})


class ParseError(ValueError):
    """The response did not have the documented shape."""


@dataclass(frozen=True)
class Prepared:
    """A request ready to send, with what the record and ledger need."""

    request: object  # runner.transport.HttpRequest
    settings: Mapping  # stored as the record's settings
    max_output_tokens: Optional[int]  # the limit sent, or None if none is


@dataclass(frozen=True)
class Tokens:
    input: Optional[int]
    output: Optional[int]  # includes reasoning
    reasoning: Optional[int]

    @property
    def complete(self):
        """Input and output are both known, so the ledger can charge them."""
        return self.input is not None and self.output is not None


@dataclass(frozen=True)
class Result:
    """The outcome of one request.

    ``stop`` is None, ``"model"`` (stop sending to this model: the same error
    would repeat) or ``"provider"`` (stop sending to the provider: the key or
    account cannot make calls).
    """

    status: str  # ok, failed, refused or truncated (record statuses)
    text: Optional[str] = None
    stop_reason: Optional[str] = None
    tokens: Optional[Tokens] = None
    model_id_returned: Optional[str] = None
    request_id: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = False
    retry_after: Optional[float] = None
    stop: Optional[str] = None


def word_or_none(value):
    """``value`` if it is text with no spaces (a record id field), else None."""
    return value if isinstance(value, str) and _is_word(value) else None


def count(value):
    """A token count, or None if the provider gave none or a bad one."""
    return value if type(value) is int and value >= 0 else None


def add(*values):
    """The sum of counts, or None if any is unknown."""
    if any(value is None for value in values):
        return None
    return sum(values)


def clip(text, limit=MAX_ERROR_TEXT):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def join_text(pieces):
    """Text from separate blocks, in order, with a blank line between blocks
    so that a code fence ending one block still closes. Empty pieces are
    skipped; text inside a block is never changed."""
    return "\n\n".join(piece for piece in pieces if piece)


def events(response):
    """(event name, parsed JSON or the raw string) for each SSE event."""
    for event in iter_sse(response.lines()):
        data = event.data
        if data.strip() == "[DONE]":
            yield event.event, "[DONE]"
            continue
        try:
            yield event.event, json.loads(data)
        except ValueError:
            raise ParseError(f"an event {event.event!r} is not JSON") from None


def ok_or_empty(text, **fields):
    """An ok result, or failed if there is no text (an ok record needs it)."""
    if text and text.strip():
        return Result("ok", text=text, **fields)
    return Result("failed", text=text or None,
                  error="the response finished but holds no text", **fields)


class Adapter:
    """Base class: subclasses set the class attributes and two methods."""

    provider = ""
    docs = ()  # (url, date checked) pairs the adapter follows
    request_id_header = None
    # Error codes (or types) that mean the account cannot continue: billing,
    # spend limits, quotas. Never retried; they stop the provider.
    account_codes = frozenset()

    def prepare(self, model, prompt, api_key):  # pragma: no cover
        raise NotImplementedError

    def parse_stream(self, response):  # pragma: no cover
        raise NotImplementedError

    def parse(self, response):
        """The :class:`Result` of an HTTP response (any status)."""
        if response.status >= 400:
            return self.error_result(response)
        if response.status != 200:
            return Result("failed", error=f"unexpected HTTP status "
                          f"{response.status}", stop="model",
                          request_id=self.header_request_id(response))
        return self.parse_stream(response)

    def header_request_id(self, response):
        if not self.request_id_header:
            return None
        return word_or_none(response.header(self.request_id_header))

    def error_fields(self, error):
        """(type, code, message) from a provider's ``error`` object."""
        if not isinstance(error, dict):
            return None, None, None
        details = error.get("details")
        code = error.get("code")
        if not isinstance(code, str):
            code = error.get("status") if isinstance(error.get("status"), str) else None
        if code is None and isinstance(details, dict):
            code = details.get("error_code")
        kind = error.get("type")
        return (kind if isinstance(kind, str) else None,
                code if isinstance(code, str) else None,
                error.get("message"))

    def error_result(self, response):
        """A failed :class:`Result` for an HTTP error status."""
        status = response.status
        try:
            body = json.loads(response.read(MAX_ERROR_BODY) or b"null")
        except ValueError:
            body = None
        error = body.get("error") if isinstance(body, dict) else None
        kind, code, message = self.error_fields(error)
        request_id = self.header_request_id(response)
        if request_id is None and isinstance(body, dict):
            request_id = word_or_none(body.get("request_id"))
        should_retry = (response.header("x-should-retry") or "").strip().lower()
        account = code in self.account_codes or kind in self.account_codes
        if account or status in PROVIDER_STOP_STATUSES:
            retryable = False
        elif should_retry in ("true", "false"):
            retryable = should_retry == "true"
        else:
            retryable = status in RETRYABLE_STATUSES
        stop = None
        if account or status in PROVIDER_STOP_STATUSES:
            stop = "provider"
        elif status in MODEL_STOP_STATUSES and not retryable:
            stop = "model"
        label = " ".join(dict.fromkeys(part for part in (kind, code) if part))
        text = f"HTTP {status}" + (f" {label}" if label else "")
        if message:
            text += f": {message}"
        return Result(
            "failed", error=clip(text), retryable=retryable, stop=stop,
            retry_after=parse_retry_after(response.header("retry-after")),
            request_id=request_id)
