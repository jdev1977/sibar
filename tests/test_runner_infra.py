"""Server-sent events, retries, rate limits and key scrubbing (T0.5).

No network: everything here runs on in-memory data and fake clocks.
"""

import datetime
import random
import threading

import pytest

from runner.ratelimit import RateLimiter
from runner.retry import RetryPolicy, parse_retry_after
from runner.scrub import Scrubber
from runner.sse import SseEvent, iter_sse


# --- Server-sent events -------------------------------------------------------------


def events(*lines):
    return list(iter_sse(line.encode("utf-8") for line in lines))


def test_named_events_with_data_are_parsed():
    assert events("event: message_start\n", 'data: {"a": 1}\n', "\n",
                  "event: ping\n", "data: {}\n", "\n") == [
        SseEvent("message_start", '{"a": 1}'), SseEvent("ping", "{}")]


def test_data_only_events_default_to_message():
    assert events("data: x\n", "\n") == [SseEvent("message", "x")]


def test_multiple_data_lines_join_with_newlines():
    assert events("data: a\n", "data:b\n", "data:  c\n", "\n") == [
        SseEvent("message", "a\nb\n c")]


def test_comments_and_unknown_fields_are_ignored():
    assert events(": keep-alive\n", "id: 7\n", "retry: 100\n", "data: x\n", "\n",
                  ": keep-alive\n", "\n") == [SseEvent("message", "x")]


def test_crlf_line_endings_work():
    assert events("event: a\r\n", "data: b\r\n", "\r\n") == [SseEvent("a", "b")]


def test_blank_lines_without_data_dispatch_nothing():
    assert events("\n", "\n", "event: lonely\n", "\n") == []


def test_a_final_event_without_a_blank_line_is_kept_if_its_line_ended():
    assert events("data: [DONE]\n") == [SseEvent("message", "[DONE]")]


def test_a_final_line_cut_mid_way_is_dropped():
    assert events("data: {\"a\": 1}\n", "\n", 'data: {"b"') == [
        SseEvent("message", '{"a": 1}')]


def test_a_byte_order_mark_is_ignored():
    assert events("﻿data: x\n", "\n") == [SseEvent("message", "x")]


def test_event_name_resets_after_each_event():
    assert events("event: a\n", "data: 1\n", "\n", "data: 2\n", "\n") == [
        SseEvent("a", "1"), SseEvent("message", "2")]


# --- Retry policy -------------------------------------------------------------------


class FixedRandom(random.Random):
    def __init__(self, value):
        super().__init__(0)
        self.value = value

    def uniform(self, low, high):
        return low + (high - low) * self.value


@pytest.mark.parametrize("attempt,low,high", [
    (1, 1.0, 2.0), (2, 2.0, 4.0), (3, 4.0, 8.0), (10, 30.0, 60.0),
])
def test_backoff_grows_exponentially_with_jitter_and_a_cap(attempt, low, high):
    policy = RetryPolicy(max_attempts=20, base_delay=2.0, max_delay=60.0)
    assert policy.delay(attempt, None, FixedRandom(0.0)) == low
    assert policy.delay(attempt, None, FixedRandom(1.0)) == high


def test_jitter_spreads_delays():
    policy = RetryPolicy()
    rng = random.Random(1)
    assert len({policy.delay(3, None, rng) for _ in range(20)}) > 10


def test_retry_after_is_a_minimum():
    policy = RetryPolicy(base_delay=2.0)
    assert policy.delay(1, 30.0, FixedRandom(1.0)) == 30.0
    assert policy.delay(3, 0.5, FixedRandom(1.0)) == 8.0


def test_a_retry_after_beyond_the_limit_means_do_not_retry_now():
    policy = RetryPolicy(max_retry_after=120.0)
    assert policy.delay(1, 121.0, FixedRandom(0.5)) is None
    assert policy.delay(1, 120.0, FixedRandom(0.5)) == 120.0


def test_attempts_are_limited():
    policy = RetryPolicy(max_attempts=3)
    assert policy.may_retry(1) and policy.may_retry(2)
    assert not policy.may_retry(3)


@pytest.mark.parametrize("bad", [
    {"max_attempts": 0}, {"base_delay": -1}, {"max_delay": 0.5, "base_delay": 1},
    {"max_retry_after": -1},
])
def test_a_retry_policy_must_make_sense(bad):
    with pytest.raises(ValueError):
        RetryPolicy(**bad)


NOW = datetime.datetime(2026, 11, 25, 12, 0, 0, tzinfo=datetime.timezone.utc)


@pytest.mark.parametrize("value,expected", [
    ("30", 30.0), (" 2.5 ", 2.5), ("0", 0.0), ("-5", 0.0),
    ("Wed, 25 Nov 2026 12:01:00 GMT", 60.0),
    ("Wed, 25 Nov 2026 11:59:00 GMT", 0.0),
    (None, None), ("", None), ("soon", None), ("nan", None), ("inf", None),
])
def test_retry_after_headers_are_read(value, expected):
    assert parse_retry_after(value, now=NOW) == expected


# --- Rate limits --------------------------------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []
        self.lock = threading.Lock()

    def time(self):
        with self.lock:
            return self.now

    def sleep(self, seconds):
        with self.lock:
            self.sleeps.append(seconds)
            self.now += seconds


def test_requests_are_spaced_to_the_rate():
    clock = FakeClock()
    limiter = RateLimiter(30, clock=clock.time, sleep=clock.sleep)  # one per 2 s
    for _ in range(4):
        limiter.acquire()
    assert clock.sleeps == [2.0, 2.0, 2.0]


def test_no_wait_when_requests_are_already_slow():
    clock = FakeClock()
    limiter = RateLimiter(60, clock=clock.time, sleep=clock.sleep)
    limiter.acquire()
    clock.now += 5
    limiter.acquire()
    assert clock.sleeps == []


def test_threads_share_one_limit():
    clock = FakeClock()
    limiter = RateLimiter(60, clock=clock.time, sleep=lambda s: None)
    slots = []
    lock = threading.Lock()

    def take():
        waited = limiter.acquire()
        with lock:
            slots.append(waited)

    threads = [threading.Thread(target=take) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(slots) == [float(n) for n in range(10)]


@pytest.mark.parametrize("rate", [0, -1, float("nan"), "10"])
def test_the_rate_must_be_positive(rate):
    with pytest.raises(ValueError):
        RateLimiter(rate)


# --- Key scrubbing ------------------------------------------------------------------


def fake_key(prefix="sk-" + "ant-"):
    return prefix + "Zq7" + "x" * 37


def test_known_keys_are_replaced_everywhere():
    key = fake_key()
    scrub = Scrubber([key])
    text = f"bad key {key} and again {key[:-1]}{key[-1]}"
    assert key not in scrub(text)
    assert scrub(text).count("[redacted]") == 2


def test_key_shaped_strings_are_replaced_even_when_unknown():
    scrub = Scrubber()
    for secret in (fake_key("sk-" + "proj-"), "AIza" + "B" * 35,
                   "Bearer " + "t" * 30):
        assert secret not in scrub(f"error: {secret}!")


def test_short_values_are_not_treated_as_keys():
    scrub = Scrubber(["abc", ""])
    assert scrub("abc def") == "abc def"


def test_keys_can_be_added_later_and_non_text_is_converted():
    scrub = Scrubber()
    key = fake_key("dsk-")
    scrub.add(key)
    assert scrub(ValueError(f"oops {key}")) == "oops [redacted]"
    assert scrub(None) == "None"
