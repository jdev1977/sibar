"""Records and tagger replies for the tagger tests (T2.6). No network."""

import json
import uuid

from runner.record import build_record
from tagger.prompt import item_answers
from tagger.rubric import CANNOT_TELL, NONE, load_checked

_RUBRICS = {}


def rubric(project_type="pipeline"):
    if project_type not in _RUBRICS:
        _RUBRICS[project_type] = load_checked(project_type)
    return _RUBRICS[project_type]


def record(project_type="pipeline", task="csv-to-database", level="L0",
           text="Here is the script.\n```python\nprint('hi')\n```\n",
           model_id="claude-opus-5-5", provider="anthropic", record_id=None,
           status="ok", batch_id="pilot-1", run_index=1, wording="A"):
    return build_record(
        project_type=project_type, task_id=task, prompt_text="Write it.",
        provider=provider, model_id=model_id, status=status, level=level,
        wording=wording, run_index=run_index, prompt_set_version="1",
        raw_response=text if status != "failed" else None,
        error="boom" if status == "failed" else None,
        record_id=record_id or str(uuid.uuid4()), batch_id=batch_id,
        timestamp="2026-11-20T10:00:00Z")


def answers_for(rubric_, item_ids, choose=None, gate="answers"):
    """A valid reply object: the first option of each item unless ``choose``
    (item id -> answer) says otherwise."""
    choose = dict(choose or {})
    out = {}
    for item_id in item_ids:
        item = rubric_.item(item_id)
        if item_id == rubric_.gate_item:
            answer = choose.get(item_id, gate)
        elif item_id in choose:
            answer = choose[item_id]
        else:
            answer = item.option_ids[0]
        if item.multi and isinstance(answer, str):
            answer = [answer]
        out[item_id] = {"evidence": "", "answer": answer}
    return out


def reply_text(rubric_, item_ids, **kwargs):
    return json.dumps(answers_for(rubric_, item_ids, **kwargs))


__all__ = ["rubric", "record", "answers_for", "reply_text", "item_answers",
           "CANNOT_TELL", "NONE"]
