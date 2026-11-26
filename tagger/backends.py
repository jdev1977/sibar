"""Batch APIs for tagging (T2.6): Anthropic Message Batches and OpenAI Batch.

Both are used through one interface, :class:`Backend`: ``create`` a job from
(custom_id, request body) pairs, ``retrieve`` it, tell whether it has
``ended``, read its ``results`` as :class:`Line` objects, and ``find`` a job
that a crashed run may have created. Requests go through ``runner.transport``
(a fake one in the tests); keys are sent only in headers, and error text
passes through ``runner.scrub``.

Written from the providers' documentation, read on 2026-11-26. **Nothing here
has been run against a live API (no keys exist yet).**

Anthropic (batch price: 50% of the standard rates):

- https://platform.claude.com/docs/en/build-with-claude/batch-processing
  (limits: 100,000 requests or 256 MB per batch; results within 24 hours,
  kept 29 days; ``custom_id`` matches ``^[a-zA-Z0-9_-]{1,64}$``; ``stream``
  is refused in a batch; results come in any order; errored, canceled and
  expired requests are not billed)
- https://platform.claude.com/docs/en/api/messages/batches/create (body
  ``{"requests": [{"custom_id", "params"}]}``; no batch-level metadata and
  no idempotency key; the MessageBatch object)
- https://platform.claude.com/docs/en/api/messages/batches/list
  (``GET /v1/messages/batches``, newest first, ``after_id``, ``limit`` up to
  1000, ``has_more``, ``last_id``)
- https://platform.claude.com/docs/en/api/messages/batches/results (one JSON
  line per request: ``succeeded`` with the Message, ``errored`` with an error
  object, ``canceled``, ``expired``)
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
  (``output_config.format``; works with batches; refusals and ``max_tokens``
  stops may not match the schema)
- https://platform.claude.com/docs/en/about-claude/pricing

OpenAI (batch price: half the standard rates):

- https://developers.openai.com/api/docs/guides/batch (``/v1/responses`` is
  supported; JSONL lines ``{custom_id, method, url, body}``; 50,000 requests
  and 200 MB per file; output lines ``{id, custom_id, response: {status_code,
  request_id, body}, error}``; expired requests go to the error file with
  code ``batch_expired``; completed requests of an expired batch are billed)
- https://developers.openai.com/api/reference/resources/batches/methods/create
  (``input_file_id``, ``endpoint``, ``completion_window: "24h"``,
  ``metadata`` of up to 16 pairs; statuses)
- https://developers.openai.com/api/reference/resources/batches/methods/list
- https://developers.openai.com/api/reference/resources/files/methods/create
  (multipart ``file`` and ``purpose: batch``)
- https://developers.openai.com/api/reference/resources/files/methods/content
- https://developers.openai.com/api/docs/guides/structured-outputs
  (``text.format`` with ``type: json_schema``, ``strict: true``)
- https://developers.openai.com/api/docs/pricing

Creating a job is never retried after the request may have reached the
provider: neither API takes an idempotency key, so a second create could
make a second, billed job. Such a create raises :class:`BackendError` with
``ambiguous`` set, and ``tagger/run.py`` reconciles it with ``find``.
"""

import datetime
import hashlib
import json
import random
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode, urlsplit

from runner.providers.anthropic import OK as ANTHROPIC_OK
from runner.providers.anthropic import TRUNCATED as ANTHROPIC_TRUNCATED
from runner.providers.anthropic import AnthropicAdapter
from runner.providers.base import Tokens, clip, join_text
from runner.providers.openai import OpenAIAdapter
from runner.retry import RetryPolicy, parse_retry_after
from runner.transport import HttpRequest, NotSentError, TransportError

MAX_JSON = 64 * 1024 * 1024
ANTHROPIC_HOST = "api.anthropic.com"
ANTHROPIC_BATCHES = f"https://{ANTHROPIC_HOST}/v1/messages/batches"
ANTHROPIC_VERSION = "2026-10-21"
OPENAI_HOST = "api.openai.com"
OPENAI_API = f"https://{OPENAI_HOST}/v1"
OPENAI_ENDPOINT = "/v1/responses"
SUBMISSION_KEY = "sibar_submission"   # OpenAI batch metadata key
# Statuses after which an HTTP answer means the job was not created.
_REJECTED = frozenset({400, 401, 402, 403, 404, 405, 413, 415, 422, 429})
_RETRY_GET = frozenset({408, 409, 429}) | frozenset(range(500, 600))
FIND_WINDOW = datetime.timedelta(minutes=15)
MAX_FIND_PAGES = 20


class BackendError(Exception):
    """A batch API call failed.

    ``ambiguous``: a create that may have made a job (do not create again
    before :meth:`Backend.find` has looked). ``stop``: the key or account
    cannot continue.
    """

    def __init__(self, message, *, ambiguous=False, stop=False, status=None):
        super().__init__(message)
        self.ambiguous = ambiguous
        self.stop = stop
        self.status = status


@dataclass(frozen=True)
class Line:
    """The result of one request of a job.

    ``attempted``: the request was processed (it counts toward the one
    retry). ``billed``: the provider may charge for it; ``tokens`` then holds
    what it reported (None if nothing was reported: charge the worst case).
    """

    custom_id: str
    attempted: bool
    billed: bool
    status: str                     # ok, refused, truncated, failed, not_run
    text: Optional[str] = None
    tokens: Optional[Tokens] = None
    stop_reason: Optional[str] = None
    error: Optional[str] = None
    request_id: Optional[str] = None
    model_id_returned: Optional[str] = None
    service_tier: Optional[str] = None


def parse_time(value):
    """An RFC 3339 time (text) or Unix seconds (number) as an aware datetime."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.datetime.fromtimestamp(value, datetime.timezone.utc)
    if isinstance(value, str):
        try:
            moment = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return moment if moment.tzinfo else moment.replace(tzinfo=datetime.timezone.utc)
    return None


class Backend:
    provider = ""
    max_requests = 0
    max_bytes = 0

    def __init__(self, transport, api_key, scrub, *, retry=None, sleep=time.sleep,
                 rng=None, workspace_id=None):
        self.transport = transport
        self._key = api_key
        self.scrub = scrub
        self.retry = retry or RetryPolicy()
        self.sleep = sleep
        self.rng = rng or random.Random()
        self.workspace_id = workspace_id

    # --- HTTP ---------------------------------------------------------------

    def _headers(self, content_type="application/json"):  # pragma: no cover
        raise NotImplementedError

    def _send(self, method, url, body=b"", content_type="application/json"):
        request = HttpRequest(method, url, self._headers(content_type), body)
        return self.transport.send(request)

    def _error(self, response, what):
        try:
            data = json.loads(response.read(MAX_JSON) or b"null")
        except ValueError:
            data = None
        error = data.get("error") if isinstance(data, dict) else None
        detail = ""
        if isinstance(error, dict):
            detail = " ".join(str(error.get(k)) for k in ("type", "code", "message")
                              if error.get(k))
        return self.scrub(clip(f"{what}: HTTP {response.status} {detail}".strip()))

    def get_json(self, url):
        """GET a JSON document, retrying what may succeed when sent again."""
        attempts = 0
        while True:
            attempts += 1
            retry_after, problem = None, None
            try:
                with self._send("GET", url) as response:
                    if response.status == 200:
                        return json.loads(response.read(MAX_JSON))
                    problem = self._error(response, f"GET {urlsplit(url).path}")
                    if response.status not in _RETRY_GET:
                        raise BackendError(problem, status=response.status,
                                           stop=response.status in (401, 402, 403))
                    retry_after = parse_retry_after(response.header("retry-after"))
            except TransportError as error:
                problem = self.scrub(str(error))
            except ValueError as error:
                raise BackendError(f"GET {urlsplit(url).path}: not JSON: {error}") from None
            delay = self.retry.delay(attempts, retry_after, self.rng) \
                if self.retry.may_retry(attempts) else None
            if delay is None:
                raise BackendError(problem)
            self.sleep(delay)

    def get_lines(self, url):
        """GET a JSON Lines body; yield each parsed line. Not retried midway:
        the caller reads results again from the start if this fails."""
        try:
            with self._send("GET", url) as response:
                if response.status != 200:
                    raise BackendError(self._error(response, f"GET {urlsplit(url).path}"),
                                       status=response.status)
                for raw in response.lines():
                    if raw.strip():
                        yield json.loads(raw)
        except TransportError as error:
            raise BackendError(self.scrub(str(error))) from None
        except ValueError as error:
            raise BackendError(f"a result line is not JSON: {error}") from None

    def post_create(self, url, body, content_type="application/json"):
        """POST that creates something billable: never sent twice."""
        try:
            response = self._send("POST", url, body, content_type)
        except NotSentError as error:
            raise BackendError(f"not sent: {self.scrub(str(error))}") from None
        except TransportError as error:
            raise BackendError(f"no answer, the job may exist: {self.scrub(str(error))}",
                               ambiguous=True) from None
        with response:
            if response.status == 200:
                try:
                    return json.loads(response.read(MAX_JSON))
                except (ValueError, TransportError) as error:
                    raise BackendError(f"the answer could not be read; the job may "
                                       f"exist: {error}", ambiguous=True) from None
            problem = self._error(response, f"POST {urlsplit(url).path}")
            rejected = response.status in _REJECTED
            raise BackendError(problem, ambiguous=not rejected, status=response.status,
                               stop=response.status in (401, 402, 403))

    # --- the interface -------------------------------------------------------

    def create(self, submission_id, requests):  # pragma: no cover
        raise NotImplementedError

    def retrieve(self, batch_id):  # pragma: no cover
        raise NotImplementedError

    def ended(self, batch):  # pragma: no cover
        raise NotImplementedError

    def never_ran(self, batch):
        """True when the job ended without processing any request."""
        return False

    def results(self, batch):  # pragma: no cover
        raise NotImplementedError

    def find(self, submission_id, count, sent_at):  # pragma: no cover
        raise NotImplementedError

    def describe(self, batch):  # pragma: no cover
        raise NotImplementedError


# --- Anthropic ------------------------------------------------------------------


def anthropic_line(data):
    """A :class:`Line` from one line of a Message Batch's results."""
    custom_id = data.get("custom_id")
    result = data.get("result") or {}
    kind = result.get("type")
    if kind == "succeeded":
        message = result.get("message") or {}
        text = join_text(block.get("text") or "" for block in message.get("content") or []
                         if isinstance(block, dict) and block.get("type") == "text")
        usage = message.get("usage") or {}
        tokens = AnthropicAdapter._tokens(usage)
        stop = message.get("stop_reason")
        if stop in ANTHROPIC_OK and text.strip():
            status, error = "ok", None
        elif stop in ANTHROPIC_TRUNCATED:
            status, error = "truncated", f"stopped: {stop}"
        elif stop == "refusal":
            status, error = "refused", "refused"
        else:
            status, error = "failed", f"stop reason {stop!r}, text {bool(text.strip())}"
        return Line(custom_id, True, True, status, text or None, tokens, stop, error,
                    message.get("id"), message.get("model"), usage.get("service_tier"))
    if kind == "errored":
        error = (result.get("error") or {}).get("error") or {}
        return Line(custom_id, True, False, "failed",
                    error=clip(f"errored: {error.get('type')}: {error.get('message')}"),
                    request_id=(result.get("error") or {}).get("request_id"))
    if kind in ("canceled", "expired"):
        return Line(custom_id, False, False, "not_run", error=kind)
    return Line(custom_id, False, True, "failed", error=f"unknown result type {kind!r}")


class AnthropicBatches(Backend):
    provider = "anthropic"
    max_requests = 100_000
    max_bytes = 256 * 1000 * 1000

    def _headers(self, content_type="application/json"):
        headers = {"authorization": f"Bearer {self._key}",
                   "anthropic-version": ANTHROPIC_VERSION,
                   "content-type": content_type}
        if self.workspace_id:
            headers["anthropic-workspace-id"] = self.workspace_id
        return headers

    @staticmethod
    def body(requests):
        return json.dumps({"requests": [{"custom_id": c, "params": p}
                                        for c, p in requests]},
                          ensure_ascii=True, separators=(",", ":")).encode("ascii")

    def create(self, submission_id, requests):
        return self.post_create(ANTHROPIC_BATCHES, self.body(requests))

    def retrieve(self, batch_id):
        return self.get_json(f"{ANTHROPIC_BATCHES}/{batch_id}")

    def ended(self, batch):
        return batch.get("processing_status") == "ended"

    def results(self, batch):
        url = batch.get("results_url")
        # The key is only ever sent to the API host.
        if not (isinstance(url, str) and urlsplit(url).scheme == "https"
                and urlsplit(url).hostname == ANTHROPIC_HOST):
            url = f"{ANTHROPIC_BATCHES}/{batch['id']}/results"
        for data in self.get_lines(url):
            yield anthropic_line(data)

    def find(self, submission_id, count, sent_at):
        """Jobs created within 15 minutes of ``sent_at`` holding ``count``
        requests (the API keeps no metadata of ours to match on)."""
        found, after = [], None
        for _ in range(MAX_FIND_PAGES):
            query = {"limit": 1000, **({"after_id": after} if after else {})}
            page = self.get_json(f"{ANTHROPIC_BATCHES}?{urlencode(query)}")
            older = False
            for batch in page.get("data") or []:
                created = parse_time(batch.get("created_at"))
                if created is None:
                    continue
                if created < sent_at - FIND_WINDOW:
                    older = True
                    continue
                total = sum(v for v in (batch.get("request_counts") or {}).values()
                            if type(v) is int)
                if created <= sent_at + FIND_WINDOW and total == count:
                    found.append(batch["id"])
            if older or not page.get("has_more") or not page.get("last_id"):
                return found
            after = page["last_id"]
        return found

    def describe(self, batch):
        counts = batch.get("request_counts") or {}
        return (f"{batch.get('processing_status')}; " + ", ".join(
            f"{k} {v}" for k, v in sorted(counts.items())))


# --- OpenAI ---------------------------------------------------------------------

_OPENAI_ENDED = frozenset({"completed", "failed", "expired", "cancelled"})


def openai_line(data):
    """A :class:`Line` from one line of an OpenAI batch output or error file."""
    custom_id = data.get("custom_id")
    response = data.get("response") or {}
    error = data.get("error") or {}
    code = error.get("code") if isinstance(error, dict) else None
    if code == "batch_expired":
        return Line(custom_id, False, False, "not_run", error="batch_expired")
    body = response.get("body") if isinstance(response, dict) else None
    if response.get("status_code") == 200 and isinstance(body, dict):
        result = OpenAIAdapter().parse_response(body, response.get("request_id"))
        return Line(custom_id, True, True, result.status, result.text, result.tokens,
                    result.stop_reason, result.error, result.request_id,
                    result.model_id_returned, body.get("service_tier"))
    # A failed request: charged as reported, or at its worst case if no usage
    # is given (the batch guide does not say failed requests are free).
    tokens = None
    if isinstance(body, dict) and isinstance(body.get("usage"), dict):
        tokens = OpenAIAdapter().parse_response(body).tokens
    message = (body or {}).get("error") if isinstance(body, dict) else None
    message = message or error
    text = message.get("message") if isinstance(message, dict) else message
    return Line(custom_id, True, True, "failed", tokens=tokens,
                error=clip(f"HTTP {response.get('status_code')}: {code or ''} {text}"),
                request_id=response.get("request_id"))


class OpenAIBatches(Backend):
    provider = "openai"
    max_requests = 50_000
    max_bytes = 200 * 1000 * 1000

    def _headers(self, content_type="application/json"):
        return {"authorization": f"Bearer {self._key}", "content-type": content_type}

    @staticmethod
    def jsonl(requests):
        return b"".join(json.dumps({"custom_id": c, "method": "POST",
                                    "url": OPENAI_ENDPOINT, "body": p},
                                   ensure_ascii=True, separators=(",", ":")
                                   ).encode("ascii") + b"\n" for c, p in requests)

    def upload(self, data):
        mark = "sibar-" + hashlib.sha256(data).hexdigest()[:32]
        if mark.encode() in data:  # pragma: no cover - a hash collision
            raise BackendError("the upload boundary occurs in the file")
        body = (f"--{mark}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\n"
                f"batch\r\n--{mark}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"tagging.jsonl\"\r\nContent-Type: application/jsonl\r\n\r\n"
                ).encode("ascii") + data + f"\r\n--{mark}--\r\n".encode("ascii")
        try:
            uploaded = self.post_create(f"{OPENAI_API}/files", body,
                                        f"multipart/form-data; boundary={mark}")
        except BackendError as error:
            # A file costs nothing and makes no job: never ambiguous.
            raise BackendError(f"upload failed: {error}", stop=error.stop) from None
        if not isinstance(uploaded, dict) or not uploaded.get("id"):
            raise BackendError("the upload answer has no file id")
        return uploaded["id"]

    def create(self, submission_id, requests):
        file_id = self.upload(self.jsonl(requests))
        body = json.dumps({"input_file_id": file_id, "endpoint": OPENAI_ENDPOINT,
                           "completion_window": "24h",
                           "metadata": {SUBMISSION_KEY: submission_id}}).encode("ascii")
        return self.post_create(f"{OPENAI_API}/batches", body)

    def retrieve(self, batch_id):
        return self.get_json(f"{OPENAI_API}/batches/{batch_id}")

    def ended(self, batch):
        return batch.get("status") in _OPENAI_ENDED

    def never_ran(self, batch):
        # "failed": the input file did not pass validation; nothing ran.
        return batch.get("status") == "failed"

    def results(self, batch):
        for name in ("output_file_id", "error_file_id"):
            if batch.get(name):
                for data in self.get_lines(f"{OPENAI_API}/files/{batch[name]}/content"):
                    yield openai_line(data)

    def find(self, submission_id, count, sent_at):
        """Jobs whose metadata names ``submission_id``."""
        found, after = [], None
        for _ in range(MAX_FIND_PAGES):
            query = {"limit": 100, **({"after": after} if after else {})}
            page = self.get_json(f"{OPENAI_API}/batches?{urlencode(query)}")
            older = False
            for batch in page.get("data") or []:
                if (batch.get("metadata") or {}).get(SUBMISSION_KEY) == submission_id:
                    found.append(batch["id"])
                created = parse_time(batch.get("created_at"))
                if created is not None and created < sent_at - datetime.timedelta(days=1):
                    older = True
            if older or not page.get("has_more") or not page.get("last_id"):
                return found
            after = page["last_id"]
        return found

    def describe(self, batch):
        counts = batch.get("request_counts") or {}
        return f"{batch.get('status')}; " + ", ".join(
            f"{k} {v}" for k, v in sorted(counts.items()))


BACKENDS = {"anthropic": AnthropicBatches, "openai": OpenAIBatches}


def backend_for(provider, transport, api_key, scrub, **kwargs):
    try:
        return BACKENDS[provider](transport, api_key, scrub, **kwargs)
    except KeyError:
        raise BackendError(f"no batch backend for provider {provider!r}") from None
