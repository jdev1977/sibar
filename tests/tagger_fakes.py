"""In-memory Anthropic Message Batches and OpenAI Batch APIs for the tagger
tests (T2.6), served through ``tests.fakes.FakeTransport``. Their shapes
follow the documentation cited in ``tagger/backends.py``. No network."""

import json
from urllib.parse import urlsplit

from runner.record import utc_now
from runner.transport import SendError
from tests.fakes import FakeResponse


def schema_of(params):
    if "output_config" in params:
        return params["output_config"]["format"]["schema"]
    return params["text"]["format"]["schema"]


def first_answers(params, gate="answers"):
    """A valid reply for a request: the first option shown for each item."""
    schema = schema_of(params)
    out = {}
    for index, item_id in enumerate(schema["required"]):
        answer = schema["properties"][item_id]["properties"]["answer"]
        multi = answer["type"] == "array"
        choice = gate if index == 0 else (answer["items"] if multi else answer)["enum"][0]
        out[item_id] = {"evidence": "", "answer": [choice] if multi else choice}
    return json.dumps(out)


def json_response(data, status=200):
    return FakeResponse(status, {"content-type": "application/json"},
                        body=json.dumps(data).encode("utf-8"))


class FakeAnthropic:
    """``reply(custom_id, params, n)`` gives the reply text for the n-th time
    these params are answered, or a ``result`` dict used as it is."""

    def __init__(self, reply=None, ended=True, created_at=None):
        self.reply = reply or (lambda cid, params, n: first_answers(params))
        self.ended = ended
        self.created_at = created_at or utc_now()  # jobs are made "now"
        self.batches = {}           # id -> [(custom_id, params)]
        self.creates = 0            # jobs made
        self.fail_create = None     # raise or return this on the next create
        self.lose_create = False    # make the job, then drop the answer
        self.answered = {}          # params digest -> times answered
        self.results_read = 0

    def handler(self, request, number):
        path = urlsplit(request.url).path
        if request.method == "POST" and path == "/v1/messages/batches":
            if self.fail_create is not None:
                outcome, self.fail_create = self.fail_create, None
                return outcome
            body = json.loads(request.body)
            self.creates += 1
            batch_id = f"msgbatch_{len(self.batches) + 1:04d}"
            self.batches[batch_id] = [(r["custom_id"], r["params"]) for r in body["requests"]]
            if self.lose_create:
                self.lose_create = False
                return SendError("the connection dropped (fake)")
            return json_response(self.batch(batch_id))
        if request.method == "GET" and path == "/v1/messages/batches":
            return json_response({"data": [self.batch(b) for b in reversed(self.batches)],
                                  "has_more": False, "first_id": None, "last_id": None})
        if request.method == "GET" and path.endswith("/results"):
            self.results_read += 1
            batch_id = path.split("/")[-2]
            return FakeResponse(200, {}, lines=[
                json.dumps(self.result(cid, params)) + "\n"
                for cid, params in self.batches[batch_id]])
        if request.method == "GET" and path.startswith("/v1/messages/batches/"):
            return json_response(self.batch(path.rsplit("/", 1)[1]))
        return json_response({"error": {"type": "not_found_error"}}, 404)

    def batch(self, batch_id):
        n = len(self.batches[batch_id])
        return {
            "id": batch_id, "type": "message_batch",
            "processing_status": "ended" if self.ended else "in_progress",
            "request_counts": {"processing": 0 if self.ended else n,
                               "succeeded": n if self.ended else 0, "errored": 0,
                               "canceled": 0, "expired": 0},
            "created_at": self.created_at, "ended_at": None,
            "expires_at": self.created_at, "cancel_initiated_at": None,
            "archived_at": None,
            "results_url": (f"https://api.anthropic.com/v1/messages/batches/"
                            f"{batch_id}/results") if self.ended else None}

    def result(self, custom_id, params):
        digest = json.dumps(params, sort_keys=True)
        self.answered[digest] = self.answered.get(digest, 0) + 1
        reply = self.reply(custom_id, params, self.answered[digest])
        if isinstance(reply, dict):
            return {"custom_id": custom_id, "result": reply}
        return {"custom_id": custom_id, "result": {"type": "succeeded", "message": {
            "id": "msg_1", "type": "message", "role": "assistant",
            "model": params["model"], "content": [{"type": "text", "text": reply}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 3000, "output_tokens": 400,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                      "output_tokens_details": {"thinking_tokens": 100},
                      "service_tier": "batch"}}}}


class FakeOpenAI:
    """The OpenAI Files and Batch APIs."""

    def __init__(self, reply=None, status="completed"):
        self.reply = reply or (lambda cid, params, n: first_answers(params))
        self.status = status
        self.files, self.batches, self.creates = {}, {}, 0

    def handler(self, request, number):
        path = urlsplit(request.url).path
        if request.method == "POST" and path == "/v1/files":
            marker = b'name="purpose"\r\n\r\nbatch'
            assert marker in request.body
            start = request.body.index(b"application/jsonl\r\n\r\n") + 21
            data = request.body[start:request.body.rindex(b"\r\n--")]
            file_id = f"file-{len(self.files) + 1}"
            self.files[file_id] = [json.loads(line) for line in data.splitlines()]
            return json_response({"id": file_id, "object": "file", "purpose": "batch"})
        if request.method == "POST" and path == "/v1/batches":
            body = json.loads(request.body)
            assert body["endpoint"] == "/v1/responses"
            assert body["completion_window"] == "24h"
            self.creates += 1
            batch_id = f"batch_{len(self.batches) + 1}"
            self.batches[batch_id] = dict(body, id=batch_id)
            return json_response(self.batch(batch_id))
        if request.method == "GET" and path == "/v1/batches":
            return json_response({"object": "list", "has_more": False,
                                  "data": [self.batch(b) for b in self.batches]})
        if request.method == "GET" and path.endswith("/content"):
            file_id = path.split("/")[-2]
            return FakeResponse(200, {}, lines=[json.dumps(x) + "\n"
                                                for x in self.files[file_id]])
        if request.method == "GET" and path.startswith("/v1/batches/"):
            return json_response(self.batch(path.rsplit("/", 1)[1]))
        return json_response({"error": {"code": "not_found"}}, 404)

    def batch(self, batch_id):
        body = self.batches[batch_id]
        out = {"id": batch_id, "object": "batch", "status": self.status,
               "metadata": body.get("metadata"), "created_at": 1795000000,
               "request_counts": {"total": 1, "completed": 1, "failed": 0},
               "output_file_id": None, "error_file_id": None}
        if self.status == "completed":
            output = f"out-{batch_id}"
            if output not in self.files:
                self.files[output] = [
                    {"id": "r1", "custom_id": line["custom_id"], "error": None,
                     "response": {"status_code": 200, "request_id": "req_1",
                                  "body": self.response(line)}}
                    for line in self.files[body["input_file_id"]]]
            out["output_file_id"] = output
        return out

    def response(self, line):
        text = self.reply(line["custom_id"], line["body"], 1)
        return {"id": "resp_1", "object": "response", "status": "completed",
                "model": line["body"]["model"], "error": None,
                "incomplete_details": None,
                "output": [{"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": text, "annotations": []}]}],
                "usage": {"input_tokens": 2000, "output_tokens": 300,
                          "output_tokens_details": {"reasoning_tokens": 50},
                          "total_tokens": 2300},
                "service_tier": "default"}
