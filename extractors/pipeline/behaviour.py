"""How a pipeline logs, is configured, retries, reads files, writes its
results and works in parallel. Keywords and calls in code with the comments
removed; test files are left out."""

import re

from extractors.base import Extractor
from extractors.common.response import NO_INPUT, get_doc, result
from extractors.pipeline.images import saves_an_image
from extractors.pipeline.libraries import read_imports
from extractors.pipeline.reading import reading
from extractors.pipeline.source import get_output

# --- logging ----------------------------------------------------------------

_LOGGING = {
    "logging": "logging", "loguru": "loguru", "structlog": "structlog",
    "winston": "winston", "pino": "pino", "bunyan": "bunyan", "log4js": "log4js",
    "log": "go-log", "log/slog": "slog",
    "github.com/sirupsen/logrus": "logrus", "go.uber.org/zap": "zap",
    "github.com/rs/zerolog": "zerolog", "tracing": "tracing",
    "env_logger": "env-logger", "logger": "logger", "futile.logger": "futile-logger",
}
_PRINT = {
    "python": re.compile(r"(?<![\w.])print\(|\bsys\.std(?:out|err)\.write\("),
    "javascript": re.compile(r"\bconsole\.(?:log|error|warn|info)\("),
    "typescript": re.compile(r"\bconsole\.(?:log|error|warn|info)\("),
    "go": re.compile(r"\bfmt\.(?:Print|Println|Printf|Fprintln|Fprintf)\("),
    "rust": re.compile(r"\be?println!"),
    "ruby": re.compile(r"(?<![\w.])(?:puts|print|warn)\b[ (]"),
    "r": re.compile(r"(?<![\w.])(?:print|cat|message)\("),
    "shell": re.compile(r"(?:^|;)[ \t]{0,40}(?:echo|printf)\b", re.M),
}


def _libraries_used(inputs):
    read = read_imports(inputs)
    return set() if read is None else read[0] | read[1]


def logging_features(inputs):
    output = get_output(inputs)
    if not output.main:
        return dict(NO_INPUT)
    doc = get_doc(inputs)
    known = [c for c in output.main if c.language in _PRINT]
    if not known and output.main:
        return result(doc, {"logging_style": None, "logging_libraries": None,
                            "uses_print": None})
    used = _libraries_used(inputs)
    libraries = {name for key, name in _LOGGING.items()
                 if key in used and (key != "log" or any(
                     c.language == "go" for c in output.main))}
    printed = any(_PRINT[c.language].search(c.parts.bare) for c in known)
    style = ("both" if libraries and printed else "logging-library" if libraries
             else "print" if printed else "neither")
    return result(doc, {"logging_style": style,
                        "logging_libraries": sorted(libraries),
                        "uses_print": printed})


# --- configuration and keys ---------------------------------------------------

_ARGUMENTS = re.compile(
    r"\bargparse\.|\bArgumentParser\(|\bsys\.argv\b|^[ \t]{0,40}(?:import|from) "
    r"(?:click|typer|docopt|getopt)\b|\bprocess\.argv\b|\bparseArgs\(|"
    r"\brequire\(\"\"\)\.program\b|\bflag\.(?:String|Int|Bool|Duration|Parse|"
    r"StringVar)\w{0,10}\(|\bcobra\.Command\b|\bos\.Args\b|\bARGV\b|\bOptionParser\b|"
    r"\bcommandArgs\(|\bgetopts\b|\$\{?[1-9]\b", re.M)
_ARGUMENT_LIBRARIES = {"click", "typer", "docopt", "yargs", "commander", "minimist",
                       "clap", "thor"}
_ENVIRONMENT = re.compile(
    r"\bos\.environ\b|\bos\.getenv\(|(?<![\w.])getenv\(|\bload_dotenv\(|"
    r"\bprocess\.env\b|\bos\.(?:Getenv|LookupEnv)\(|\bENV(?:\[|\.fetch\b)|"
    r"\bSys\.getenv\(|\benv::var\(")
_CONFIG_CALLS = re.compile(
    r"\bconfigparser\.|\bConfigParser\(|\btomllib\.loads?\(|\btoml\.load\(|"
    r"\btomli\.loads?\(|\byaml\.(?:safe_load|load|full_load)\(|\bviper\.")
_CONFIG_NAME = re.compile(
    r"""["'`/](?:[\w-]{0,40}[_-])?(?:config|settings|rules|schema)[\w-]{0,40}"""
    r"""\.(?:json|ya?ml|toml|ini|cfg)\b""", re.IGNORECASE)

_KEY = re.compile(r"api[_-]?key|api[_-]?token|access[_-]?token|auth[_-]?token|"
                  r"client[_-]?secret|secret[_-]?key|password|passwd|db[_-]?pass",
                  re.IGNORECASE)
_KEY_ENV = re.compile(r"getenv\(|environ\b|process\.env\b|Getenv\(|LookupEnv\(|"
                      r"\bENV(?:\[|\.fetch)|env::var\(")
_KEY_ARGUMENT = re.compile(
    r"\bargs\.\w{0,40}(?:key|token|secret|password)|[\"']--[\w-]{0,30}"
    r"(?:key|token|secret|password)|flag\.String\w{0,5}\(\s?\"[\w-]{0,30}"
    r"(?:key|token|secret|password)", re.IGNORECASE)
_KEY_FILE = re.compile(
    r"\b(?:config|cfg|conf|settings|secrets)\w{0,20}(?:\[|\.get\()[^\n]{0,60}"
    r"(?:key|token|secret|password)|(?:key|token|secret)\w{0,20}[^\n]{0,60}"
    r"(?:\.read_text\(|\bopen\()", re.IGNORECASE)
_ASSIGNED = re.compile(
    r"""(?P<name>[\w-]{0,60})["']?\]?[ \t]{0,3}(?::[ \t]?[\w\[\]]{1,30}[ \t]?)?"""
    r"""(?::=|=(?!=)|:)[ \t]{0,3}(?P<q>["'])(?P<value>[^"'\n]{3,200})(?P=q)""")
_NOT_A_KEY = re.compile(r"header|env|name|var|file|path|field|column|url|param|label",
                        re.IGNORECASE)


def _written_in(line):
    for match in _ASSIGNED.finditer(line):
        name, value = match["name"], match["value"]
        if (_KEY.search(name) and not _NOT_A_KEY.search(name)
                and not value.lower().startswith("x-")
                and not re.fullmatch(r"[A-Za-z]{0,30}_?(?:api_)?(?:key|token)_?env", value,
                                     re.IGNORECASE)):
            return True
    return False


def _key_source(code):
    mentioned, sources = False, set()
    for line in code.split("\n"):
        if not _KEY.search(line):
            continue
        mentioned = True
        line = line[:2000]
        if _KEY_ENV.search(line):
            sources.add("environment")
        if _KEY_ARGUMENT.search(line):
            sources.add("argument")
        if _KEY_FILE.search(line):
            sources.add("file")
        if _written_in(line):
            sources.add("written-in")
    if not mentioned:
        return "none"
    if not sources:
        return None
    return sources.pop() if len(sources) == 1 else "several"


def config(inputs):
    output = get_output(inputs)
    if not output.main:
        return dict(NO_INPUT)
    code = output.text("code")
    sources = set()
    if (_ARGUMENTS.search(output.text("bare"))
            or _libraries_used(inputs) & _ARGUMENT_LIBRARIES):
        sources.add("arguments")
    if _ENVIRONMENT.search(output.text("bare")):
        sources.add("environment")
    if _CONFIG_CALLS.search(output.text("bare")) or _CONFIG_NAME.search(code):
        sources.add("config-file")
    return result(get_doc(inputs), {"config_sources": sorted(sources),
                                    "key_source": _key_source(code)})


# --- retries, reading, writing, parallel work ----------------------------------

_RETRY = re.compile(
    r"retr(?:y|ies|ied|ying)|backoff|max_?attempts?|"
    r"\b(?:for|while)\b[^\n]{0,80}attempt", re.IGNORECASE)
_RETRY_LIBRARIES = {
    "tenacity": "tenacity", "backoff": "backoff", "retrying": "retrying",
    "retry": "retry", "p-retry": "p-retry",
    "axios-retry": "axios-retry", "async-retry": "async-retry",
    "github.com/cenkalti/backoff": "cenkalti-backoff",
    "github.com/avast/retry-go": "retry-go",
    "github.com/hashicorp/go-retryablehttp": "go-retryablehttp",
}
# urllib3 retries only where its Retry object is made; importing it is not enough
_URLLIB3_RETRY = re.compile(r"(?<![\w])Retry\(")

# (format, searched in code with strings?, pattern)
_OUTPUTS = (
    ("csv", False, r"\.to_csv\(|\bcsv\.(?:writer|DictWriter|NewWriter)\(|\bwrite_csv\(|"
                   r"\bcreateObjectCsvWriter\(|\bwrite\.csv2?\("),
    ("json", False, r"\bjson\.dumps?\(|\.to_json\(|\bJSON\.stringify\(|"
                    r"\bjson\.(?:NewEncoder|Marshal\w{0,10})\(|\bwrite_json\("),
    # a .jsonl name alone may be the input, so only a writing call counts
    ("jsonl", True, r"\.to_json\([^\n]{0,120}\blines ?= ?True\b|"
                    r"\.(?:jsonl|ndjson)[\"'][^\n]{0,20}[\"'][wa]t?[\"']|"
                    r"\bjson\.dumps\([^\n]{0,100}\) ?\+ ?[\"']\\n[\"']|"
                    r"\{json\.dumps\([^\n]{0,100}\)\}\\n|\.sink_ndjson\(|\.write_ndjson\("),
    ("parquet", False, r"\.(?:to|write|sink)_parquet\(|\bpq\.write_table\("),
    ("database", True, r"\bINSERT(?: OR \w{1,10})? INTO\b|\.to_sql\(|\binsert_(?:one|many)\(|"
                       r"\bbulk_insert\w{0,20}\(|\bCOPY \w{1,60} FROM STDIN"),
    ("excel", False, r"\.to_excel\(|\bExcelWriter\(|\bWorkbook\("),
    ("html", False, r"\.to_html\("),
    ("plot", False, r"\bsavefig\(|\.write_image\(|\bggsave\("),
    ("image", False, r"\.toFile\(|\bcv2\.imwrite\(|\bimaging\.Save\(|"
                     r"\b(?:jpeg|png)\.Encode\("),
)
_OUTPUTS = tuple((name, strings, re.compile(pattern))
                 for name, strings, pattern in _OUTPUTS)
_PYTHON_IMAGES = {"pillow", "opencv-python", "wand", "pyvips", "scikit-image"}
_PARALLEL = tuple((name, re.compile(pattern)) for name, pattern in (
    ("process-pool", r"\bProcessPoolExecutor\b|\bmultiprocessing\b|(?<![\w.])Pool\(|"
                     r"\bParallel\(n_jobs|\bmclapply\(|\bchild_process\.fork\(|\bcluster\.fork\("),
    ("thread-pool", r"\bThreadPoolExecutor\b|\bThreadPool\(|\bthreading\.Thread\(|"
                    r"\bThread\.new\b"),
    ("asyncio", r"\basyncio\.(?:gather|TaskGroup|create_task|as_completed|wait)\b"),
    ("promise-all", r"\bPromise\.(?:all|allSettled)\("),
    ("worker-threads", r"\bnew Worker\(|\bPiscina\b"),
    ("goroutines", r"\bgo func\b|\bsync\.WaitGroup\b|\berrgroup\."),
    ("rayon", r"\.par_(?:iter|bridge)\("),
    ("shell-parallel", r"\bxargs\b[^\n]{0,80}-P ?\d|(?:^|\|)[ \t]{0,20}parallel "),
))


def operations(inputs):
    output = get_output(inputs)
    if not output.main:
        return dict(NO_INPUT)
    code, bare = output.text("code"), output.text("bare")
    retry_libraries = {name for key, name in _RETRY_LIBRARIES.items()
                       if key in _libraries_used(inputs)}
    if (_URLLIB3_RETRY.search(bare)
            and _libraries_used(inputs) & {"urllib3", "requests"}):
        retry_libraries.add("urllib3")
    style, calls = reading(code)
    formats = {name for name, strings, pattern in _OUTPUTS
               if pattern.search(code if strings else bare)}
    if _libraries_used(inputs) & _PYTHON_IMAGES and saves_an_image(bare):
        formats.add("image")
    if any(c.language in _PRINT and c.language != "shell"
           and _PRINT[c.language].search(c.parts.bare) for c in output.main):
        formats.add("printed")
    return result(get_doc(inputs), {
        "retry_present": bool(retry_libraries) or bool(_RETRY.search(bare)),
        "retry_libraries": sorted(retry_libraries),
        "file_reading": style,
        "read_calls": calls,
        "output_formats": sorted(formats),
        "parallel_work": sorted(name for name, pattern in _PARALLEL
                                if pattern.search(bare)),
    })


EXTRACTORS = (
    Extractor("pipeline.logging", "1", "pipeline", logging_features,
              "logging library or print"),
    Extractor("pipeline.config", "1", "pipeline", config,
              "configuration sources and where a key is read from"),
    Extractor("pipeline.operations", "3", "pipeline", operations,
              "retries, file reading, output formats, parallel work"),
)
