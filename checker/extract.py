"""The deterministic extractor: the answers a response labels plainly.

:func:`extract` returns :class:`checker.answers.Answers`; a model-based
extractor would return the same. It reads only a value that follows its own
label, in a sentence, a table or a few named forms (a fitted line, an
interval, a decision, a keyed table). It takes no value from code, and it
decides nothing: statements in conditions, comparisons and checks are marked
``hedged``, and the grader refuses to call an answer wrong where the text
leaves room. What it finds and what it cannot is in checker/README.md.
"""

import datetime
import math
import re
from functools import lru_cache

from checker import labels, units
from checker.answers import EXTRACTED, Answers, Stated
from checker.formulas import level_quantities
from checker.reading import clean, read
from extractors.common.numbers import NUMBER, parse
from extractors.common.response import split_fences, PLAIN

MAX_TEXT = 1_000_000
MAX_CANDIDATES = 50
MAX_SEEN = 20_000
MAX_LABEL = 100

HEDGE = (r"\b(?:if|would|could|instead|not|wrong|incorrect|mistakes?|naive(?:ly)?|"
         r"alternative(?:ly)?|otherwise|suppose|examples?|before|had|were|trial|"
         r"first (?:try|attempt|guess|pass)|simple interest|check(?:s|ing)?|verif\w{0,6}|"
         r"sensitivity|rejected|initial(?:ly)? (?:guess|try)|options?|scenarios?|"
         r"variants?|whether|one[- ](?:sided|tailed)")
# Words that are plain speech in an answer about the case without air.
AIRLESS = r"|without|ignor\w{0,4}|neglect\w{0,4}|compar\w{0,6}"
_HEDGED = re.compile(HEDGE + AIRLESS + r")\b", re.IGNORECASE)
_HEDGED_NO_AIR = re.compile(HEDGE + r")\b", re.IGNORECASE)
_NO_AIR = re.compile(r"\b(?:no[- ](?:air|drag)|without (?:air|drag)|vacuum|drag[- ]free|"
                     r"ignoring (?:air|drag)|ideal)\b", re.IGNORECASE)
_WITH_AIR = re.compile(r"\b(?:with (?:air|drag)|compar\w{0,6}|vs|versus|and)\b",
                       re.IGNORECASE)
_HYPOTHESES = re.compile(r"H_?\{?[01a]\}?\b|hypothes", re.IGNORECASE)

_CLAUSE = re.compile(r";|,(?=\s)|\band\b|\bwhich\b|\bso that\b|—|(?<=\.)\s")
_FILLER = re.compile(r"^(?:(?:so|thus|therefore|hence|then|finally|answer|result|final "
                     r"answer|this gives|giving|the|your|its|a|an|here)\b[ ,:]{0,3}){0,4}",
                     re.IGNORECASE)
_CONNECTOR = re.compile(r"=|≈|≃|:|\bis(?: (?:therefore|about|approximately|then|thus|"
                        r"just))?\b|\bof(?= ?[$€£]?\d)")
_PAREN = re.compile(r"\(([^()]{0,30})\)")
_SYMBOL = r"(?: [A-Za-zΔτσθ](?:_\{?[\w,+\-]{1,8}\}?)?'?)?"
_SYMBOLIC = re.compile(r"[A-Za-zΔτσθμν̄ŷ][\w,^{}'̄\-]{0,5}|R\^2")
_NOT_SYMBOL = re.compile(r"max|min|lim|req|tot|new|old|two|one", re.IGNORECASE)
_LEAD = re.compile(r"^(?:(?:about|approximately|approx\.?|roughly|only|just|therefore|"
                   r"then|thus|~)\s+){0,3}[+]?", re.IGNORECASE)
_TRAILING = re.compile(r"(?:[ ]*\([^()]{0,80}\))?[ .!:,*_]{0,6}$")
_WORDS_AFTER = re.compile(
    r"(?:^| )(?:(?:of |w\.?)?water(?: column)?|head|per month|each month|a month|monthly|"
    r"each|per screw|on each screw|rounded|exactly|in total|total|at the wall)$",
    re.IGNORECASE)
_EXPRESSION = re.compile(r"[×·*/^]|\d ?[+\-] ?\d")
_FRACTION = re.compile(r"(\d{1,6})/(\d{1,6})(?![\d.])")
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})\b")
_MONTHS = ("january february march april may june july august september october "
           "november december").split()
_NAMED_DATE = re.compile(r"(?:([A-Z][a-z]{2,8})\.? (\d{1,2}),? (\d{4})|(\d{1,2}) "
                         r"([A-Z][a-z]{2,8})\.?,? (\d{4}))\b")


@lru_cache(maxsize=None)
def _label_pattern(pattern):
    return re.compile(rf"(?:{pattern}){_SYMBOL}", re.IGNORECASE)


def _date(text):
    """``(ISO date, rest)`` for a date at the start of ``text``, or None."""
    found = _ISO.match(text)
    if found:
        year, month, day = (int(g) for g in found.groups())
    else:
        found = _NAMED_DATE.match(text)
        if not found:
            return None
        name = (found[1] or found[5]).lower()
        month = next((i for i, m in enumerate(_MONTHS, 1)
                      if m == name or m[:3] == name[:3] and len(name) == 3), None)
        if month is None:
            return None
        year, day = int(found[3] or found[6]), int(found[2] or found[4])
    try:
        return datetime.date(year, month, day).isoformat(), text[found.end():]
    except ValueError:
        return None


def _numbers(pattern, text):
    return {float(v.replace(",", ""))
            for v in re.findall(pattern, text, re.IGNORECASE)[:5]}


def _tidy(tail):
    """The unit text after a number, with brackets and filler words gone."""
    tail = re.sub(r"^/ ?mo(?:nth)?(?![\w])", "", tail.strip()).strip()
    for _ in range(3):
        tail = _TRAILING.sub("", tail).strip()
    for _ in range(3):
        tail = _WORDS_AFTER.sub("", tail).strip()
    return tail


def _value(text, kind):
    """``(value, unit text)`` of the whole of ``text``, or None."""
    text = _LEAD.sub("", text.strip().strip("*_ "))
    text = re.sub(r"^[$€£] ?", "", text)
    if kind == "date":
        found = _date(text)
        return (found[0], "date") if found and not _tidy(found[1]) else None
    fraction = _FRACTION.match(text)
    if fraction:
        if not int(fraction[2]):
            return None
        value, tail = int(fraction[1]) / int(fraction[2]), text[fraction.end():]
    else:
        match = NUMBER.match(text)
        if not match:
            return None
        value, tail = parse(match).value, text[match.end():]
    if not math.isfinite(value) or abs(value) > 1e300:
        return None
    tail = re.sub(r"^ ?: ?1\b", "", tail)           # a ratio written n:1
    if tail[:1].isdigit() or re.match(r" ?[.,]?\d", tail):
        return None
    return value, _tidy(tail)


def _final(rest, kind):
    """The last part of a chain ``a = b = c``, cut at the end of the clause."""
    rest = _CLAUSE.split(rest, maxsplit=1)[0]
    part = re.split(r"=|≈|≃", rest)[-1].strip().rstrip(".")
    return part, _value(part, kind)


def _label(text):
    """``(label, unit in brackets)`` from the text before a value."""
    text = _FILLER.sub("", text.strip().strip("*_| ").strip())
    unit = None

    def drop(match):
        nonlocal unit
        inside = re.sub(r"^in ", "", match[1].strip())
        inside = re.sub(r" (?:of )?water$", "", inside)
        if units.canonical(inside) or inside in ("%", "$", "€", "£"):
            unit = inside
            return ""
        if _SYMBOLIC.fullmatch(inside) and not _NOT_SYMBOL.search(inside):
            return ""
        if re.fullmatch(r"(?:at )?\d{1,3}(?:\.\d{1,3})? ?mL", inside):
            return " " + inside.removeprefix("at ")
        return match[0]

    text = _PAREN.sub(drop, text)
    return re.sub(r" {2,}", " ", text).strip().strip("*_ ").strip(), unit


class _Reader:
    def __init__(self, reference, level, text, truncated):
        self.reference, self.level, self.text = reference, level, text
        self.task = reference["task_id"]
        self.listed = set(level_quantities(reference["levels"][level]))
        self.found = {}
        self.inputs = {}          # name -> set of values; None if unreadable
        self.unreadable = set()
        prose, blocks = split_fences(text)
        working = "\n".join(["\n".join(prose),
                             *(b.body for b in blocks if b.language in PLAIN)])
        self.sentences, self.tables = read(working)
        self.truncated = truncated
        doubt = labels.DOUBTS.get(self.task)
        self.doubts = {}
        if doubt and re.search(doubt[0], text, re.IGNORECASE):
            self.doubts = dict.fromkeys(doubt[1], doubt[2])
        self.wanted = {name: pattern for name, pattern
                       in labels.QUANTITIES[self.task].items() if name in self.listed}
        self.input_labels = labels.LABELLED_INPUTS.get(self.task, {})

    # --- recording ----------------------------------------------------------

    def quantity(self, name):
        return self.reference["quantities"][name]

    def add(self, name, value, unit, hedged):
        if name not in self.listed:
            return
        quantity = self.quantity(name)
        if quantity["unit"] == "currency" and not unit:
            unit = "currency"
        doubt = self.doubts.get(name)
        if self.truncated:
            doubt = "the response is cut off"
        statement = Stated(value, unit, source=EXTRACTED, hedged=hedged, doubt=doubt)
        held = self.found.setdefault(name, [])
        if statement not in held and len(held) < MAX_CANDIDATES:
            held.append(statement)

    def add_input(self, name, value, unit):
        wanted = self.input_labels[name][1]
        quantity = {"unit": wanted}
        scale = units.conversion(unit or ("1" if wanted == "1" else ""), quantity)
        values = self.inputs.setdefault(name, set())
        values.add(None if scale is None else value)

    def hedged(self, name, *texts):
        pattern = _HEDGED_NO_AIR if name.endswith("_no_air") else _HEDGED
        return any(pattern.search(text) for text in texts)

    def routed(self, name, context):
        """A projectile figure under a heading or column for no air."""
        if (self.task == "projectile-drag" and _NO_AIR.search(context)
                and not _WITH_AIR.search(context)):
            other = {"range": "range_no_air"}.get(name)
            return other or (None if not name.endswith("_no_air") else name)
        return name

    def take(self, label, rest, heading, sentence, header_unit=None):
        """Record the value in ``rest`` for every quantity or input whose
        label ``label`` is."""
        label, unit = _label(label)
        if not label or len(label) > MAX_LABEL:
            return
        for name, pattern in self.wanted.items():
            if not _label_pattern(pattern).fullmatch(label):
                continue
            kind = self.quantity(name).get("type", "number")
            if kind in ("choice", "list"):
                continue
            part, value = _final(rest, kind)
            target = self.routed(name, heading if _NO_AIR.search(heading) else sentence)
            if target is None:
                continue
            if value is None:
                self.note_unreadable(target, part, kind)
                continue
            own = value[1] or unit or header_unit or ""
            if value[1] and units.conversion(value[1], self.quantity(name)) is None \
                    and kind != "date":
                self.note_unreadable(target, part, kind)
                continue
            self.add(target, value[0], own,
                     self.hedged(target, sentence, heading if target == name else ""))
        for name, (pattern, _) in self.input_labels.items():
            if _label_pattern(pattern).fullmatch(label):
                part, value = _final(rest, "number")
                if value is None:
                    if re.search(r"\d", part) and not _EXPRESSION.search(part):
                        self.inputs.setdefault(name, set()).add(None)
                elif not self.hedged(name, sentence, heading):
                    self.add_input(name, value[0], value[1] or unit or header_unit)

    def note_unreadable(self, name, part, kind):
        """A labelled statement with a number that cannot be read: the
        response may say something else there than elsewhere."""
        if kind == "date":
            if re.search(r"\d{4}", part):
                self.unreadable.add(name)
        elif (re.search(r"\d", part) and not _EXPRESSION.search(part)
                and not _date(part)):
            self.unreadable.add(name)

    # --- sentences ----------------------------------------------------------

    def read_sentences(self):
        for sentence in self.sentences:
            text, heading = sentence.text, sentence.heading
            if (self.task in ("hypothesis-test",) and _HYPOTHESES.search(text)
                    and not re.search(r"\bp(?:[- ]value)? ?[=≈]", text)):
                continue
            for clause in _CLAUSE.split(text):
                connector = _CONNECTOR.search(clause)
                if connector:
                    self.take(clause[:connector.start()], clause[connector.end():],
                              heading, text)

    # --- tables -------------------------------------------------------------

    def read_tables(self):
        for table in self.tables:
            if self.keyed_table(table) or len(table.header) < 2:
                continue
            columns = self.value_columns(table.header)
            for row in table.rows:
                if len(row) < 2 or not row[0]:
                    continue
                unit_column = next((row[i] for i, h in enumerate(table.header)
                                    if h.lower() in ("unit", "units") and i < len(row)),
                                   None)
                for index, header_unit, context in columns:
                    if index >= len(row) or row[index] in ("", "-", "—", "–"):
                        continue
                    sentence = " ".join([table.header[index] if index < len(table.header)
                                         else "",
                                         *(c for i, c in enumerate(row) if i != index)])
                    self.take(row[0], row[index],
                              context or table.heading,
                              f"{sentence} {row[index]}",
                              header_unit or unit_column)

    def value_columns(self, header):
        """``(column, unit, condition)`` for the columns that hold values."""
        found = []
        for index, title in enumerate(header[1:], 1):
            label, unit = _label(title)
            plain = re.sub(r" (?:of )?water$", "", title.strip())
            plain = {"m water": "m", "meters of water": "m", "metres of water": "m",
                     "mH2O": "m"}.get(title.strip(), plain)
            if _NO_AIR.search(title) or re.search(r"\bwith (?:air|drag)|^drag$", title,
                                                  re.IGNORECASE):
                found.append((index, unit, title.replace("With", "with")))
            elif units.canonical(plain) or plain in ("%", "$"):
                found.append((index, plain, ""))
            elif len(header) == 2 and not re.search(r"formula|note|equation|source",
                                                    title, re.IGNORECASE):
                found.append((index, unit, ""))
            elif re.fullmatch(r"(?:final )?(?:value|answer|result|amount|magnitude)s?",
                              label, re.IGNORECASE):
                found.append((index, unit, ""))
        return found

    def keyed_table(self, table):
        reader = {"loan-amortization": self.schedule_table,
                  "titration-curve": self.titration_table,
                  "hypothesis-test": self.measurement_table,
                  "least-squares-fit": self.residual_table}.get(self.task)
        return bool(reader and reader(table))

    @staticmethod
    def columns(table, pattern):
        return [i for i, title in enumerate(table.header)
                if re.fullmatch(pattern, title.strip(), re.IGNORECASE)]

    @staticmethod
    def cell(row, index):
        if index >= len(row):
            return None
        found = _value(row[index], "number")
        return found[0] if found else None

    def schedule_table(self, table):
        number = self.columns(table, r"(?:payment ?(?:#|no\.?|number)|month|#|no\.?|"
                                     r"period|n|payment)")
        balance = self.columns(table, r"(?:remaining |closing |ending |new )?balance"
                                      r"(?: ?(?:remaining|after(?: payment)?|\([^)]*\)))?")
        if not number or not balance:
            return False
        numbered = [(self.cell(row, number[0]), row) for row in table.rows]
        if [n for n, _ in numbered] != list(range(1, 61)):
            return True             # a part of a schedule says nothing certain
        rows = [row for _, row in numbered]
        heading = table.heading
        hedged = self.hedged("schedule_rows", heading)
        self.add("schedule_rows", 60, "1", hedged)
        for month in (1, 12, 24, 36, 48, 59, 60):
            value = self.cell(rows[month - 1], balance[0])
            if value is not None:
                self.add(f"balance_after_{month}", value, "currency", hedged)
        payment = [i for i in self.columns(
            table, r"(?:monthly |total )?payment(?: amount)?(?: ?\([^)]*\))?")
            if i != number[0]]
        if len(payment) == 1:
            value = self.cell(rows[59], payment[0])
            if value is not None:
                self.add("final_payment", value, "currency", hedged)
        dates = self.columns(table, r"(?:payment |due )?date(?: due)?")
        if len(dates) == 1:
            for name, row in (("first_payment_date", rows[0]),
                              ("final_payment_date", rows[59])):
                found = row[dates[0]] if dates[0] < len(row) else ""
                found = _value(found, "date")
                if found:
                    self.add(name, found[0], "date", hedged)
        return True

    def titration_table(self, table):
        volume = [i for i, title in enumerate(table.header)
                  if re.search(r"\bmL\b", title)
                  and re.search(r"vol|naoh|base|^v", title, re.IGNORECASE)]
        ph = self.columns(table, r"(?:calculated )?pH")
        if len(volume) != 1 or len(ph) != 1:
            return False
        for row in table.rows:
            cells = [re.sub(r" ?\([^()]{0,40}\)$", "", c) for c in row]
            amount, value = self.cell(cells, volume[0]), self.cell(cells, ph[0])
            if amount is None or value is None:
                continue
            name = f"ph_{amount:g}".replace(".", "_") + "_ml"
            self.add(name, value, "pH", self.hedged(name, table.heading, " ".join(row)))
        return True

    def keyed(self, table, name, key, value):
        """A list quantity from a table that has every key exactly once."""
        if name not in self.listed or len(value) != 1:
            return
        keys = self.quantity(name)["keyed_by"]["values"]
        found = {}
        for row in table.rows:
            at, stated = self.cell(row, key), self.cell(row, value[0])
            if at is None:
                continue
            if at in found or stated is None:
                return
            found[at] = stated
        if sorted(found) == sorted(keys):
            self.add(name, found, self.quantity(name)["unit"],
                     self.hedged(name, table.heading))

    def measurement_table(self, table):
        key = self.columns(table, r"(?:measurement|value|observation|length|data|x)"
                                  r"(?:[ _]?\{?i\}?)?(?: ?\([^)]*\))?")
        if not key:
            return False
        self.keyed(table, "differences", key[0], self.columns(
            table, r"(?:signed )?(?:difference|d(?:_?\{?i\}?)?)(?: ?\([^)|]*\))?|"
                   r"x(?:_?i)? ?- ?50"))
        self.keyed(table, "ranks", key[0], self.columns(
            table, r"rank(?: of (?:\|d\||the absolute difference))?"))
        return True

    def residual_table(self, table):
        key = self.columns(table, r"x(?:_?\{?i\}?)?(?: ?\([^)]*\))?")
        if not key:
            return False
        self.keyed(table, "residuals", key[0], self.columns(
            table, r"residuals?(?: ?(?:\([^)^²]*\)|e(?:_?i)?|r(?:_?i)?))?"))
        return True

    # --- named forms --------------------------------------------------------

    def fitted_line(self):
        if self.task != "least-squares-fit":
            return
        n = r"(-?\d{1,6}(?:\.\d{1,10})?)"
        forms = ((re.compile(rf"(?:ŷ|\by) ?= ?{n} ?\+ ?{n} ?[·*×]? ?x\b"), (2, 1, 1)),
                 (re.compile(rf"(?:ŷ|\by) ?= ?{n} ?[·*×]? ?x ?([+-]) ?{n}(?![\d.])"),
                  (1, 3, 2)))
        for sentence in self.sentences:
            for pattern, (slope, intercept, sign) in forms:
                for found in list(pattern.finditer(sentence.text))[:5]:
                    value = float(found[intercept])
                    if sign == 2 and found[sign] == "-":
                        value = -value
                    for name, number in (("slope", float(found[slope])),
                                         ("intercept", value)):
                        self.add(name, number, "1", self.hedged(
                            name, sentence.text, sentence.heading))

    def intervals(self):
        subject = {"hypothesis-test": (r"", ("ci95_low", "ci95_high")),
                   "least-squares-fit": (r"slope", ("slope_ci95_low",
                                                    "slope_ci95_high"))}.get(self.task)
        if not subject:
            return
        number = r"(-?\d{1,6}(?:\.\d{1,10})?)"
        interval = re.compile(rf"[\[(] ?{number} ?, ?{number} ?[\])]|"
                              rf"(?<![\d.]){number} to {number}(?![\d])")
        for sentence in self.sentences:
            text = sentence.text
            named = re.search(r"95 ?% (?:two-sided )?(?:confidence interval|CI\b)", text,
                              re.IGNORECASE)
            if (not named or subject[0] and not re.search(subject[0], text, re.IGNORECASE)
                    or re.search(r"difference|median|wilcoxon|hodges|pseudo", text,
                                 re.IGNORECASE)):
                continue
            if self.task == "least-squares-fit" and re.search(
                    r"intercept|spring|stiffness", text, re.IGNORECASE):
                continue
            found = list(interval.finditer(text, named.end()))
            if len(found) != 1:
                continue
            low, high = [float(g) for g in found[0].groups() if g is not None]
            if low < high:
                for name, value in zip(subject[1], (low, high)):
                    self.add(name, value, "1",
                             self.hedged(name, text, sentence.heading))

    def decisions(self):
        if self.task == "hypothesis-test":
            self.hypothesis_decision()
        elif self.task == "cantilever-beam":
            pattern = re.compile(
                r"\b(deflection|stress)(?: (?:limit|criterion|constraint|requirement))? "
                r"(?:governs|controls)\b|\bgoverning (?:limit|criterion|constraint)"
                r"(?: is|:) (?:the )?(deflection|stress)\b", re.IGNORECASE)
            for sentence in self.sentences:
                for found in list(pattern.finditer(sentence.text))[:5]:
                    word = (found[1] or found[2]).lower()
                    self.add("governing_limit", word, "1", self.hedged(
                        "governing_limit", sentence.text, sentence.heading))

    def hypothesis_decision(self):
        null = r"(?:the )?(?:null(?: hypothesis)?\b|H_?\{?0\}?(?![\w]))"
        kept = re.compile(
            rf"(?:fail(?:s|ed)? to|do(?:es)? not|don't|doesn't|cannot|can't|can not) "
            rf"reject {null}|{null} (?:is|was) not rejected|{null} "
            rf"(?:cannot|can't|can not) be rejected", re.IGNORECASE)
        # "reject" as the answer's own act, not as what a rule would need
        rejected = re.compile(
            rf"(?:^|[:,;] ?|\b(?:we(?: (?:can|therefore|thus|hence|also))?|so|therefore|"
            rf"thus|hence|decision|conclusion) )[*_ ]{{0,3}}reject(?:s|ed)? {null}|"
            rf"{null} (?:is|was) rejected", re.IGNORECASE)
        negation = re.compile(r"\b(?:not|no|never|cannot|can't|fail\w{0,3}|unable|"
                              r"insufficient|neither|nor|don't|doesn't|won't)\b",
                              re.IGNORECASE)
        unsure = re.compile(r"\b(?:if|would|whether|when|unless|rule|criterion|had|could|"
                            r"might|may|should|need(?:s|ed)?|require[sd]?|in order)\b", re.IGNORECASE)
        name = "decision_l2" if self.level == "L2" else "decision"
        for sentence in self.sentences:
            text = sentence.text
            if "reject" not in text.lower() or unsure.search(text):
                continue
            hedged = self.hedged(name, sentence.heading)
            for _ in kept.findall(text)[:3]:
                self.add(name, "do_not_reject", "1", hedged)
            rest = kept.sub(" ", text)
            for found in list(rejected.finditer(rest))[:3]:
                if negation.search(rest[max(found.start() - 60, 0):found.start()]):
                    self.unreadable.add(name)
                else:
                    self.add(name, "reject", "1", hedged)

    # --- facts and inputs ---------------------------------------------------

    def facts(self):
        if self.task != "hypothesis-test":
            return (), ()
        text = self.text

        def has(pattern):
            return re.search(pattern, text, re.IGNORECASE) is not None

        tests = []
        if has(r"\bt[- ]tests?\b|student'?s t\b|\bt[- ]statistic"):
            tests.append("t")
        if has(r"\bz[- ]tests?\b"):
            tests.append("z")
        if has(r"wilcoxon|signed[- ]rank"):
            approximate = has(r"normal approximation|approximately normal")
            exact = has(r"\bexact\b")
            if approximate and not exact:
                corrected = has(r"continuity") and not has(
                    r"(?:no|without) (?:a )?continuity")
                tests.append("wilcoxon_normal_corrected" if corrected
                             else "wilcoxon_normal")
            elif exact and not approximate:
                tests.append("wilcoxon_exact")
            else:
                tests.append("wilcoxon")
        if has(r"\bsign test\b"):
            tests.append("sign_test")
        if has(r"permutation test|sign[- ]flip|randomi[sz]ation test"):
            tests.append("sign_flip_permutation")
        if has(r"bootstrap|bayes|mann[- ]whitney|chi[- ]squared? test"):
            tests.append("other")
        number = r"(0?\.\d{1,4}|\d{1,2}(?:\.\d{1,2})? ?%)"
        levels = set()
        normal = clean(text[:MAX_TEXT])
        for pattern in (rf"(?:α|\balpha\b) ?(?:=|of|is|:)? ?{number}",
                        r"(\d{1,2}(?:\.\d{1,2})? ?%) (?:significance )?level",
                        rf"significance level(?: of| =| is|:)? ?{number}"):
            for found in re.findall(pattern, normal, re.IGNORECASE)[:20]:
                value = float(found.rstrip("% "))
                levels.add(round(value if "%" in found else value * 100, 6))
        if not levels and self.level != "L2":
            levels = {5.0}
        return tuple(tests), tuple(sorted(levels))

    def searched_inputs(self):
        for name, patterns in labels.SEARCHED_INPUTS.get(self.task, {}).items():
            values = set()
            for pattern in patterns:
                for sentence in self.sentences:
                    values |= _numbers(pattern, sentence.text)
                for table in self.tables:
                    for row in table.rows[:200]:
                        values |= _numbers(pattern, " ".join(row))
            self.inputs[name] = values

    def conditions(self):
        found = {}
        quantities = self.reference["quantities"]
        for name in self.listed:
            for alternative in quantities[name].get("alternatives", ()):
                pattern = labels.MENTIONS.get(alternative["id"])
                if pattern and not re.search(pattern, self.text, re.IGNORECASE):
                    found[alternative["id"]] = False
        return found

    def seen(self):
        found = set()
        for index, match in enumerate(NUMBER.finditer(clean(self.text))):
            value = parse(match).value
            if math.isfinite(value):
                found.add(value)
            if index >= MAX_SEEN:
                break
        return tuple(sorted(found))

    def answers(self):
        self.read_sentences()
        self.read_tables()
        self.fitted_line()
        self.intervals()
        self.decisions()
        self.searched_inputs()
        tests, levels = self.facts()
        quantities = {name: tuple(found) for name, found in sorted(self.found.items())
                      if name not in self.unreadable}
        inputs = {name: values.copy().pop() for name, values in sorted(self.inputs.items())
                  if len(values) == 1 and None not in values}
        return Answers(quantities=quantities, inputs=inputs,
                       conditions=self.conditions(), tests=tests, levels=levels,
                       seen=self.seen(), extracted_inputs=frozenset(inputs))


def extract(reference, level, text, truncated=False):
    """The :class:`~checker.answers.Answers` found in ``text``, a response to
    the task of ``reference`` at ``level``. With ``truncated`` the response
    is cut off, and no mismatch in it is called wrong."""
    truncated = truncated or len(text) > MAX_TEXT
    text = text[:MAX_TEXT].replace("\r\n", "\n")
    return _Reader(reference, level, text, truncated).answers()
