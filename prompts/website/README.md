# Website prompts

Six website tasks, each at three levels of direction (L0, L1, L2) and in two
wordings (A, B): 36 prompts. One YAML file per task, in the format described in
[../README.md](../README.md). Written for task T1.1 in
[tasks.md](../../tasks.md). T1.2 checked every prompt for leaks: the verdict
and reason for each one are in [leak-check.md](leak-check.md), and the rules
are in [docs/leak-check.md](../../docs/leak-check.md).

## The tasks

The plan lists eight example website tasks. These six were kept because each
is a different kind of page, so the model faces different choices:

| File | Task | Kind of page |
| --- | --- | --- |
| [bakery-landing.yaml](bakery-landing.yaml) | Bakery website | Local business: sells itself to neighbors, shows hours and prices |
| [pricing-page.yaml](pricing-page.yaml) | Pricing page for software | Commercial conversion: compares plans and terms, asks for sign-up |
| [portfolio.yaml](portfolio.yaml) | Personal portfolio | One person's identity and voice, a gallery of past work |
| [event-page.yaml](event-page.yaml) | Event page | Time-bound: date, place, schedule, rules and booking |
| [todo-app.yaml](todo-app.yaml) | To-do list app | Interactive tool: input, state, sorting, data kept between visits |
| [dashboard.yaml](dashboard.yaml) | Dashboard | Data display: key figures, charts and warnings read at a glance |

Left out: the restaurant menu (another local food business, close to the
bakery) and the blog home (a personal content list, close to the portfolio).
"Small" was dropped from "small dashboard" because it can read as a layout
direction.

## The levels

- **L0 Bare**: the request only, as short as the plan's "Make a website for a
  bakery." It names the kind of page and nothing else.
- **L1 Brief**: L0 plus one or two sentences of purpose and audience (who the
  page is for and what it must help them do). No content details.
- **L2 Directed**: a realistic full brief: names, content, prices or figures,
  required sections, tone, and a color and type direction.

L0 and L1 must not name or imply a style, color, font, library, framework,
layout, component, dark mode or technology, and ask for no file format. No
level asks for a file format, a single file or a technology; every extra
instruction shifts the default being measured. The L1 wording of a task (a
sourdough bakery, freelancers, a food bank) is content: it describes the
business or the audience, not the page. Such content can still suggest a
look, and [leak-check.md](leak-check.md) records where it does. L1 also
avoids words that say how a page should read or that share a root with a page
pattern, such as "at a glance" or "compare".

Each L2 points the look **away** from what models are expected to produce by
default for that task, so that prompt sensitivity can be measured; each
direction differs from the others. An L2 says what it wants and never names
the default it moves away from, not even to forbid it: "flat, solid color",
not "no gradients". A default that then appears in an output cannot have come
from the prompt. The intended direction, and the default it moves away from,
is a comment above L2 in each file. The expected defaults are guesses until
the pilot (T1.7) measures them; after it, each direction is checked against
the measured defaults.

Two L2 briefs set a realistic technical constraint, stated as a need and not
as a technology: the dashboard must work with no internet connection, and the
to-do app must keep tasks on the device between visits with no accounts or
sign-in. Both will move the technology choices for those tasks. The other L2
briefs ask for features (such as a pre-order or booking form) but set no
technical constraint.

## The wordings

The two wordings of a cell ask for the same thing with the same information,
in different words:

- **A** is an imperative ("Make ..."). At L2 it is a structured brief with
  labelled lines and lists.
- **B** is a request ("Can you build ...?"). At L2 it is prose in the client's
  own voice ("we", "I"), and it says "please" once.

So that a difference between A and B can be read as a wording effect, this
split is the same for every task. Both L2 wordings carry identical facts.

A and B differ in several ways at once: mood, verb, length and, at L2, layout
and voice. B is the longer one at every level. The leak check kept this on
purpose, so that the pair covers more of how people ask. A difference between
A and B is therefore one bundled wording effect, and cannot be put down to
the question form, the verb or the length alone.

## Invented content

All names, places and figures are invented. Towns (Wrenmoor, Fennlow,
Marrowick, Ostrey) are made up so that no street address can be real. Emails
use `example.com`, and phone numbers use the 555-01xx range kept for fiction.
No prompt uses text from the private catalogues.

Spelling, dates and prices follow US usage in every prompt, so that no prompt
hints at a different locale from the others.

The to-do app's example tasks are due in March 2027, the event is in April
2027 and the dashboard is dated March 2027. A page that reads the clock looks
different depending on the day it is rendered, so the renderer should use a
fixed date (see [docs/leak-check.md](../../docs/leak-check.md)).

## Versions

Each file has a `prompt_set_version`. **Any change to the text of any prompt
in a file raises that file's version** ("1" to "2", and so on), however small
the change, because records carry the version and results from different texts
must not be mixed. Changes to comments or `notes` only do not need a new
version.

[tests/test_website_prompts.py](../../tests/test_website_prompts.py) pins each
file's version together with a fingerprint of its texts in `EXPECTED`. Any
text change makes that test fail until `EXPECTED` is updated, so no change goes
unnoticed. The test cannot tell whether the version was raised: raise it in the
same change, then copy the new version and the fingerprint that the failing
test prints into `EXPECTED`. A reviewer checks that both values changed
together.

Before the first run, texts may be corrected without a new version. Version
"1" was revised twice that way, before any run: after review (four files:
bakery-landing, dashboard, pricing-page and todo-app), and after the leak
check (all six files; see [leak-check.md](leak-check.md)).

## Checks

`python -m pytest tests/test_website_prompts.py` loads every prompt and
checks:

- 6 tasks x 3 levels x 2 wordings = 36 prompts, each file's version and text
  fingerprint equal to the pinned values, and an L2 direction comment;
- every prompt names its task's subject, and names no format or technology
  word from a list (also inside hyphenated compounds such as "React-based"
  or "single-page");
- L0 and L1 contain none of a list of style, color, type, layout, component
  and technology words (also inside compounds such as "dark-mode" or
  "two-column"), none of the words the leak check removed ("glance",
  "overview", "compare"), and no invented details (numbers, emails, quotes);
- no L2 names a common default (gradient, shadow, rounded, card, icon, emoji,
  "most popular" and others), so none can be named in order to forbid it;
- no prompt uses a listed British spelling;
- each level is longer than the one before;
- every A opens with "Make" and every B with "Can you build" and a question;
  "please" appears once in each L2 B and nowhere else;
- the two wordings of each cell differ (word-sequence similarity below a
  limit);
- the two L2 wordings have the same numbers, emails and quoted text in the
  same order (so swapped prices are caught), the same color and type words,
  each listed invented name, and no capitalized name found in only one; the
  L2 color and type words differ between tasks;
- contact details are `example.com` emails and 555-01xx numbers only.

These checks are mechanical. A word list cannot catch every hint, so the T1.2
leak check read each prompt. After any change to a prompt, read it again
against [docs/leak-check.md](../../docs/leak-check.md) and add the result to
[leak-check.md](leak-check.md).
