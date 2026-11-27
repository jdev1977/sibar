"""How a pipeline's code reads its input files: whole, or piece by piece.

Reading a configuration file whole says nothing about how the data is read,
so it counts for neither.
"""

import re

_MAX_HANDLES = 50
_MAX_HITS = 500
_ARGS = r"(?:[^()\n]|\([^()\n]{0,100}\)){0,200}"
_OPEN = (
    # with open(...) as name
    re.compile(r"\b(?:\w{0,20}open\w{0,20}|[\w.]{0,60}\.open)\("
               rf"(?P<args>{_ARGS})\) as (?P<name>\w{{1,60}})"),
    # name = open(...)
    re.compile(r"\b(?P<name>\w{1,60}) ?= ?(?:[\w.]{0,40}\.)?open\w{0,10}\("
               rf"(?P<args>{_ARGS})\)(?![.\w])"),
)
_IMAGE_OPEN = re.compile(r"\bImage(?:File)?\.open\(")
_MODE = r"""["'][rbt+]{0,3}[wax][bt+]{0,3}["']"""
_WRITE_MODE = re.compile(rf"(?:,|mode ?=) ?{_MODE}")
# path.open("w"): the first argument of the method is the mode
_METHOD_MODE = re.compile(
    rf"(?<!gzip)(?<!bz2)(?<!lzma)(?<!io)(?<!codecs)\.open\( ?{_MODE}")
# words that name a file, or what it holds, as configuration
_CONFIGURATION = re.compile(
    r"config|setting|(?<![a-z])(?:cfg|conf)(?![a-z])|rules|schema", re.IGNORECASE)
_LITERAL = re.compile(r"""(["'])([^"'\n]{0,200})\1""")
# cfg["input"]: an entry looked up in an object
_ENTRY = re.compile(r"(?<![\w.])([A-Za-z_][\w.]{0,100})\[[^\[\]\n]{0,100}\]")
_CHAIN = re.compile(r"(?<![\w.])\.?[A-Za-z_]\w{0,60}(?:\.[A-Za-z_]\w{0,60}){0,8}")
_CONFIG_LOAD = re.compile(
    r"\b(?:tomllib\.load|tomli\.load|toml\.load|yaml\.(?:safe_load|load|full_load)|"
    r"\w{0,20}(?:config|parser)\w{0,10}\.read_file)\( ?(\w{1,60})")
_JSON_LOAD = re.compile(r"\bjson\.load\(")
_READ_TEXT = re.compile(r"\.read_(?:text|bytes)\(")
_TABLE_READ = re.compile(
    r"\b(?:pd|pandas|pl|polars)\.read_(?:csv|json|table|excel|parquet|fwf|ndjson)\(")
_WHOLE = (
    ("readlines", re.compile(r"\.readlines\(\s?\)")),
    ("read", re.compile(rf"\bopen\({_ARGS}\)\.read\(\s?\)")),
    ("list-of-rows", re.compile(r"\blist\(\s?csv\.(?:Dict)?[Rr]eader\(")),
    ("read-file", re.compile(
        r"\breadFile(?:Sync)?\(|\b(?:os|ioutil)\.ReadFile\(|\bio(?:util)?\.ReadAll\(|"
        r"\.ReadAll\(\)|\bFile\.read\(|\.read_to_string\(|\breadLines\(|"
        r"(?<![\w.])read\.csv2?\(")),
)
_STREAM = (
    ("line-loop", re.compile(r"\bfileinput\.(?:input|FileInput)\(")),
    ("line-loop", re.compile(
        r"\bfor [\w, ]{1,60} in (?:enumerate\( ?)?sys\.stdin(?:\.buffer)?(?![\w.(\[])")),
    ("readline", re.compile(r"\.readline\(|\bReadString\(|\.each_line\b|\bforeach\(")),
    ("chunked", re.compile(
        r"\bchunksize ?=|\biter\( ?lambda\b|\.read\( ?(?:\d{1,10}|\w{0,20}(?:SIZE|size|"
        r"CHUNK|chunk)\w{0,20}) ?\)|\.scan_(?:csv|ndjson|parquet)\(")),
    ("stream-api", re.compile(
        r"\bcreateReadStream\(|\breadline\.createInterface\(|\bbufio\.New(?:Scanner|"
        r"Reader)\(|\bBufReader::new\(")),
)
# for line in open(p):  for row in csv.reader(path.open()):
_OPEN_LOOP = re.compile(
    r"\bfor [\w, ]{1,60} in (?:enumerate\( ?)?(?:csv\.(?:Dict)?[Rr]eader\( ?)?"
    r"(?P<call>(?:[\w.]{0,60}(?:\([^()\n]{0,100}\))?\.)?\w{0,20}open\("
    rf"{_ARGS}\))(?![.\w])")
# loops over a name: one called after lines, or one a csv reader reads
_NAMED_LOOPS = (
    re.compile(
        r"\bfor (?:\w{1,20}, )?(?:raw_?)?line(?:_?\w{0,20})? in (?:enumerate\( ?)?"
        r"(?P<name>\w{1,60})(?![\w.(\[])"),
    re.compile(
        r"\bfor [\w, ]{1,60} in (?:enumerate\( ?)?csv\.(?:Dict)?[Rr]eader\( ?"
        r"(?P<name>\w{1,60})(?![\w.(\[])"),
)
# name = ...read() / ...splitlines(): the content, already in memory
_IN_MEMORY = re.compile(
    r"^[ \t]{0,40}(\w{1,60}) ?= ?[^\n]{0,200}?(?:\.read\(\s?\)|\.readlines\(|"
    r"\.read_(?:text|bytes)\(|\.splitlines\()", re.MULTILINE)


def _hits(pattern, code):
    return (m for m, _ in zip(pattern.finditer(code), range(_MAX_HITS)))


def _line_before(code, position):
    """The text of the line up to ``position``, at most 200 characters."""
    return code[max(position - 200, 0):position].rsplit("\n", 1)[-1]


def _names_configuration(expression):
    """Whether an expression names a configuration file: in a string
    (``'config.json'``) or a name (``CONFIG_PATH``, ``args.config``). A value
    taken from a configuration object (``config.input_path``,
    ``settings['input']``) is a path to data."""
    expression = _ENTRY.sub(
        lambda m: " " if _CONFIGURATION.search(m[1]) else m[0], expression)
    if any(_CONFIGURATION.search(m[2]) for m in _LITERAL.finditer(expression)):
        return True
    for match in _CHAIN.finditer(_LITERAL.sub(" ", expression)):
        *objects, last = match[0].split(".")
        if any(_CONFIGURATION.search(name) for name in objects if name != "self"):
            continue
        if _CONFIGURATION.search(last):
            return True
    return False


def _opened(code):
    """``(handles, configuration handles)`` of the files opened for reading."""
    handles, configs = [], {m[1] for m in _hits(_CONFIG_LOAD, code)}
    for pattern in _OPEN:
        for match in _hits(pattern, code):
            name, call = match["name"], match[0]
            if _IMAGE_OPEN.search(code[max(match.start() - 10, 0):match.end()]) \
                    or _WRITE_MODE.search(match["args"]) or _METHOD_MODE.search(call):
                continue
            if _names_configuration(match["args"]) or _CONFIGURATION.search(name):
                configs.add(name)
            elif name not in handles:
                handles.append(name)
    return handles, configs


def reading(code):
    """``(style, calls)``; the style is ``whole-file``, ``streaming``,
    ``both``, ``none``, or None where a file is opened and no read is known."""
    handles, configs = _opened(code)
    whole = {name for name, pattern in _WHOLE if pattern.search(code)}
    stream = {name for name, pattern in _STREAM if pattern.search(code)}
    for match in _hits(_JSON_LOAD, code):
        argument = code[match.end():match.end() + 150].split("\n")[0]
        # the handle itself, as in json.load(f), not an object's attribute
        handle = re.match(r" ?(\w{1,60}) ?[,)]", argument)
        first = handle[1] if handle else ""
        if (first in configs or _names_configuration(argument)
                or _names_configuration(_line_before(code, match.start()))):
            if first:
                configs.add(first)
        else:
            whole.add("json-load")
    for match in _hits(_READ_TEXT, code):
        if not _names_configuration(_line_before(code, match.start())):
            whole.add("read-text")
    for match in _hits(_TABLE_READ, code):
        arguments = code[match.end():match.end() + 300].split("\n")[0]
        if "chunksize" not in arguments:
            whole.add("table-read")
    for match in _hits(_OPEN_LOOP, code):
        call = match["call"]
        if not (_IMAGE_OPEN.search(call) or _WRITE_MODE.search(call)
                or _METHOD_MODE.search(call)):
            stream.add("line-loop")
    in_memory = {m[1] for m in _hits(_IN_MEMORY, code)}
    for pattern in _NAMED_LOOPS:
        for match in _hits(pattern, code):
            if match["name"] not in in_memory and "lines" not in match["name"]:
                stream.add("line-loop")
    handles = [name for name in handles if name not in configs][:_MAX_HANDLES]
    readers = []
    for name in handles:
        escaped = re.escape(name)
        if re.search(rf"(?<![\w.]){escaped}\.read\(\s?\)", code):
            whole.add("read")
        if re.search(rf"\b(?:for [\w, ]{{1,60}} in (?:enumerate\( ?)?|yield from )"
                     rf"{escaped}(?![\w.(\[])", code):
            stream.add("line-loop")
        readers += re.findall(
            rf"\b(\w{{1,60}}) ?= ?csv\.(?:Dict)?[Rr]eader\( ?{escaped}\b", code)[:5]
    for name in readers[:_MAX_HANDLES]:
        if re.search(rf"\bfor [\w, ]{{1,60}} in (?:enumerate\( ?)?{re.escape(name)}"
                     rf"(?![\w.(\[])", code):
            stream.add("line-loop")
    for name in handles + readers[:_MAX_HANDLES]:
        if re.search(rf"\blist\( ?{re.escape(name)} ?\)", code):
            whole.add("list-of-rows")
    if whole and stream:
        style = "both"
    elif whole:
        style = "whole-file"
    elif stream:
        style = "streaming"
    else:
        style = None if handles else "none"
    return style, sorted(whole | stream)
