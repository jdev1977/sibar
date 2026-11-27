"""Provider adapters (T0.5): requests built and responses read.

All responses are fakes shaped like the providers' documented examples; no
request leaves the machine. Nothing here proves an adapter works against the
live API.
"""

import json
from pathlib import Path

import pytest

from fakes import (FakeResponse, anthropic_stream, deepseek_stream, error_response,
                   google_stream, openai_stream, sse)
from runner.models import load_models
from runner.providers import ADAPTERS, adapter_for
from runner.providers.base import ParseError, Tokens

ROOT = Path(__file__).resolve().parents[1]
MODELS = load_models(ROOT / "models.yaml")
KEY = "test-" + "k" * 30
PROMPT = "Make a website for a bakery."
SAMPLING = {"temperature", "top_p", "top_k", "system", "system_instruction",
            "instructions", "thinking", "reasoning", "reasoning_effort",
            "output_config", "generation_config", "background", "seed"}


def prepare(model_id, prompt=PROMPT):
    model = MODELS.get(model_id)
    return adapter_for(model.provider).prepare(model, prompt, KEY)


def parse(provider, response):
    return adapter_for(provider).parse(response)


# --- Requests -----------------------------------------------------------------------


def test_every_listed_provider_has_an_adapter():
    assert {model.provider for model in MODELS.models} <= set(ADAPTERS)


def test_each_adapter_cites_its_documentation_and_date():
    for adapter in ADAPTERS.values():
        assert adapter.docs
        for url, checked in adapter.docs:
            assert url.startswith("https://") and checked == "2026-11-25"


@pytest.mark.parametrize("model", MODELS.models, ids=lambda m: m.id)
def test_requests_send_only_what_the_api_requires(model):
    prepared = adapter_for(model.provider).prepare(model, PROMPT, KEY)
    body = json.loads(prepared.request.body)
    assert body["model"] == model.id
    assert not SAMPLING & set(body)
    assert prepared.request.method == "POST"
    assert prepared.request.url.startswith("https://")
    assert KEY not in prepared.request.url
    assert KEY not in json.dumps(prepared.settings)
    assert prepared.settings["stream"] is True and body["stream"] is True
    assert KEY in " ".join(prepared.request.headers.values())


def test_anthropic_request():
    prepared = prepare("claude-opus-5-5")
    body = json.loads(prepared.request.body)
    assert prepared.request.url == "https://api.anthropic.com/v1/messages"
    assert body == {"model": "claude-opus-5-5", "max_tokens": 128000,
                    "messages": [{"role": "user", "content": PROMPT}],
                    "stream": True}
    assert prepared.request.headers["authorization"] == f"Bearer {KEY}"
    assert prepared.request.headers["anthropic-version"] == "2026-10-21"
    assert "anthropic-workspace-id" not in prepared.request.headers
    assert prepared.settings == {"max_tokens": 128000, "stream": True,
                                 "anthropic-version": "2026-10-21"}
    assert prepared.max_output_tokens == 128000


def test_anthropic_workspace_header_is_optional():
    model = MODELS.get("claude-haiku-5-5")
    prepared = adapter_for("anthropic", workspace_id="wrkspc_01").prepare(
        model, PROMPT, KEY)
    assert prepared.request.headers["anthropic-workspace-id"] == "wrkspc_01"
    assert "wrkspc_01" not in json.dumps(prepared.settings)


def test_openai_request():
    prepared = prepare("gpt-6.2-sol")
    assert prepared.request.url == "https://api.openai.com/v1/responses"
    assert json.loads(prepared.request.body) == {
        "model": "gpt-6.2-sol", "input": PROMPT, "stream": True, "store": False}
    assert prepared.request.headers["authorization"] == f"Bearer {KEY}"
    assert prepared.settings == {"stream": True, "store": False}
    assert prepared.max_output_tokens is None


def test_google_request():
    prepared = prepare("gemini-4-hydrogen")
    assert prepared.request.url == (
        "https://generativelanguage.googleapis.com/v1beta/interactions?alt=sse")
    assert json.loads(prepared.request.body) == {
        "model": "gemini-4-hydrogen", "input": PROMPT, "stream": True,
        "store": False}
    assert prepared.request.headers["x-goog-api-key"] == KEY
    assert prepared.request.headers["api-revision"] == "2026-05-20"
    assert prepared.settings == {"stream": True, "store": False, "alt": "sse",
                                 "api-revision": "2026-05-20"}
    assert prepared.max_output_tokens is None


def test_deepseek_request():
    prepared = prepare("deepseek-v4-pro")
    assert prepared.request.url == "https://api.deepseek.com/chat/completions"
    assert json.loads(prepared.request.body) == {
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": PROMPT}], "stream": True}
    assert prepared.max_output_tokens is None


def test_prompts_are_sent_exactly():
    prompt = "Line one\n  Line two with é and \"quotes\"\t"
    for model_id in ("claude-opus-5-5", "gpt-6-luna", "gemini-3.5-flash-lite",
                     "deepseek-flash"):
        body = json.loads(prepare(model_id, prompt).request.body)
        sent = body.get("input") or body["messages"][0]["content"]
        assert sent == prompt


# --- Successful responses -------------------------------------------------------------


def test_anthropic_ok():
    result = parse("anthropic", anthropic_stream(text="Hi " * 10))
    assert result.status == "ok" and result.text == "Hi " * 10
    assert result.tokens == Tokens(input=28, output=120, reasoning=80)
    assert (result.model_id_returned, result.request_id, result.stop_reason) == (
        "claude-opus-5-5", "req_011ABC", "end_turn")
    assert result.error is None


def test_openai_ok():
    result = parse("openai", openai_stream(text="Hello there"))
    assert result.status == "ok" and result.text == "Hello there"
    assert result.tokens == Tokens(input=30, output=200, reasoning=150)
    assert (result.model_id_returned, result.request_id, result.stop_reason) == (
        "gpt-6.2-sol", "req_openai_1", "completed")


def test_google_ok_adds_thinking_to_output():
    result = parse("google", google_stream(text="Hi from Gemini"))
    assert result.status == "ok" and result.text == "Hi from Gemini"
    assert result.tokens == Tokens(input=11, output=90 + 245, reasoning=245)
    assert (result.model_id_returned, result.request_id, result.stop_reason) == (
        "gemini-4-hydrogen", "v1_ChdPU0F4", "completed")


def test_deepseek_ok():
    result = parse("deepseek", deepseek_stream(text="Hi from DeepSeek"))
    assert result.status == "ok" and result.text == "Hi from DeepSeek"
    assert result.tokens == Tokens(input=7, output=40, reasoning=25)
    assert (result.model_id_returned, result.request_id, result.stop_reason) == (
        "deepseek-v4-pro", "071f229d-daa0", "stop")


def test_text_from_separate_blocks_is_joined_with_a_blank_line():
    extra = [("content_block_start", {"type": "content_block_start", "index": 2,
                                      "content_block": {"type": "text", "text": ""}}),
             ("content_block_delta", {"type": "content_block_delta", "index": 2,
                                      "delta": {"type": "text_delta",
                                                "text": "Second."}})]
    result = parse("anthropic", anthropic_stream(text="First.\n```", extra=extra))
    assert result.text == "First.\n```\n\nSecond."


def test_anthropic_blocks_are_ordered_by_number_not_text():
    extra = [("content_block_start", {"type": "content_block_start", "index": 10,
                                      "content_block": {"type": "text", "text": "Ten"}})]
    extra += [("content_block_start", {"type": "content_block_start", "index": 2,
                                       "content_block": {"type": "text", "text": "Two"}})]
    result = parse("anthropic", anthropic_stream(text="One", extra=extra))
    assert result.text == "One\n\nTwo\n\nTen"


def test_unknown_events_are_ignored():
    extra = [("brand_new_event", {"type": "brand_new_event", "x": 1})]
    assert parse("anthropic", anthropic_stream(extra=extra)).status == "ok"
    extra = [("step.mystery", {"event_type": "step.mystery"})]
    assert parse("google", google_stream(extra=extra)).status == "ok"


# --- Billed output from reported totals ----------------------------------------------------


@pytest.mark.parametrize("provider,response,output", [
    # total minus input is larger than the output count: bill the difference
    ("openai", openai_stream(input_tokens=30, output_tokens=200, total_tokens=290), 260),
    ("google", google_stream(input_tokens=11, output_tokens=90, thought_tokens=245,
                             total_tokens=400), 389),
    ("deepseek", deepseek_stream(prompt_tokens=7, completion_tokens=40,
                                 total_tokens=60), 53),
    # a smaller total never lowers the output count
    ("openai", openai_stream(input_tokens=30, output_tokens=200, total_tokens=100), 200),
    ("google", google_stream(output_tokens=90, thought_tokens=245, total_tokens=5), 335),
    ("deepseek", deepseek_stream(completion_tokens=40, total_tokens=1), 40),
])
def test_output_is_billed_as_at_least_total_minus_input(provider, response, output):
    result = parse(provider, response)
    assert result.status == "ok"
    assert result.tokens.output == output


# --- Service tier and inference region ------------------------------------------------------


def test_the_reported_tier_is_returned_and_standard_is_not_premium():
    result = parse("anthropic", anthropic_stream())
    assert result.reported == {"service_tier": "standard", "inference_geo": "global",
                               "speed": "standard"}
    assert result.premium is None
    assert parse("openai", openai_stream()).reported == {"service_tier": "default"}
    assert parse("google", google_stream()).reported == {"service_tier": "standard"}
    for provider, response in (("openai", openai_stream()),
                               ("google", google_stream()),
                               ("deepseek", deepseek_stream())):
        assert parse(provider, response).premium is None


@pytest.mark.parametrize("provider,response,word", [
    ("anthropic", anthropic_stream(service_tier="priority"), "priority"),
    ("anthropic", anthropic_stream(speed="fast"), "fast"),
    ("anthropic", anthropic_stream(inference_geo="us"), "us"),
    ("openai", openai_stream(service_tier="priority"), "priority"),
    ("openai", openai_stream(service_tier="flex"), "flex"),
    ("openai", openai_stream(service_tier="scale"), "scale"),
    ("google", google_stream(service_tier="priority"), "priority"),
    ("google", google_stream(service_tier="flex"), "flex"),
])
def test_a_non_standard_tier_is_flagged_as_premium(provider, response, word):
    result = parse(provider, response)
    assert result.status == "ok"
    assert result.premium and word in result.premium


def test_http_errors_carry_their_status():
    assert parse("google", error_response(429, {"code": "too_many_requests",
                                                "message": "x"})).http_status == 429
    assert parse("anthropic", anthropic_stream()).http_status is None


# --- Truncated and refused -------------------------------------------------------------


@pytest.mark.parametrize("provider,response,stop_reason", [
    ("anthropic", anthropic_stream(stop_reason="max_tokens"), "max_tokens"),
    ("anthropic", anthropic_stream(stop_reason="model_context_window_exceeded"),
     "model_context_window_exceeded"),
    ("openai", openai_stream(status="incomplete", incomplete="max_output_tokens"),
     "max_output_tokens"),
    ("google", google_stream(status="incomplete"), "incomplete"),
    ("google", google_stream(status="requires_continuation"), "requires_continuation"),
    ("deepseek", deepseek_stream(finish="length"), "length"),
])
def test_length_limits_are_truncated(provider, response, stop_reason):
    result = parse(provider, response)
    assert result.status == "truncated"
    assert result.stop_reason == stop_reason
    assert result.text and result.tokens.complete


@pytest.mark.parametrize("provider,response", [
    ("anthropic", anthropic_stream(text="", stop_reason="refusal",
                                   stop_details={"type": "refusal", "category": "cyber",
                                                 "explanation": "Not allowed."})),
    ("openai", openai_stream(text="", refusal="I can't help with that.")),
    ("openai", openai_stream(status="incomplete", incomplete="content_filter")),
    ("openai", openai_stream(text="", status="failed",
                             error={"code": "bio_policy", "message": "blocked"})),
    ("deepseek", deepseek_stream(text="", finish="content_filter")),
    ("google", FakeResponse(200, {}, sse(("error", {
        "error": {"code": "prohibited_content", "message": "Blocked."},
        "event_type": "error"})))),
])
def test_refusals_are_refused(provider, response):
    result = parse(provider, response)
    assert result.status == "refused"
    assert result.error and not result.retryable


def test_an_openai_refusal_keeps_the_refusal_text():
    result = parse("openai", openai_stream(text="", refusal="I can't help."))
    assert result.text == "I can't help."


@pytest.mark.parametrize("provider,response", [
    ("anthropic", anthropic_stream(text="")),
    ("openai", openai_stream(text="")),
    ("google", google_stream(text="")),
    ("deepseek", deepseek_stream(text="")),
    ("anthropic", anthropic_stream(text="  \n ")),
])
def test_a_finished_response_without_text_is_failed_not_ok(provider, response):
    result = parse(provider, response)
    assert result.status == "failed" and result.error
    assert not result.retryable


@pytest.mark.parametrize("provider,response", [
    ("anthropic", anthropic_stream(stop_reason="tool_use")),
    ("anthropic", anthropic_stream(stop_reason="pause_turn")),
    ("deepseek", deepseek_stream(finish="tool_calls")),
    ("google", google_stream(status="requires_action")),
    ("openai", openai_stream(status="incomplete", incomplete="max_messages")),
])
def test_unexpected_endings_fail_and_stop_the_model(provider, response):
    result = parse(provider, response)
    assert result.status == "failed" and result.stop == "model"
    assert not result.retryable


# --- Interrupted streams ------------------------------------------------------------------


@pytest.mark.parametrize("provider,response", [
    ("anthropic", anthropic_stream(end=False)),
    ("openai", openai_stream(end=False)),
    ("google", google_stream(end=False)),
    ("deepseek", deepseek_stream(end=False)),
])
def test_a_stream_that_stops_early_is_a_retryable_failure(provider, response):
    result = parse(provider, response)
    assert result.status == "failed" and result.retryable
    assert result.tokens is None or not result.tokens.complete


@pytest.mark.parametrize("provider,data,retryable", [
    ("anthropic", {"type": "error", "error": {"type": "overloaded_error",
                                              "message": "Overloaded"}}, True),
    ("anthropic", {"type": "error", "error": {"type": "invalid_request_error",
                                              "message": "bad"}}, False),
    ("openai", {"type": "error", "code": "server_error", "message": "x",
                "sequence_number": 3}, True),
    ("google", {"error": {"code": "gateway_timeout", "message": "Deadline expired"},
                "event_type": "error"}, True),
    ("google", {"error": {"code": "not_found", "message": "x"},
                "event_type": "error"}, False),
    ("deepseek", {"error": {"message": "x", "type": "server_error"}}, True),
])
def test_errors_inside_a_stream(provider, data, retryable):
    response = FakeResponse(200, {}, sse(("error", data)))
    result = parse(provider, response)
    assert result.status == "failed"
    assert result.retryable is retryable
    assert result.tokens is None


@pytest.mark.parametrize("provider", sorted(ADAPTERS))
def test_a_body_that_is_not_a_stream_is_not_retried(provider):
    response = FakeResponse(200, {"content-type": "application/json; charset=utf-8"},
                            body=b'{"id": "x"}')
    result = parse(provider, response)
    assert result.status == "failed" and not result.retryable
    assert result.stop == "model" and "application/json" in result.error


@pytest.mark.parametrize("provider", sorted(ADAPTERS))
def test_a_stream_that_is_not_json_is_a_parse_error(provider):
    response = FakeResponse(200, {}, ["event: x\n", "data: {not json\n", "\n"])
    with pytest.raises(ParseError):
        parse(provider, response)


# --- HTTP errors ----------------------------------------------------------------------------


ANTHROPIC_ERROR = {"type": "rate_limit_error", "message": "Slow down"}


@pytest.mark.parametrize("provider", sorted(ADAPTERS))
@pytest.mark.parametrize("status,retryable,stop", [
    (429, True, None), (500, True, None), (503, True, None), (529, True, None),
    (504, True, None), (408, True, None), (400, False, "model"), (404, False, "model"),
    (422, False, "model"), (401, False, "provider"), (402, False, "provider"),
    (403, False, "provider"),
])
def test_http_errors_are_classified(provider, status, retryable, stop):
    response = error_response(status, {"type": "some_error", "message": "nope"},
                              headers={"retry-after": "12"})
    result = parse(provider, response)
    assert result.status == "failed"
    assert result.retryable is retryable
    assert result.stop == stop
    assert result.retry_after == 12.0
    assert f"HTTP {status}" in result.error and "nope" in result.error
    assert result.tokens is None


@pytest.mark.parametrize("provider,error", [
    ("anthropic", {"type": "rate_limit_error", "message": "limit",
                   "details": {"error_code": "enforced_spend_limit_reached"}}),
    ("openai", {"message": "No credit", "type": "insufficient_quota",
                "code": "credit_balance_exhausted"}),
    ("openai", {"message": "Spend", "type": "rate_limit_error",
                "code": "project_spend_limit_exceeded"}),
    ("google", {"code": "quota_exceeded", "message": "Daily quota"}),
])
def test_spend_and_quota_limits_are_not_retried_and_stop_the_provider(provider, error):
    result = parse(provider, error_response(429, error))
    assert not result.retryable and result.stop == "provider"


def test_anthropic_x_should_retry_is_followed():
    no = error_response(500, ANTHROPIC_ERROR, headers={"x-should-retry": "false"})
    assert not parse("anthropic", no).retryable
    yes = error_response(400, ANTHROPIC_ERROR, headers={"x-should-retry": "true"})
    assert parse("anthropic", yes).retryable
    assert parse("anthropic", yes).stop is None


def test_anthropic_request_id_from_header_or_body():
    with_header = error_response(529, {"type": "overloaded_error", "message": "x"},
                                 headers={"request-id": "req_H"})
    assert parse("anthropic", with_header).request_id == "req_H"
    in_body = error_response(529, {"type": "overloaded_error", "message": "x"},
                             request_id_field="req_B")
    assert parse("anthropic", in_body).request_id == "req_B"


def test_an_error_body_that_is_not_json_still_gives_a_result():
    response = FakeResponse(502, {}, body=b"<html>Bad gateway</html>")
    result = parse("openai", response)
    assert result.status == "failed" and result.retryable
    assert result.error == "HTTP 502"


def test_google_legacy_error_shape():
    response = error_response(429, {"code": 429, "message": "Resource exhausted",
                                    "status": "RESOURCE_EXHAUSTED"})
    result = parse("google", response)
    assert result.retryable and "resource_exhausted" in result.error


def test_a_request_id_with_spaces_is_dropped():
    response = anthropic_stream()
    response._headers["request-id"] = "has a space"
    assert parse("anthropic", response).request_id == "msg_01ABC"


def test_long_error_messages_are_shortened():
    response = error_response(400, {"type": "invalid_request_error",
                                    "message": "x" * 5000})
    assert len(parse("anthropic", response).error) <= 1000
