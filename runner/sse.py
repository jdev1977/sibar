"""Server-sent events (``text/event-stream``), as the WHATWG HTML standard
defines them, read from an iterable of raw lines.

All four providers stream this way. Comments (``: keep-alive``), ``id`` and
``retry`` fields are ignored; providers' own payloads are left to the adapters.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SseEvent:
    event: str  # "message" when the stream names none
    data: str


def iter_sse(lines):
    """Yield an :class:`SseEvent` per event in ``lines`` (bytes or text, each
    one line with its line break).

    A last event not followed by a blank line is still yielded if its final
    line was complete; a line cut off mid-way (no line break) is dropped.
    """
    event, data, first, ended = "", [], True, True
    for raw in lines:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        ended = raw.endswith("\n")
        if not ended:
            break  # cut off: an interrupted stream
        line = raw.rstrip("\n").rstrip("\r")
        if first:
            line, first = line.removeprefix("﻿"), False
        if not line:
            if data:
                yield SseEvent(event or "message", "\n".join(data))
            event, data = "", []
            continue
        if line.startswith(":"):
            continue
        field, colon, value = line.partition(":")
        if colon and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)
    if data and ended:
        yield SseEvent(event or "message", "\n".join(data))
