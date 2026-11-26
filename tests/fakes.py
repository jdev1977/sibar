"""Fake transport and provider responses for the runner tests (T0.5).

The streams follow the shapes in each provider's documentation (see the
adapter modules). Nothing here opens a socket.
"""

import json
import threading

from runner.transport import HttpRequest, NotSentError, SendError  # noqa: F401


class FakeResponse:
    def __init__(self, status=200, headers=None, lines=(), body=b"",
                 error_after=None):
        self.status = status
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._lines = [line if isinstance(line, bytes) else line.encode("utf-8")
                       for line in lines]
        self._body = body
        self._error_after = error_after  # raise SendError after this many lines
        self.closed = False

    def header(self, name):
        return self._headers.get(name.lower())

    def lines(self):
        for number, line in enumerate(self._lines):
            if self._error_after is not None and number >= self._error_after:
                raise SendError("the connection dropped (fake)")
            yield line
        if self._error_after is not None and self._error_after >= len(self._lines):
            raise SendError("the connection dropped (fake)")

    def read(self, limit=1024 * 1024):
        return self._body[:limit]

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


class FakeTransport:
    """Answers each request with ``handler(request, number)``: a FakeResponse,
    or an exception to raise. Records every request."""

    def __init__(self, handler):
        self.handler = handler
        self.requests = []
        self._lock = threading.Lock()

    def send(self, request):
        assert isinstance(request, HttpRequest)
        with self._lock:
            self.requests.append(request)
            number = len(self.requests)
        outcome = self.handler(request, number)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def bodies(self):
        return [json.loads(request.body) for request in self.requests]


def sse(*events):
    """SSE lines for (event name or None, data) pairs; data dicts become JSON."""
    lines = []
    for name, data in events:
        if name is not None:
            lines.append(f"event: {name}\n")
        payload = data if isinstance(data, str) else json.dumps(data)
        lines.append(f"data: {payload}\n")
        lines.append("\n")
    return lines


def chunks(text, size=7):
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


# --- Anthropic ----------------------------------------------------------------------


def anthropic_stream(text="Hello from Claude.", stop_reason="end_turn",
                     model="claude-opus-5-5", input_tokens=25, cache_read=3,
                     output_tokens=120, thinking_tokens=80, stop_details=None,
                     extra=(), end=True):
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_01ABC", "type": "message", "role": "assistant",
            "content": [], "model": model, "stop_reason": None,
            "stop_sequence": None, "usage": {
                "input_tokens": input_tokens, "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": cache_read, "output_tokens": 1}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "thinking",
                                                   "thinking": "", "signature": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "thinking_delta",
                                           "thinking": "Let me think."}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "signature_delta",
                                           "signature": "EqQB"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("content_block_start", {"type": "content_block_start", "index": 1,
                                 "content_block": {"type": "text", "text": ""}}),
        ("ping", {"type": "ping"}),
    ]
    events += [("content_block_delta", {"type": "content_block_delta", "index": 1,
                                        "delta": {"type": "text_delta", "text": part}})
               for part in chunks(text)]
    events += list(extra)
    events += [
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        ("message_delta", {"type": "message_delta", "delta": {
            "stop_reason": stop_reason, "stop_sequence": None,
            "stop_details": stop_details},
            "usage": {"output_tokens": output_tokens,
                      "output_tokens_details": {"thinking_tokens": thinking_tokens}}}),
    ]
    if end:
        events.append(("message_stop", {"type": "message_stop"}))
    return FakeResponse(200, {"request-id": "req_011ABC",
                              "content-type": "text/event-stream"}, sse(*events))


# --- OpenAI -------------------------------------------------------------------------


def openai_response(text="Hello from GPT.", status="completed", model="gpt-6.2-sol",
                    incomplete=None, error=None, refusal=None, input_tokens=30,
                    output_tokens=200, reasoning_tokens=150):
    content = []
    if text:
        content.append({"type": "output_text", "text": text, "annotations": [],
                        "logprobs": []})
    if refusal:
        content.append({"type": "refusal", "refusal": refusal})
    return {
        "id": "resp_67ccd3a9", "object": "response", "created_at": 1740855869,
        "status": status, "error": error,
        "incomplete_details": {"reason": incomplete} if incomplete else None,
        "model": model, "output": [
            {"id": "rs_1", "type": "reasoning", "summary": []},
            {"id": "msg_1", "type": "message", "role": "assistant",
             "status": "completed", "content": content}],
        "usage": {"input_tokens": input_tokens,
                  "input_tokens_details": {"cached_tokens": 0,
                                           "cache_write_tokens": 0},
                  "output_tokens": output_tokens,
                  "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
                  "total_tokens": input_tokens + output_tokens},
    }


def openai_stream(text="Hello from GPT.", status="completed", end=True, **kwargs):
    final = openai_response(text=text, status=status, **kwargs)
    started = dict(final, status="in_progress", output=[], usage=None)
    events = [("response.created", {"type": "response.created",
                                    "response": started, "sequence_number": 0}),
              ("response.in_progress", {"type": "response.in_progress",
                                        "response": started, "sequence_number": 1})]
    events += [("response.output_text.delta", {
        "type": "response.output_text.delta", "item_id": "msg_1",
        "output_index": 1, "content_index": 0, "delta": part,
        "sequence_number": n + 2}) for n, part in enumerate(chunks(text or ""))]
    terminal = {"completed": "response.completed", "incomplete": "response.incomplete",
                "failed": "response.failed"}.get(status, "response.completed")
    if end:
        events.append((terminal, {"type": terminal, "response": final,
                                  "sequence_number": 99}))
    return FakeResponse(200, {"x-request-id": "req_openai_1"}, sse(*events))


# --- Google -------------------------------------------------------------------------


def google_stream(text="Hello from Gemini.", status="completed",
                  model="gemini-4-hydrogen", input_tokens=11, output_tokens=90,
                  thought_tokens=245, end=True, extra=()):
    events = [
        ("interaction.created", {"interaction": {
            "id": "v1_ChdPU0F4", "status": "in_progress", "object": "interaction",
            "model": model}, "event_type": "interaction.created"}),
        ("interaction.status_update", {"interaction_id": "v1_ChdPU0F4",
                                       "status": "in_progress",
                                       "event_type": "interaction.status_update"}),
        ("step.start", {"index": 0, "step": {"type": "thought"},
                        "event_type": "step.start"}),
        ("step.delta", {"index": 0, "delta": {"signature": "abc",
                                              "type": "thought_signature"},
                        "event_type": "step.delta"}),
        ("step.stop", {"index": 0, "event_type": "step.stop"}),
        ("step.start", {"index": 1, "step": {"type": "model_output"},
                        "event_type": "step.start"}),
    ]
    events += [("step.delta", {"index": 1, "delta": {"text": part, "type": "text"},
                               "event_type": "step.delta"}) for part in chunks(text)]
    events += list(extra)
    events.append(("step.stop", {"index": 1, "event_type": "step.stop"}))
    if end:
        events.append(("interaction.completed", {"interaction": {
            "id": "v1_ChdPU0F4", "status": status, "usage": {
                "total_tokens": input_tokens + output_tokens + thought_tokens,
                "total_input_tokens": input_tokens,
                "input_tokens_by_modality": [{"modality": "text",
                                              "tokens": input_tokens}],
                "total_cached_tokens": 0, "total_output_tokens": output_tokens,
                "total_tool_use_tokens": 0, "total_thought_tokens": thought_tokens},
            "created": "2026-11-25T18:44:51Z", "updated": "2026-11-25T18:44:51Z",
            "service_tier": "standard", "object": "interaction", "model": model},
            "event_type": "interaction.completed"}))
        events.append(("done", "[DONE]"))
    return FakeResponse(200, {"content-type": "text/event-stream"}, sse(*events))


# --- DeepSeek -----------------------------------------------------------------------


def deepseek_stream(text="Hello from DeepSeek.", finish="stop",
                    model="deepseek-v4-pro", prompt_tokens=7, completion_tokens=40,
                    reasoning_tokens=25, end=True, usage=True):
    base = {"id": "071f229d-daa0", "object": "chat.completion.chunk",
            "created": 1793084907, "model": model, "system_fingerprint": "fp1"}

    def chunk(delta, finish_reason=None, chunk_usage=None):
        return (None, dict(base, choices=[{"index": 0, "delta": delta,
                                           "logprobs": None,
                                           "finish_reason": finish_reason}],
                           usage=chunk_usage))

    events = [chunk({"role": "assistant", "content": None,
                     "reasoning_content": "Thinking..."})]
    events += [chunk({"content": part}) for part in chunks(text)]
    if end:
        final_usage = {"prompt_tokens": prompt_tokens,
                       "completion_tokens": completion_tokens,
                       "total_tokens": prompt_tokens + completion_tokens,
                       "prompt_tokens_details": {"cached_tokens": 0},
                       "prompt_cache_hit_tokens": 0,
                       "prompt_cache_miss_tokens": prompt_tokens,
                       "completion_tokens_details": {
                           "reasoning_tokens": reasoning_tokens}} if usage else None
        events.append(chunk({"content": ""}, finish, final_usage))
        events.append((None, "[DONE]"))
    lines = [": keep-alive\n", "\n"] + sse(*events)
    return FakeResponse(200, {"content-type": "text/event-stream"}, lines)


STREAMS = {"anthropic": anthropic_stream, "openai": openai_stream,
           "google": google_stream, "deepseek": deepseek_stream}


def ok_stream(provider, text, model):
    """A successful stream from ``provider`` for ``model`` with ``text``."""
    return STREAMS[provider](text=text, model=model)


def error_response(status, error, headers=None, request_id_field=None):
    body = {"error": error}
    if request_id_field:
        body["request_id"] = request_id_field
    return FakeResponse(status, headers or {}, body=json.dumps(body).encode("utf-8"))
