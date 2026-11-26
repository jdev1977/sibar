"""The shape of a reply: headings, lists, tables, code blocks and length.
The same features for pipeline, math and engineering."""

import re

from extractors.base import Extractor
from extractors.common.response import NO_INPUT, get_doc, result

VERSION = "1"
MAX_COUNT = 100_000
_HEADING = re.compile(r" {0,3}#{1,6}[ \t]")
_LIST = re.compile(r"[ \t]{0,12}(?:[-*+]|\d{1,3}[.)])[ \t]{1,4}\S")
_WORD = re.compile(r"[^\W\d_]{1,60}")


def _separator(line):
    line = line.strip()
    return "|" in line and "-" in line and not line.strip("|-: \t")


def tables(text):
    """Data rows of each Markdown table in ``text``."""
    lines = text.split("\n")
    found, index = [], 1
    while index < len(lines):
        if _separator(lines[index]) and "|" in lines[index - 1]:
            end = index + 1
            while end < len(lines) and "|" in lines[end]:
                end += 1
            found.append(end - index - 1)
            index = end + 1
        else:
            index += 1
    return found


def reply_values(inputs):
    doc = get_doc(inputs)
    if not doc.has_text:
        return dict(NO_INPUT)
    lines = doc.prose.split("\n")
    rows = tables(doc.prose)
    return result(doc, {
        "words": min(sum(1 for _ in _WORD.finditer(doc.prose)), MAX_COUNT),
        "headings": sum(1 for line in lines if _HEADING.match(line)),
        "list_items": sum(1 for line in lines if _LIST.match(line)),
        "code_blocks": len(doc.blocks),
        "tables": len(rows),
        "largest_table_rows": max(rows, default=0),
    })


def reply_extractor(project_type):
    return Extractor(
        name=f"{project_type}.reply", version=VERSION, project_type=project_type,
        extract=reply_values,
        summary="headings, lists, tables, code blocks and length of the reply")
