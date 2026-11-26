"""Agreement between two taggings, and the human tag file (T2.6).

    python -m tagger agreement --type pipeline --a HUMAN.yaml --b TAGGED.jsonl
    python -m tagger agreement --type pipeline --a CLAUDE.jsonl --b OTHER.jsonl \\
        --family anthropic
    python -m tagger template --type pipeline --records FILE --sample 30 \\
        --seed 1 --out FOLDER

A tagging is either a tagged record file (``python -m tagger tag``) or a
human tag file (YAML, made by ``template``). Side A is the reference (the
Human in calibration; the Claude tagger in the cross-family check).

The measures are those of docs/rubrics.md, "Calibration (T2.5)":

- per item and output: 1 or 0 for a single-select item, the Jaccard overlap
  for a multi-select item (1 when both say ``none``); ``cannot-tell`` or
  ``not-applicable`` on one side only scores 0, on both 1; where the two
  disagree at the gate (one went on, the other stopped), every further item
  scores 0;
- item agreement A(i): the mean over the outputs for which the item was asked
  and at least one side went past the gate (the gate item: every output);
- rubric agreement A: the mean of A(i) weighted by judged outputs, with a 95%
  interval from a bootstrap over outputs (resampled whole);
- Gwet's AC1 per single-select item, K being the number of answers either
  side gave, as in the worked examples of docs/rubrics.md;
- minority agreement, over single-select items, where A's answer is not that
  item's most common A answer; the ``cannot-tell`` rate of B where A gave a
  value; the four conditions of the bar;
- with ``--family``: the agreement gap and the direction per answer between
  outputs written by that provider's models and the others.
"""

import json
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from runner.record import RecordError, read_records
from tagger.prompt import ERROR, STATUS, _item_block
from tagger.rubric import (
    CANNOT_TELL, NONE, NOT_APPLICABLE, RubricError, load_checked,
)

SCHEMA_VERSION = 1
HUMAN_KIND = "human-tags"
STOPPED = "(stopped at the gate)"
BAR = {"agreement": 0.90, "lower": 0.85, "item": 0.80, "item_min_n": 20,
       "minority": 0.80, "minority_min_n": 20, "cannot_tell": 0.10}
FLAG = 0.10


class AgreementError(ValueError):
    """A tagging file cannot be read or compared."""


@dataclass
class Tagged:
    """One output as one side tagged it."""

    task: str
    asked: tuple                         # item ids, gate first
    values: dict                         # item -> stored value (reached items only)
    level: Optional[str] = None
    provider: Optional[str] = None       # of the model that wrote the output


# --- reading ---------------------------------------------------------------------


def load_tagged_records(path, rubric):
    """``{record_id: Tagged}`` from a tagged record file; records without
    tags of ``rubric.<type>`` are left out. One tagger version per file."""
    try:
        found = read_records(path)
    except OSError as error:
        raise AgreementError(f"{path}: {error}") from None
    if found.problems:
        raise AgreementError(f"{path}: line {found.problems[0].line} is not a valid record")
    out, versions = {}, set()
    for record in found.records:
        listed = {e["extractor"]: e["extractor_version"] for e in record["extractors"]}
        if rubric.extractor not in listed:
            continue
        versions.add(listed[rubric.extractor])
        values = {f["name"]: f["value"] for f in record["features"]
                  if f["extractor"] == rubric.extractor
                  and f["name"] not in (STATUS, ERROR)}
        asked = tuple(i.id for i in rubric.items_for(record["task_id"], record["level"]))
        values.setdefault(rubric.gate_item, None)  # an error: nothing could be read
        out[record["record_id"]] = Tagged(record["task_id"], asked, values,
                                          record["level"], record["provider"])
    if len(versions) > 1:
        raise AgreementError(f"{path}: tags of several versions ({sorted(versions)}); "
                             "compare one tagger and rubric version at a time")
    for version in versions:
        if not version.startswith(rubric.version + "@"):
            raise AgreementError(f"{path}: the tags are at version {version}, not of "
                                 f"rubric {rubric.name}")
    return out


def _human_value(item, answer):
    """A human answer as a stored value; raises ValueError."""
    if isinstance(answer, list) and len(answer) == 1 and answer[0] in (
            CANNOT_TELL, NOT_APPLICABLE):
        answer = answer[0]
    if answer == CANNOT_TELL:
        return None
    if not item.multi:
        return answer
    if answer == NOT_APPLICABLE:
        return []
    if answer == NONE:
        return [NONE]
    if not isinstance(answer, list):
        raise ValueError("a multi-select answer is a list of option ids")
    if len(set(answer)) != len(answer):
        raise ValueError("an option is listed twice")
    return [NONE] if answer == [NONE] else sorted(answer)


def load_human(path, rubric):
    """``{record_id: Tagged}`` from a human tag file; refuses blanks."""
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise AgreementError(f"{path}: {error}") from None
    if not isinstance(raw, dict) or raw.get("kind") != HUMAN_KIND or \
            raw.get("schema_version") != SCHEMA_VERSION:
        raise AgreementError(f"{path}: not a schema version {SCHEMA_VERSION} human tag file")
    if raw.get("rubric") != rubric.name:
        raise AgreementError(f"{path}: tags rubric {raw.get('rubric')}, not {rubric.name}")
    out, problems = {}, []
    for entry in raw.get("outputs") or []:
        rid, task = entry.get("record_id"), entry.get("task")
        asked = tuple(entry.get("items") or ())
        given = entry.get("answers") or {}
        at = f"output {rid}"
        if not asked or asked[0] != rubric.gate_item:
            problems.append(f"{at}: items must start with {rubric.gate_item}")
            continue
        values, unknown = {}, set(given) - set(asked)
        if unknown:
            problems.append(f"{at}: answers for items not asked: {sorted(unknown)}")
        for item_id in asked:
            try:
                item = rubric.item(item_id)
            except RubricError as error:
                problems.append(f"{at}: {error}")
                break
            answer = given.get(item_id)
            if item_id != rubric.gate_item and rubric.gate_item in values and \
                    rubric.stops_at_gate(values[rubric.gate_item]):
                if answer is not None:
                    problems.append(f"{at}: {item_id} is answered, but the gate "
                                    "stops the tagging; leave it blank")
                continue
            if answer is None:
                problems.append(f"{at}: {item_id} is blank (write {CANNOT_TELL} if "
                                "you cannot tell)")
                continue
            try:
                value = _human_value(item, answer)
                rubric.check_value(item_id, value)
            except (ValueError, RubricError) as error:
                problems.append(f"{at}: {item_id}: {error}")
                continue
            values[item_id] = value
        out[rid] = Tagged(task, asked, values)
    if problems:
        shown = "; ".join(problems[:10])
        more = f" (and {len(problems) - 10} more)" if len(problems) > 10 else ""
        raise AgreementError(f"{path}: {shown}{more}")
    return out


def load_tagging(path, rubric):
    if Path(path).suffix.lower() in (".yaml", ".yml"):
        return load_human(path, rubric)
    return load_tagged_records(path, rubric)


# --- scoring ---------------------------------------------------------------------


def _reached(rubric, tagged):
    return not rubric.stops_at_gate(tagged.values.get(rubric.gate_item))


def _category(rubric, tagged, item_id, reached):
    """The answer of a single-select item as a category label."""
    if not reached and item_id != rubric.gate_item:
        return STOPPED
    value = tagged.values.get(item_id)
    return CANNOT_TELL if value is None else value


def score(rubric, item, a, b, reached_a, reached_b):
    """Agreement of one item on one output (the gate included)."""
    if item.id != rubric.gate_item and reached_a != reached_b:
        return 0.0
    va, vb = a.values.get(item.id), b.values.get(item.id)
    if va is None or vb is None:
        return 1.0 if va is None and vb is None else 0.0
    if not item.multi:
        return 1.0 if va == vb else 0.0
    if va == [] or vb == []:
        return 1.0 if va == vb else 0.0
    sa, sb = set(va), set(vb)
    return len(sa & sb) / len(sa | sb)


@dataclass
class Judgement:
    record_id: str
    item: str
    score: float
    cat_a: object
    cat_b: object
    a_has_value: bool
    b_cannot_tell: bool
    set_a: frozenset = frozenset()
    set_b: frozenset = frozenset()


def judgements(rubric, side_a, side_b):
    """Every scored (output, item) pair, and the record ids compared."""
    common = sorted(set(side_a) & set(side_b))
    out = []
    for rid in common:
        a, b = side_a[rid], side_b[rid]
        if a.task != b.task:
            raise AgreementError(f"record {rid}: task {a.task} on one side, {b.task} "
                                 "on the other")
        asked = [i for i in a.asked if i in b.asked]
        reached_a, reached_b = _reached(rubric, a), _reached(rubric, b)
        for item_id in asked:
            item = rubric.item(item_id)
            if item_id != rubric.gate_item and not (reached_a or reached_b):
                continue
            va, vb = a.values.get(item_id), b.values.get(item_id)
            ra = reached_a or item_id == rubric.gate_item
            rb = reached_b or item_id == rubric.gate_item
            out.append(Judgement(
                rid, item_id, score(rubric, item, a, b, reached_a, reached_b),
                _category(rubric, a, item_id, ra) if not item.multi else None,
                _category(rubric, b, item_id, rb) if not item.multi else None,
                ra and va is not None, rb and vb is None and ra and va is not None,
                frozenset(va or ()) if ra and isinstance(va, list) else
                frozenset([va]) if ra and isinstance(va, str) else frozenset(),
                frozenset(vb or ()) if rb and isinstance(vb, list) else
                frozenset([vb]) if rb and isinstance(vb, str) else frozenset()))
    return out, common


def pooled(items):
    items = list(items)
    return sum(j.score for j in items) / len(items) if items else None


def bootstrap(groups, statistic, reps, seed):
    """95% percentile interval of ``statistic`` over outputs resampled whole.
    ``groups`` maps record id -> its judgements."""
    keys = sorted(groups)
    if not keys:
        return None, None
    rng = random.Random(seed)
    values = []
    for _ in range(reps):
        sample = [j for _ in keys for j in groups[keys[rng.randrange(len(keys))]]]
        value = statistic(sample)
        if value is not None:
            values.append(value)
    if not values:
        return None, None
    values.sort()
    return values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]


def ac1(pairs):
    """Gwet's AC1 for (category A, category B) pairs; None if one category."""
    n = len(pairs)
    if not n:
        return None
    agreement = sum(1 for x, y in pairs if x == y) / n
    counts = Counter(x for x, _ in pairs) + Counter(y for _, y in pairs)
    k = len(counts)
    if k < 2:
        return None
    chance = sum((c / (2 * n)) * (1 - c / (2 * n)) for c in counts.values()) / (k - 1)
    return (agreement - chance) / (1 - chance)


def _by_record(items):
    groups = {}
    for j in items:
        groups.setdefault(j.record_id, []).append(j)
    return groups


def minority(rubric, items):
    """Agreement where A's answer is not the item's most common A answer."""
    chosen = []
    by_item = {}
    for j in items:
        if not rubric.item(j.item).multi:
            by_item.setdefault(j.item, []).append(j)
    for item_id, group in by_item.items():
        counts = Counter(str(j.cat_a) for j in group)
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        chosen += [j for j in group if str(j.cat_a) != top]
    return pooled(chosen), len(chosen)


def compare(rubric, side_a, side_b, *, reps=2000, seed=0):
    """Every measure of the module text, as a dict."""
    items, common = judgements(rubric, side_a, side_b)
    if not items:
        raise AgreementError("the two taggings have no output in common")
    per_item = {}
    for item in rubric.items:
        group = [j for j in items if j.item == item.id]
        if not group:
            continue
        valued = [j for j in group if j.a_has_value]
        per_item[item.id] = {
            "n": len(group), "agreement": pooled(group),
            "agree_sum": sum(j.score for j in group),
            "ac1": None if item.multi else ac1([(j.cat_a, j.cat_b) for j in group]),
            "cannot_tell_rate": (sum(j.b_cannot_tell for j in valued) / len(valued)
                                 if valued else None),
            "select": item.select}
    low, high = bootstrap(_by_record(items), pooled, reps, seed)
    small = [j for j in items if per_item[j.item]["n"] < BAR["item_min_n"]]
    minority_a, minority_n = minority(rubric, items)
    result = {
        "rubric": rubric.name, "outputs": len(common),
        "only_a": len(set(side_a) - set(side_b)), "only_b": len(set(side_b) - set(side_a)),
        "judgements": len(items), "agreement": pooled(items),
        "interval": [low, high], "items": per_item,
        "pooled_small_items": {"n": len(small), "items": sorted({j.item for j in small}),
                               "agreement": pooled(small)},
        "minority": {"agreement": minority_a, "n": minority_n},
    }
    result["bar"] = bar(result)
    return result


def bar(result):
    """The four conditions of docs/rubrics.md, "The bar"."""
    checks = []
    a, (low, _) = result["agreement"], result["interval"]
    checks.append(("1 rubric agreement >= 0.90, lower end >= 0.85",
                   a >= BAR["agreement"] and low is not None and low >= BAR["lower"]))
    big = {k: v for k, v in result["items"].items() if v["n"] >= BAR["item_min_n"]}
    failing = sorted(k for k, v in big.items() if v["agreement"] < BAR["item"])
    small = result["pooled_small_items"]
    small_ok = small["agreement"] is None or small["agreement"] >= BAR["item"]
    checks.append((f"2 every item on {BAR['item_min_n']}+ outputs >= 0.80"
                   + (f" (failing: {', '.join(failing)})" if failing else "")
                   + "; items on fewer outputs pooled >= 0.80", not failing and small_ok))
    m = result["minority"]
    checks.append(("3 minority agreement >= 0.80" + (
        "" if m["n"] >= BAR["minority_min_n"]
        else f" (only {m['n']} judgements; 20 needed: add L2 outputs)"),
        m["n"] >= BAR["minority_min_n"] and m["agreement"] is not None
        and m["agreement"] >= BAR["minority"]))
    over = sorted(k for k, v in result["items"].items()
                  if v["cannot_tell_rate"] is not None
                  and v["cannot_tell_rate"] > BAR["cannot_tell"])
    checks.append(("4 cannot-tell where A gave a value <= 10% on every item"
                   + (f" (over: {', '.join(over)})" if over else ""), not over))
    return [{"condition": text, "passed": bool(ok)} for text, ok in checks]


def family(rubric, side_a, side_b, writers, provider, *, reps=2000, seed=0):
    """The agreement gap and the direction per answer (cross-family check).

    ``writers`` maps record id -> the provider of the model that wrote it.
    Side A is the Claude tagger, side B the other one.
    """
    items, _ = judgements(rubric, side_a, side_b)
    inside = [j for j in items if writers.get(j.record_id) == provider]
    outside = [j for j in items if writers.get(j.record_id) not in (provider, None)]
    if not inside or not outside:
        raise AgreementError(f"--family {provider}: outputs written by {provider} "
                             "models and by others are both needed")

    def gap(sample):
        a = pooled(j for j in sample if writers.get(j.record_id) == provider)
        b = pooled(j for j in sample if writers.get(j.record_id) != provider)
        return None if a is None or b is None else a - b

    groups = _by_record(inside + outside)
    out = {"provider": provider, "outputs_inside": len(_by_record(inside)),
           "outputs_outside": len(_by_record(outside)),
           "gap": gap(inside + outside),
           "gap_interval": list(bootstrap(groups, gap, reps, seed)), "directions": []}
    for item in rubric.items:
        group = [j for j in inside + outside if j.item == item.id]
        if not group:
            continue
        for answer in sorted({x for j in group for x in j.set_a | j.set_b}):
            def direction(sample, answer=answer, item_id=item.id):
                def diff(part):
                    part = [j for j in part if j.item == item_id]
                    if not part:
                        return None
                    return (sum(answer in j.set_a for j in part)
                            - sum(answer in j.set_b for j in part)) / len(part)
                x = diff([j for j in sample if writers.get(j.record_id) == provider])
                y = diff([j for j in sample if writers.get(j.record_id) != provider])
                return None if x is None or y is None else x - y
            value = direction(group)
            low, high = bootstrap(_by_record(group), direction, reps, seed)
            flagged = (value is not None and abs(value) >= FLAG and low is not None
                       and (low > 0 or high < 0))
            out["directions"].append({"item": item.id, "answer": answer, "value": value,
                                      "interval": [low, high], "flagged": flagged})
    low, high = out["gap_interval"]
    out["gap_flagged"] = (out["gap"] is not None and abs(out["gap"]) >= FLAG
                          and low is not None and (low > 0 or high < 0))
    return out


# --- report ----------------------------------------------------------------------


def _f(value):
    return "-" if value is None else f"{value:.3f}"


def report(result, fam=None):
    lines = [f"Rubric {result['rubric']}: {result['outputs']} outputs in common "
             f"({result['only_a']} only in A, {result['only_b']} only in B), "
             f"{result['judgements']} judgements.",
             f"Rubric agreement A = {_f(result['agreement'])} (95% interval "
             f"{_f(result['interval'][0])} to {_f(result['interval'][1])}).", "",
             f"{'item':28} {'n':>4} {'A(i)':>6} {'AC1':>6} {'ct-rate':>7}"]
    for item_id, v in result["items"].items():
        lines.append(f"{item_id:28} {v['n']:>4} {_f(v['agreement']):>6} "
                     f"{_f(v['ac1']):>6} {_f(v['cannot_tell_rate']):>7}")
    small = result["pooled_small_items"]
    m = result["minority"]
    lines += ["", f"Items on fewer than {BAR['item_min_n']} outputs, pooled: "
              f"{_f(small['agreement'])} over {small['n']} judgements.",
              f"Minority agreement: {_f(m['agreement'])} over {m['n']} judgements.", "",
              "The bar (docs/rubrics.md; A is the Human's first pass):"]
    lines += [f"  [{'pass' if c['passed'] else 'FAIL'}] {c['condition']}"
              for c in result["bar"]]
    if fam:
        lines += ["", f"Cross-family check: outputs written by {fam['provider']} models "
                  f"({fam['outputs_inside']}) against the others ({fam['outputs_outside']}).",
                  f"Agreement gap: {_f(fam['gap'])} (interval {_f(fam['gap_interval'][0])} "
                  f"to {_f(fam['gap_interval'][1])}){'  FLAGGED' if fam['gap_flagged'] else ''}"]
        flagged = [d for d in fam["directions"] if d["flagged"]]
        lines.append(f"Directions flagged ({FLAG:.2f} or more, interval leaving out 0): "
                     f"{len(flagged)} of {len(fam['directions'])}.")
        lines += [f"  {d['item']} = {d['answer']}: {_f(d['value'])} "
                  f"({_f(d['interval'][0])} to {_f(d['interval'][1])})" for d in flagged]
    return "\n".join(lines)


# --- the human tag file template --------------------------------------------------------


def _fence(text):
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(4, longest + 1)


def sheet(rubric, record, items):
    """A reading sheet: the instructions, the items (options in the order the
    tagger sees for this output) and the response. Blind: no model, prompt or
    level."""
    fence = _fence(record["raw_response"])
    parts = [f"# Output {record['record_id']}", "",
             "Answer in tags.yaml under this record id. Write an answer id exactly "
             f"as shown; a multi-select item takes a list, or {NONE}, {CANNOT_TELL} or "
             f"{NOT_APPLICABLE} alone. If {rubric.gate_item} is "
             f"{' or '.join(rubric.gate_no_solution)} or {CANNOT_TELL}, leave the "
             "other items blank. Never leave an item blank otherwise: write "
             f"{CANNOT_TELL}.", "", "## Rubric instructions", ""]
    parts += [f"- {line}" for line in rubric.instructions]
    parts += ["", "## Items", ""]
    for number, item in enumerate(items, start=1):
        parts += [_item_block(rubric, item, number, record["task_id"],
                              record["record_id"]), ""]
    parts += ["## The response", "", fence + "text", record["raw_response"], fence, ""]
    return "\n".join(parts)


def make_template(rubric, records, folder, *, record_ids=(), sample=None, seed=0,
                  label="human", pass_number=1):
    """Write ``folder/tags.yaml`` (blank answers) and ``folder/sheets/``."""
    pool = [r for r in records if r["project_type"] == rubric.project_type
            and r["status"] == "ok" and r["task_id"] in rubric.tasks
            and r["level"] is not None]
    if record_ids:
        wanted = set(record_ids)
        chosen = [r for r in pool if r["record_id"] in wanted]
        missing = wanted - {r["record_id"] for r in chosen}
        if missing:
            raise AgreementError(f"records not found (or not tagged by this rubric): "
                                 f"{sorted(missing)}")
    else:
        chosen = list(pool)
    rng = random.Random(seed)
    if sample is not None:
        if sample > len(chosen):
            raise AgreementError(f"--sample {sample}: only {len(chosen)} records")
        chosen = rng.sample(chosen, sample)
    rng.shuffle(chosen)  # no grouping by model, task or level in the file
    folder = Path(folder)
    (folder / "sheets").mkdir(parents=True, exist_ok=True)
    if (folder / "tags.yaml").exists():
        raise AgreementError(f"{folder / 'tags.yaml'} exists; it is never overwritten")
    outputs = []
    for record in chosen:
        items = rubric.items_for(record["task_id"], record["level"])
        name = f"sheets/{record['record_id']}.md"
        (folder / name).write_text(sheet(rubric, record, items), encoding="utf-8")
        outputs.append({"record_id": record["record_id"], "task": record["task_id"],
                        "sheet": name, "items": [i.id for i in items],
                        "answers": {i.id: None for i in items}})
    document = {"schema_version": SCHEMA_VERSION, "kind": HUMAN_KIND,
                "rubric": rubric.name, "tagger": label, "pass": pass_number,
                "outputs": outputs}
    header = ("# Human tags (T2.5). Fill every answer from the sheet named; see "
              "tagger/README.md.\n# Leave the items after the gate blank (~) only "
              "when the gate stops the tagging.\n")
    (folder / "tags.yaml").write_text(
        header + yaml.safe_dump(document, sort_keys=False, allow_unicode=False),
        encoding="utf-8")
    return len(outputs)


# --- command line ------------------------------------------------------------------------


def add_agreement_arguments(parser):
    parser.add_argument("--type", required=True, dest="project_type")
    parser.add_argument("--rubric-version", default="1")
    parser.add_argument("--a", required=True, help="reference tagging (.yaml human "
                        "file, or a tagged record file)")
    parser.add_argument("--b", required=True, help="tagging compared with it")
    parser.add_argument("--records", nargs="*", default=[], metavar="FILE",
                        help="record files giving the writing model of each output "
                             "(needed for --family when neither side is a record file)")
    parser.add_argument("--family", metavar="PROVIDER",
                        help="cross-family check: outputs written by this provider's "
                             "models against the others")
    parser.add_argument("--reps", type=int, default=2000, help="bootstrap resamples")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", metavar="PATH", help="also write every figure as JSON")


def add_template_arguments(parser):
    parser.add_argument("--type", required=True, dest="project_type")
    parser.add_argument("--rubric-version", default="1")
    parser.add_argument("--records", nargs="+", required=True, metavar="FILE")
    parser.add_argument("--record-id", action="append", default=[], metavar="ID")
    parser.add_argument("--sample", type=int)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--label", default="human",
                        help="the tagger name in the file (a role, not a person's name)")
    parser.add_argument("--pass", dest="pass_number", type=int, default=1, choices=(1, 2))
    parser.add_argument("--out", required=True, metavar="FOLDER")


def _records(paths):
    records = []
    for path in paths:
        found = read_records(path)
        if found.problems:
            raise AgreementError(f"{path}: line {found.problems[0].line} is not a valid record")
        records.extend(found.records)
    return records


def run_agreement(args, out=print):
    try:
        rubric = load_checked(args.project_type, args.rubric_version)
        side_a, side_b = load_tagging(args.a, rubric), load_tagging(args.b, rubric)
        result = compare(rubric, side_a, side_b, reps=args.reps, seed=args.seed)
        fam = None
        if args.family:
            writers = {rid: t.provider for side in (side_a, side_b)
                       for rid, t in side.items() if t.provider}
            writers.update({r["record_id"]: r["provider"] for r in _records(args.records)})
            fam = family(rubric, side_a, side_b, writers, args.family,
                         reps=args.reps, seed=args.seed)
        out(report(result, fam))
        if args.json:
            Path(args.json).write_text(json.dumps({"agreement": result, "family": fam},
                                                  indent=1), encoding="utf-8")
        return 0
    except (AgreementError, RubricError, RecordError, OSError) as error:
        out(f"refused: {error}")
        return 2


def run_template(args, out=print):
    try:
        rubric = load_checked(args.project_type, args.rubric_version)
        count = make_template(rubric, _records(args.records), args.out,
                              record_ids=args.record_id, sample=args.sample,
                              seed=args.seed, label=args.label,
                              pass_number=args.pass_number)
        out(f"{count} outputs: {Path(args.out) / 'tags.yaml'} and its sheets.")
        return 0
    except (AgreementError, RubricError, RecordError, OSError) as error:
        out(f"refused: {error}")
        return 2

