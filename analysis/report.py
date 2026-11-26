"""Writing results: JSON (exact fractions kept as text beside a decimal) and
a readable Markdown summary. Same input, byte-identical files."""

import json
import math
import re
from fractions import Fraction
from pathlib import Path

DECIMALS_JSON = 6


def plain(obj):
    """Results as JSON-ready values: a Fraction becomes
    ``{"fraction": "59/80", "decimal": 0.7375}``, a set a sorted list."""
    if isinstance(obj, Fraction):
        return {"fraction": str(obj), "decimal": round(float(obj), DECIMALS_JSON)}
    if isinstance(obj, bool) or obj is None or isinstance(obj, (str, int)):
        return obj
    if isinstance(obj, float):
        if math.isinf(obj):
            return "inf" if obj > 0 else "-inf"
        return round(obj, DECIMALS_JSON)
    if isinstance(obj, frozenset) or isinstance(obj, set):
        return sorted(plain(x) for x in obj)
    if isinstance(obj, dict):
        return {str(k): plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [plain(x) for x in obj]
    raise TypeError(f"cannot write {type(obj).__name__}")


def dumps(result):
    return json.dumps(plain(result), indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def safe_name(text):
    """A model id or batch id as a file-name part."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._") or "x"


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


# --- formatting -------------------------------------------------------------------


def num(x, places=4):
    if x is None:
        return "-"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{float(x):.{places}f}"


def frac(x):
    if x is None:
        return "-"
    return f"{x} ({num(x)})" if isinstance(x, Fraction) and x.denominator != 1 else num(x)


def interval(iv):
    return "-" if not iv else f"{num(iv[0])} to {num(iv[1])}"


def value_text(value):
    if isinstance(value, (frozenset, set, list, tuple)):
        return "{" + ", ".join(sorted(str(v) for v in value)) + "}"
    return str(value)


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return lines


def _summary_rows(summary, flag_name=None):
    rows = []
    for dim, block in summary["dimensions"].items():
        row = [dim, num(block["mean"]), interval(block["interval"]), block["T"]]
        if flag_name:
            row.append(block.get("flag") or "")
        rows.append(row)
    if summary["overall"]:
        block = summary["overall"]
        row = ["**overall**", num(block["mean"]), interval(block["interval"]), block["T"]]
        if flag_name:
            row.append("")
        rows.append(row)
    return rows


def _variable_rows(rows):
    out = []
    for row in rows:
        if row["role"] not in ("primary", "provisional"):
            continue
        name = row["variable"].split(".", 1)[1]
        if row["role"] == "provisional":
            name += " (provisional)"
        if not row.get("items"):
            undetermined = row.get("undetermined")
            out.append([name, row["label"], "-", "-", "-", "-", row["N"], row["T"], "-",
                        f"{undetermined['count']} ({num(undetermined['share'], 2)})"
                        if undetermined else "-",
                        row["not_applicable"]["count"] if undetermined else "-",
                        "-", ", ".join(row["flags"])])
            continue
        top = row["items"][0]
        if "default_set" in row:
            shown = value_text(row["default_set"]) if row["default_set"] else "{}"
        else:
            shown = row["reported"] or ("(" + ", ".join(row["nominal_top"]) + ")")
        flags = list(row["flags"])
        if row.get("holds_across_tasks"):
            flags.append("holds across tasks")
        support = row.get("task_support")
        out.append([name, row["label"], shown, f"{top['choice']} {num(top['share'])}",
                    interval(top["run_interval"]), interval(top["task_interval"]),
                    row["N"], row["T"], num(row["n_eff"], 1),
                    f"{row['undetermined']['count']} ({num(row['undetermined']['share'], 2)})",
                    row["not_applicable"]["count"],
                    f"{support[0]}/{support[1]}" if support else "-",
                    ", ".join(flags)])
    return out


def tables_markdown(result):
    lines = [f"# Fingerprints: {result['project_type']}, batch group "
             f"{', '.join(result['batch_group'])}", "",
             f"Metrics version {result['metrics_version']}. Extractor versions: "
             + ", ".join(f"{k} {v}" for k, v in result["extractor_versions"].items()) + ".",
             "", "Record files: " + ", ".join(result["record_files"]) + ".", ""]
    for note in result["notes"]:
        lines += [f"- Note: {note}"]
    lines += ["", "Every figure, with exact fractions and every choice of every variable "
              "(secondary variables and per-task tables included), is in the JSON file "
              "beside this one. Top choice: the reported top choice; a choice in "
              "brackets is the nominal top of a row without a clear lead.", ""]
    for model, body in result["models"].items():
        lines += [f"## {model}", ""]
        for level, data in body["levels"].items():
            fp = data["fingerprint"]
            lines += [f"### {model} at {level}", "",
                      f"Dates {' to '.join(fp['dates'] or ['-'])}; model_id_returned "
                      f"{', '.join(fp['model_id_returned']) or 'not reported'}; flags: "
                      f"{', '.join(fp['flags']) or 'none'}.", ""]
            out = fp["outcomes"]
            lines += ["Outcomes (all selected records, pooled):", ""]
            lines += table(["Outcome", "Share", "Count"],
                           [[o, num(out["shares"][o]), out["counts"][o]] for o in out["shares"]])
            lines += ["", f"N {out['N']}, T {out['T']}, n_eff {num(out['n_eff'], 2)}.", ""]
            health = [[name, num(rate["share"]), rate["N"]] for name, rate in fp["health"].items()
                      if rate["share"]]
            if health:
                lines += ["Health rates above 0 (usable runs):", ""]
                lines += table(["Rate", "Share", "N"], health) + [""]
            if fp["partly_read_dimensions"]:
                lines += ["Dimensions flagged `partly read`: " + ", ".join(
                    f"{d} ({', '.join(v)})" for d, v in fp["partly_read_dimensions"].items())
                    + ".", ""]
            lines += ["Fingerprint (primary and provisional variables):", ""]
            lines += table(["Variable", "Label", "Top choice", "Largest share", "Run interval",
                            "Task interval", "N", "T", "n_eff", "Undetermined",
                            "Not applicable", "Task support", "Flags"],
                           _variable_rows(fp["variables"]))
            lines += ["", "Convergence by dimension (task interval):", ""]
            lines += table(["Dimension", "C", "Task interval", "T"],
                           _summary_rows(data["convergence"]))
            lines += ["", "Wording sensitivity by dimension:", ""]
            lines += table(["Dimension", "S_w", "Task interval", "T", "Flag"],
                           _summary_rows(data["wording_sensitivity"], "flag"))
            pooled = data["directed"]["pooled"]
            if pooled:
                lines += ["", "Directed table, pooled over tasks (closed variables with an "
                          "expected value):", ""]
                rows = []
                for var, entry in pooled.items():
                    comp, pers = entry["compliance"], entry["persistence"]
                    rows.append([var.split(".", 1)[1],
                                 len(comp["tasks"]) if comp else 0,
                                 num(comp["share"]) if comp else "-",
                                 interval(comp["run_interval"]) if comp else "-",
                                 comp["no_verdict"] if comp else "-",
                                 num(pers["share"]) if pers else "-",
                                 interval(pers["run_interval"]) if pers else "-",
                                 pers["reading"] if pers else "not read"])
                lines += table(["Variable", "Tasks", "Compliance", "Run interval",
                                "No verdict", "Persistence", "Run interval", "Reading"], rows)
            reps = fp["representative_outputs"]
            lines += ["", "Representative outputs:", ""]
            rows = []
            for task, rep in reps.items():
                if rep is None:
                    rows.append([task, "none (fewer than 3 usable runs)", "-", "-", "-"])
                    continue
                best = rep["most_typical"][0]
                rows.append([task, best["record_id"], num(best["typicality"]),
                             ", ".join(f"{e['wording']}{e['run_index']}"
                                       for e in rep["most_typical"]),
                             f"{rep['least_typical']['wording']}"
                             f"{rep['least_typical']['run_index']}"])
            lines += table(["Task", "Representative", "Typicality", "Three most typical",
                            "Least typical"], rows) + [""]
        for sens in body["sensitivity"]:
            lines += [f"### {model}: prompt sensitivity {sens['from']} to {sens['to']}", "",
                      "Variables open at both levels (spill-over). S: level shift; "
                      "yardstick: mean wording shift; E: excess.", ""]
            rows = []
            dims = list(sens["shift"]["dimensions"])
            for dim in dims:
                s = sens["shift"]["dimensions"][dim]
                y = sens["yardstick"]["dimensions"].get(dim)
                e = sens["excess"]["dimensions"].get(dim)
                rows.append([dim, num(s["mean"]), interval(s["interval"]),
                             num(y["mean"]) if y else "-",
                             num(e["mean"]) if e else "-",
                             interval(e["interval"]) if e else "-",
                             (e or {}).get("flag") or ""])
            lines += table(["Dimension", "S", "Task interval", "Yardstick", "E",
                            "Task interval", "Flag"], rows)
            for task, notes in sens["associations"].items():
                for note in notes:
                    lines += ["", f"- Association ({task}, into {sens['to']}): "
                              f"\"{note['quote'] if isinstance(note['quote'], str) else '; '.join(note['quote'])}\""
                              f" may pull {', '.join(note['variables'][:6])}"
                              f"{' ...' if len(note['variables']) > 6 else ''}. {note['note'] or ''}"]
            lines += [""]
    for comp in result["model_comparisons"]:
        lines += [f"## Across models at {comp['level']}", "",
                  "All models (mean over pairs): agreement X and model shift D.", ""]
        rows = []
        x_dims = comp["all_models"]["agreement"]["dimensions"]
        for dim, d in comp["all_models"]["model_shift"]["dimensions"].items():
            x = x_dims.get(dim)
            rows.append([dim, num(x["mean"]) if x else "-", num(d["mean"]),
                         interval(d["interval"]), d.get("flag") or ""])
        lines += table(["Dimension", "X", "D", "Task interval of D", "Flag"], rows)
        shared = comp["shared_defaults"]
        lines += ["", "Shared defaults: " + ("; ".join(
            f"{v.split('.', 1)[1]} {value_text(c)}" for v, c in shared.items()) or "none") + ".",
            ""]
    return "\n".join(lines).rstrip() + "\n"


def stability_markdown(result):
    lines = [f"# Stability check: {result['model']}, batch {result['batch']}", "",
             f"Check: {result['check']}. Metrics version {result['metrics_version']}.", "",
             f"**Verdict: `{result['verdict']}`.** {result['consequence']}", ""]
    if result["verdict"] == "not run":
        if result["selection"]["cells"]:
            lines += ["Cells to run (run indexes still missing):", ""]
            lines += table(["Task", "Level", "Wording", "Run indexes"],
                           [[c["task"], c["level"], c["wording"],
                             ", ".join(map(str, c["run_indexes"]))]
                            for c in result["selection"]["cells"]])
            lines += ["", "Runner command (check the plan with --dry-run, then run with "
                      "--paid and both caps):", "", "    " + result["selection"]["runner_command"],
                      ""]
        if result["cells_short"]:
            lines += ["Cells short of usable runs: " + ", ".join(result["cells_short"]) + ".", ""]
    else:
        lines += table(["Score", "Counted", "Kept", "New", "Lost", "Reversed (variables)",
                        "Changed (sets)", "Reversals", "E small", "E big", "Growth"],
                       [[frac(result["score"]), len(result["counted"]),
                         result["kinds"]["kept"], result["kinds"]["new"],
                         result["kinds"]["lost"], result["kinds"]["reversed"],
                         result["kinds"]["changed"], result["reversals"],
                         result["established_defaults"][0], result["established_defaults"][1],
                         frac(result["growth"])]])
        if result["changes"]:
            lines += ["", "Variables that changed:", ""]
            rows = []
            for c in result["changes"]:
                if "default_set" in c["small"]:
                    detail = (f"{value_text(c['small']['default_set'])} -> "
                              f"{value_text(c['big']['default_set'])}; gained "
                              f"{value_text(c['gained'])}, dropped {value_text(c['dropped'])}")
                    majority = "default items"
                else:
                    detail = f"{c['small']['reported'] or '-'} -> {c['big']['reported'] or '-'}"
                    majority = (f"{'yes' if c['small']['established_majority'] else 'no'} / "
                                f"{'yes' if c['big']['established_majority'] else 'no'}")
                rows.append([c["variable"].split(".", 1)[1], c["kind"], detail, majority])
            lines += table(["Variable", "Change", "Reported", "Established majority (small / big)"],
                           rows)
        if result["open_at_10_runs"]:
            lines += ["", "Open at 10 runs (gained an established default between 10 and 20): "
                      + ", ".join(g["variable"].split(".", 1)[1] for g in result["open_at_10_runs"])
                      + f"; growth {frac(result['growth'])}."]
        halves = result["halves"]

        def group(g):
            dates = " to ".join(g["dates"]) if g["dates"] else "-"
            return f"dates {dates}, model_id_returned " + (
                ", ".join(g["model_id_returned"]) or "not reported")
        lines += ["", f"Run indexes {halves['groups'][0]} against {halves['groups'][1]} "
                  "(read for drift): overall shift "
                  f"{num((halves['shift_overall'] or {}).get('mean'))}; first group "
                  f"{group(halves['first'])}; second group {group(halves['second'])}.", ""]
        if halves["shift_by_dimension"]:
            lines += table(["Dimension", "Shift", "Task interval", "T"],
                           [[d, num(b["mean"]), interval(b["interval"]), b["T"]]
                            for d, b in halves["shift_by_dimension"].items()]) + [""]
    lines += ["Cells:", ""]
    lines += table(["Task", "Wording", "Usable in first", "Usable in all", "Missing"],
                   [[c["task"], c["wording"], c["usable_first"], c["usable_all"],
                     ", ".join(map(str, c["missing_run_indexes"])) or "-"]
                    for c in result["cells"]])
    return "\n".join(lines).rstrip() + "\n"
