"""Imports and libraries of a pipeline output.

Imports are read from code with comments removed. A name counts as a third
party library only when it is in a table here: a name that is neither in the
table, nor the language's own, nor a file of the output, goes to
``other_imports``, as it may be either.
"""

import re
import sys

from extractors.base import Extractor
from extractors.common.response import get_doc, result, NO_INPUT
from extractors.pipeline.source import get_output

SUPPORTED = ("python", "javascript", "typescript", "go", "rust", "ruby", "r")
MAX_IMPORTS = 500

# import name -> library name
PYTHON = {name: name for name in """
requests httpx aiohttp urllib3 pandas numpy polars pyarrow duckdb sqlalchemy
sqlmodel peewee psycopg psycopg2 asyncpg pymysql pymongo redis pyodbc boto3
click typer docopt rich pydantic pandera jsonschema cerberus voluptuous
marshmallow schedule apscheduler airflow prefect dagster luigi celery rocketry
tenacity backoff retrying retry loguru structlog cv2 wand pyvips imageio
skimage piexif exifread tqdm joblib pytz pendulum arrow pytest hypothesis
responses requests_mock freezegun openpyxl xlsxwriter matplotlib scipy sklearn
dask pyspark flask fastapi lxml toml tomli orjson ujson msgspec ijson filelock
tabulate colorama environs platformdirs humanize great_expectations
connectorx fastavro zstandard pillow_heif seaborn plotly""".split()}
PYTHON.update({
    "PIL": "pillow", "cv2": "opencv-python", "yaml": "pyyaml",
    "dotenv": "python-dotenv", "dateutil": "python-dateutil",
    "bs4": "beautifulsoup4", "decouple": "python-decouple",
    "skimage": "scikit-image", "sklearn": "scikit-learn", "attr": "attrs",
    "attrs": "attrs", "pydantic_settings": "pydantic-settings", "vcr": "vcrpy",
    "psycopg2": "psycopg2", "google": "google-cloud", "MySQLdb": "mysqlclient",
})
JAVASCRIPT = frozenset("""
axios node-fetch got undici superagent csv-parse csv-parser csv-writer
papaparse fast-csv dotenv node-cron cron node-schedule agenda sharp jimp gm
imagemagick pg mysql mysql2 better-sqlite3 sqlite3 sqlite mongodb mongoose knex
prisma @prisma/client sequelize drizzle-orm winston pino bunyan log4js yargs
commander minimist zod joi ajv yup p-retry axios-retry async-retry retry p-limit
piscina glob fast-glob fs-extra jest vitest mocha chai exifr exif-parser
piexifjs lodash date-fns dayjs moment luxon js-yaml yaml chalk ora""".split())
NODE_BUILTINS = frozenset("""
assert async_hooks buffer child_process cluster console crypto dgram dns events
fs http http2 https module net os path perf_hooks process querystring readline
repl stream string_decoder test timers tls tty url util v8 vm wasi
worker_threads zlib""".split())
RUBY_STDLIB = frozenset("""csv json yaml logger optparse net/http uri fileutils
time date set pathname open-uri digest securerandom benchmark thread""".split())
RUBY_GEMS = frozenset("""httparty faraday sqlite3 pg sequel activerecord
mini_magick image_processing ruby-vips rufus-scheduler whenever dotenv thor
nokogiri rspec parallel""".split())
R_BASE = frozenset("base stats utils methods graphics grDevices datasets tools "
                   "parallel".split())
R_PACKAGES = frozenset("""readr dplyr tidyr data.table ggplot2 DBI RSQLite httr
httr2 jsonlite yaml logger futile.logger testthat lubridate stringr purrr magick
validate pointblank arrow duckdb""".split())
RUST = frozenset("""tokio reqwest serde serde_json csv rusqlite sqlx clap anyhow
thiserror chrono log tracing env_logger image rayon regex flate2 walkdir""".split())

DATABASE = frozenset("""sqlite3 duckdb psycopg2 psycopg asyncpg pymysql
mysqlclient pymongo redis sqlalchemy sqlmodel peewee pyodbc connectorx pg mysql
mysql2 better-sqlite3 sqlite mongodb mongoose knex prisma @prisma/client
sequelize drizzle-orm node:sqlite database/sql github.com/mattn/go-sqlite3
modernc.org/sqlite github.com/lib/pq github.com/jackc/pgx RSQLite DBI rusqlite
sqlx sequel activerecord""".split())
SCHEDULING = frozenset("""schedule apscheduler airflow prefect dagster luigi
celery rocketry node-cron cron agenda node-schedule github.com/robfig/cron
github.com/go-co-op/gocron rufus-scheduler whenever""".split())

_PY_IMPORT = re.compile(r"^[ \t]{0,40}import ([\w. ,]{1,300})", re.M)
_PY_FROM = re.compile(r"^[ \t]{0,40}from ([\w.]{1,120}) import\b", re.M)
_JS_IMPORT = re.compile(
    r"""(?:\brequire\( ?|\bimport\( ?|\bfrom |^[ \t]{0,40}import )["']"""
    r"""([^"'\n ]{1,200})["']""", re.M)
_GO_BLOCK = re.compile(r"^[ \t]{0,40}import ?\(([^)]{0,4000})\)", re.M)
_GO_LINE = re.compile(r'^[ \t]{0,40}import (?:[\w.]{1,40} )?"([^"\n]{1,200})"', re.M)
_GO_PATH = re.compile(r'"([^"\n]{1,200})"')
_RUST_USE = re.compile(r"^[ \t]{0,40}(?:pub )?use ([a-z_]\w{0,80})::", re.M)
_RUBY = re.compile(r"""^[ \t]{0,40}require ["']([\w./-]{1,100})["']""", re.M)
_R = re.compile(r"""\b(?:library|require)\( ?["']?([A-Za-z][\w.]{0,60})["']? ?[,)]""")


def _python(item):
    names = []
    for match in _PY_IMPORT.finditer(item.parts.bare):
        for piece in match[1].split(","):
            words = piece.split()
            if words:
                names.append(words[0])
    names += [m[1] for m in _PY_FROM.finditer(item.parts.bare)]
    for name in names:
        top = name.split(".")[0]
        if not top:                      # a relative import
            continue
        if top == "urllib3" and name == "urllib3.util.retry":
            yield "urllib3", "urllib3"
        elif top == "__future__" or top in sys.stdlib_module_names:
            yield top, None
        else:
            yield top, PYTHON.get(top, "")


def _javascript(item):
    for match in _JS_IMPORT.finditer(item.parts.code):
        name = match[1]
        if name.startswith((".", "/", "http:", "https:")):
            continue
        parts = name.split("/")
        if name.startswith("node:"):
            yield parts[0], None
            continue
        top = "/".join(parts[:2]) if name.startswith("@") else parts[0]
        if top in NODE_BUILTINS:
            yield "node:" + top, None
        else:
            yield top, top if top in JAVASCRIPT or top.startswith("@aws-sdk/") else ""


def _go(item):
    text = item.parts.code
    names = [m[1] for m in _GO_LINE.finditer(text)]
    for block in _GO_BLOCK.finditer(text):
        names += [m[1] for m in _GO_PATH.finditer(block[1])]
    for name in names:
        parts = name.split("/")
        if "." not in parts[0]:
            yield name, None
        else:
            top = "/".join(parts[:3])
            yield top, top


def _named(pattern, text, own, known):
    for match in pattern.finditer(text):
        name = match[1]
        yield name, None if name in own else name if name in known else ""


def _imports(item):
    if item.language == "python":
        return _python(item)
    if item.language in ("javascript", "typescript"):
        return _javascript(item)
    if item.language == "go":
        return _go(item)
    if item.language == "rust":
        return _named(_RUST_USE, item.parts.bare,
                      {"std", "core", "alloc", "crate", "self", "super"}, RUST)
    if item.language == "ruby":
        return _named(_RUBY, item.parts.code, RUBY_STDLIB, RUBY_GEMS)
    return _named(_R, item.parts.code, R_BASE, R_PACKAGES)


def _local_names(files):
    """Names a file of the output can be imported by."""
    names = set()
    for source in files:
        parts = source.path.split("/")
        names.update(parts[:-1])
        names.add(parts[-1].rsplit(".", 1)[0])
    return names


def _read(inputs):
    """``(imports, third party, unknown)`` or None where no program is in a
    language whose imports are read."""
    output = get_output(inputs)
    programs = [c for c in output.programs if c.language in SUPPORTED]
    if not programs:
        return None
    local = _local_names(get_doc(inputs).files)
    imports, third, other = set(), set(), set()
    for item in programs:
        for name, library in _imports(item):
            if library == "":
                if name in local:
                    continue
                other.add(name)
            elif library:
                third.add(library)
            imports.add(name)
    return imports, third, other


def read_imports(inputs):
    return inputs.cached("t2.8.imports", lambda: _read(inputs))


def libraries(inputs):
    output = get_output(inputs)
    if not output.programs:
        return dict(NO_INPUT)
    doc = get_doc(inputs)
    read = read_imports(inputs)
    if read is None:
        return result(doc, dict.fromkeys(
            ("imports", "third_party", "other_imports", "stdlib_only",
             "database_libraries", "scheduling_libraries")))
    imports, third, other = read
    unread = any(c.language not in SUPPORTED and c.language not in
                 ("shell", "sql", "powershell", "batch") for c in output.programs)
    used = imports | third
    return result(doc, {
        "imports": sorted(imports)[:MAX_IMPORTS],
        "third_party": sorted(third)[:MAX_IMPORTS],
        "other_imports": sorted(other)[:MAX_IMPORTS],
        "stdlib_only": False if third else None if other or unread else True,
        "database_libraries": sorted(used & DATABASE),
        "scheduling_libraries": sorted(used & SCHEDULING),
    })


EXTRACTOR = Extractor("pipeline.libraries", "1", "pipeline", libraries,
                      "imports, third-party, database and scheduling libraries")
