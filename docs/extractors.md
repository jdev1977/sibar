# Extractors

`extractors/` (task T1.4) reads a generated output's files and records the
choices made in it as **features**: countable values stored in the run record
(see [record-format.md](record-format.md)), each with the name and version of
the extractor that produced it. Extractors read bytes only. They never run the
output's code and never use the network.

This page has four parts: how to run them, the interface new extractors
follow, the twelve website extractors, feature by feature, and the
[pipeline, math and engineering extractors](#pipeline-math-and-engineering-outputs-t28).

## Use

    python -m extractors --records data/runs/<batch-id>/records.jsonl
    python -m extractors --records FILE --record-id ID --only website.palette
    python -m extractors --dir FOLDER [--type website] [--only NAME]
    python -m extractors --list

| Option | Meaning |
|---|---|
| `--records FILE` | Add features to the records of a record file and rewrite it once, atomically (`write_records`). By default every record with status `ok` or `truncated` whose project type has extractors. |
| `--record-id ID` | Only this record (repeatable), whatever its status. |
| `--only NAME` | Run only this extractor (repeatable). Other extractors' features are kept. |
| `--dir FOLDER` | Print the features of the files in a folder as JSON; nothing is written. |
| `--list` | Each extractor's name, version, type and summary. |

Exit codes: 0 done; 1 done, but an extractor recorded an `error`; 2 refused
(bad option, missing or busy record file, a line that is not a valid record,
an unknown record id or extractor name). The record file is locked with the
runner's lock while it is rewritten; a file with bad or truncated lines is
refused rather than rewritten, as those lines would be lost.

Re-running replaces each extractor's earlier features and version
(`with_features`), so the same input gives a byte-identical file.

## The interface (for T2.8 and later types)

Code: [extractors/base.py](../extractors/base.py),
[extractors/registry.py](../extractors/registry.py).

```python
from extractors.base import Extractor

def extract(inputs):          # inputs: extractors.base.Inputs
    ...
    return {"status": "ok", "language": "python", "libraries": ["pandas"]}

EXTRACTOR = Extractor(
    name="pipeline.libraries",   # slug: lower-case letters, digits, . _ -
    version="1",                 # no spaces; raise it whenever output could change
    project_type="pipeline",     # the records' project_type it applies to
    extract=extract,
    summary="one line for --list")
```

- **Package and registry.** Each project type is a package
  `extractors/<type>/` whose `__init__.py` defines `EXTRACTORS`, a tuple in
  run order. Add the package's module name to `PACKAGES` in
  `extractors/registry.py`. Names must be unique across all packages.
- **Input.** `Inputs` holds `files` (`InputFile(path, data)`, sorted by path,
  with `.text` decoded as UTF-8 with replacement and `.suffix` the lower-case
  extension), `skipped` (`(path, reason)` for files not read) and `record`
  (the run record, read-only, or None for `--dir`). Paths are relative with
  `/`; the runner's `extracted/` prefix is removed. Files are read with
  limits: at most 500 files, 2 MB each and 8 MB in all; a file whose sha256
  no longer matches its record entry is skipped as `changed`. Symbolic links
  and paths leaving the folder are skipped.
- **Shared parsing.** `inputs.cached(key, build)` computes something once per
  output, so several extractors can share one parse (the website extractors
  share `extractors.website.site.get_site`).
- **Output.** A mapping of feature name (slug) to a JSON value: text,
  number, true/false, null, or lists and objects of these. `run_extractor`
  checks it, adds `status` if missing and sorts the names. Lists must be
  sorted (or be a meaningful order, such as the page's section order) so the
  output is byte-identical for the same input.
- **Status.** Every result has `status`:
  - `ok`: the extractor read its input. Empty lists, `0`, `false`, `"none"`
    or `"default"` mean **looked, and not present**.
  - `partial`: as `ok`, but a limit cut the input short (files skipped, or
    a parser limit hit); `skipped_files` counts skipped files.
  - `no-input`: nothing for this extractor to read (no HTML at all, say).
    It returns only `status`: **could not determine**. The extractor still
    appears in the record's `extractors` list, so "ran, nothing to read"
    differs from "never ran".
  - `error`: the extractor raised, or returned something that is not plain
    JSON with slug names. `error` holds the exception type and message,
    with local paths replaced by `<path>`. The other extractors still run.
  - Within an `ok` result, a single feature set to `null` means that one
    feature could not be determined (for example a background given through
    a `var()` that does not resolve).
- **Countable values.** Prefer categories from a fixed vocabulary and
  sorted sets of normalised names, as T1.5 builds frequency tables from
  them; keep raw values (hex codes, pixel sizes, package names) alongside
  where they help.
- **Versions.** Raise an extractor's version whenever the same input could
  give different features: new feature, changed vocabulary, changed table.
  A data file that drives an extractor contributes its own version (the
  stock phrase extractor is `1+rules.1`).
- **Tests.** Hand-made fixtures under `tests/fixtures/<type>/` (never in a
  folder named `data/`, which is ignored by git) with expected values worked
  out by reading the fixture, plus negative and hostile cases.

## How website outputs are read

Code: [extractors/website/](../extractors/website/). Every website extractor
reads one parsed `Site` (`site.py`), built once per output:

| Input | Read as |
|---|---|
| `.html` `.htm` `.xhtml` | HTML documents. The **entry page** is chosen as the renderer chooses it: `index.html` (shallowest), then a complete document, then the shallowest, largest, first by name. |
| `.vue` `.svelte` `.astro` | HTML documents (their template, `<style>` and `<script>`). |
| `.css`; `.scss` `.sass` `.less` | Stylesheets; preprocessor `$name:` / `@name:` variables are read as custom properties. |
| `<style>`, `style="..."` | Stylesheets, and declarations tied to their element. |
| `.js` `.mjs` `.cjs` `.ts`; `.jsx` `.tsx`; inline `<script>` | Scripts: imports, class names given in code, HTML held in strings (parsed as fragments), strings that read as prose. `.jsx`/`.tsx`, `type="text/babel"` scripts and scripts that look like JSX are also parsed as JSX markup. |
| `<script type="importmap">`, `package.json` | References to packages. |
| `<link href>`, `<script src>`, `@import` | References. |

**Parsers.** HTML is read by a small tokenizer written for this
(`html.py`), not Python's `html.parser`: on Python 3.13.1 that parser takes
minutes on `"<a " * 10000` (a start tag that never closes) and quadratic time
on repeated `</`. The tokenizer reads each character a bounded number of
times; an unclosed tag, quote or comment ends the parse there, as browsers
drop it. It builds a light tree (implied `</p>`, `</li>`, table cells; stray
end tags ignored; depth capped at 512, 100,000 elements per document). CSS is
read by **tinycss2 1.4.0** (pinned in `requirements.txt`; pure Python, BSD
licence, one dependency), which implements the CSS Syntax spec, so comments,
strings, escapes, `url()` and nesting are read as a browser reads them;
hand-written regexes get these wrong. Scripts are split into code, comments
and strings by a linear scanner (`js.py`); there is no JavaScript parser.
Every regular expression has bounded repeats or a single character class, so
none can backtrack catastrophically. Hostile inputs are in the tests.

**Tailwind and other utility classes.** Tailwind is the main case. It is
**referenced** when the page loads it (`cdn.tailwindcss.com`,
`@tailwindcss/browser`, an npm `tailwindcss` import or dependency), has
`@tailwind`/`@apply`/`@theme` or `@import "tailwindcss"` in CSS, a
`tailwind.config.*` file, or an inline `tailwind.config = {...}`. Without
any of these it is **classes-only** when five or more distinct
Tailwind-specific classes are used (`bg-indigo-600`, `rounded-2xl`,
`space-y-4`, `md:` variants...; classes Bootstrap shares, such as `px-4`,
`rounded`, `shadow-sm`, do not count). Utility classes are read as styling
only when Tailwind is referenced or classes-only, so Bootstrap's `rounded` is
not read as a 4px radius.

**The project's own theme** is read too (`tailwind_config.py`): the
`colors` and `fontFamily` objects of an inline `tailwind.config = {...}` or a
`tailwind.config.*` file (v3, wherever they sit: `theme` or `theme.extend`),
and `--color-*` / `--font-*` in a CSS `@theme` block (v4). Nested colour
keys join with `-` (`primary: {500: ...}` is `primary-500`; `DEFAULT` is the
bare name). Configs are read by a small bounded reader of object literals,
never run: keys, nested objects, arrays and strings; spreads, references and
function calls are skipped. A theme colour whose value is not a plain colour
(`hsl(var(--primary))`, common in shadcn-style setups) is a known name with
no colour and counts in `unparsed_colors`; before that, its `var()`s are
resolved through the page's custom properties, so shadcn-style
`hsl(var(--primary))` with `--primary: 221 83% 53%` reads as `#2463eb` (CSS
colour functions with `var()` inside are resolved the same way). The key
names of `fontSize` and `backgroundImage` are read too, so `text-display`
and `bg-hero-pattern` are not taken for unknown colours; a spread
(`...other`) in an object is skipped. `darkMode` is read from inline configs
and config files alike.

Coverage of utility classes (Tailwind v3 default palette plus the project's
theme colours and fonts):

| Utility | Read as | Feature family |
|---|---|---|
| `bg- text- border(-side)- from- via- to- ring- ring-offset- fill- stroke- outline- decoration- divide- accent- caret- shadow- placeholder-` with a palette colour, `white`, `black`, `[#hex]` or a theme colour name, any variant, any `/opacity` (except `/0`) | that colour, from Tailwind v3's palette or the theme; a colour name in neither (and not a size or keyword such as `text-xl`, `border-2`, `bg-cover`) is counted in `unknown_color_utilities` | palette, gradients, shadows |
| `rounded`, `rounded-{side}-{size}`, `rounded-[...]` | radius: none 0, xs/sm 2, (bare) 4, md 6, lg 8, xl 12, 2xl 16, 3xl 24, full | corners |
| `shadow`, `shadow-{xs,sm,md,lg,xl,2xl,inner,none}`, `shadow-{colour}` | xs to md subtle, lg to 2xl soft, inner inset; a colour makes it `colored` | shadows |
| `bg-gradient-to-*`, `bg-linear-to-*`, `bg-linear-{angle}`, `bg-radial`, `bg-conic`, `bg-clip-text` | gradient type, direction, gradient text | gradients |
| `font-sans`, `font-serif`, `font-mono`, `font-['Name']`, `font-{config key}` | font family | fonts |
| `flex`, `grid`, `grid-cols-N`, `columns-N`, `float-*`, `sticky`, `fixed`, `container`, `max-w-*` | layout system, columns, nav position, container width | layout |
| `backdrop-blur*` | backdrop blur | shadows |
| variants `sm md lg xl 2xl`, `max-*`, `dark`, `focus`, `focus-visible`, `motion-safe`, `motion-reduce` | breakpoints, dark mode, focus styles, reduced motion | responsiveness, dark mode, accessibility |

Not covered: spacing, sizing and typography scales (`p-4`, `text-xl`), other
frameworks' utilities (Bootstrap, UnoCSS presets beyond Tailwind's names) and
the styling a framework's own stylesheet applies (Bootstrap's blue primary,
its radii). For Bootstrap and similar, `css_framework` records the choice and
its defaults are implied.

## The colour vocabulary

Colours are kept as `#rrggbb` (lower case, alpha dropped; fully transparent
colours are left out) and named by a **class**:

- `black`, `white` or `gray-<lightness>` for near-neutral colours: CIELAB
  chroma below 16, or below 6 when L* is 85 or more. All of Tailwind's grey
  families stay neutral (`slate`, the bluest, reaches chroma 14.5); real
  navies stay blue (`#1e3a8a` has chroma about 50, `#14213d` about 23);
  creams such as `#fdf6e3` read as `yellow-light`; `black` is L* under 12,
  `white` over 97.
- otherwise `<hue>-<lightness>`: hue from the HSL angle, one of `red` (under
  12 or from 345), `orange` (12), `yellow` (40), `green` (70), `teal` (165),
  `blue` (195), `indigo` (232), `violet` (250), `purple` (270), `pink` (295);
  an orange or yellow with L* under 45 is `brown`.
- lightness: `dark` (L* under 40), `mid`, `light` (L* 75 or more).

The boundaries put Tailwind's families on their own names (indigo-500 is
indigo, purple-500 purple, violet-500 violet); rose falls in red, sky in
blue, cyan in teal, fuchsia in purple. Pure `#0000ff` (hue 240) reads as
indigo. The blue/indigo boundary is HSL 232: `#667eea`, the start of the
well-known purple gradient, is hue 229 and reads as `blue-mid`, while
`#6366f1` (indigo-500, 239) is `indigo-mid`; a gradient from `#667eea` to
`#764ba2` is `blue>violet`. `slate-900` (`#0f172a`) is `black`.

The neutral limit has a known boundary: the flat "navy" greys `#2c3e50` and
`#34495e` read as `gray-dark`, because on every measure tried they sit with
Tailwind's `slate-700` (`#334155`): chroma 13.3 and 15.1 against 13.8, HSL
saturation 0.29 against 0.25, hue 210 against 215. Separating them would make
slate blue again, so they stay grey; saturated navies (`#1e3a8a`,
`#14213d`) are blue.

A colour counts toward a page's **dominant hue** only when its chroma is 20
or more: pale tints (a cream background, `indigo-50`) name a hue in
`color_classes` and `hues` but do not outvote the accent colour.

Read: hex (3, 4, 6, 8 digits), the 148 CSS named colours (as words only in
colour properties, or as a custom property's whole value), `rgb() rgba()
hsl() hsla() hwb() oklab() oklch()` in legacy and modern syntax, and
`var()` followed to custom properties (alias chains of any length). A custom
property takes
its value from `:root`, `html`, `body` or `@theme` outside `@media`, else from
any other selector that does not mention dark; on a page that starts dark
(`forced_dark`), values on `.dark`, `html.dark` or `[data-theme="dark"]`
win, for CSS rules and for Tailwind theme values alike. Counted as
`unparsed_colors`: `lab() lch() color() color-mix() light-dark()` and
`var()` with no value or fallback.

Following `var()` is bounded so that a hostile stylesheet costs time in
proportion to its size:

- each custom property is expanded once (its own top-level `var()`s
  substituted) and its colours read once, then reused;
- a value whose size expands past 2,000 is unreadable. Size is the number of
  component values plus the characters of their text. Values inside
  functions and blocks count, so a huge gradient behind a variable is not
  one value; every character counts, so neither is one huge string or word
  (a six-layer mesh gradient is about 510, a five-layer shadow about 250);
- as text inside a colour function (`hsl(var(--primary))`) the limit is 300
  characters; at most 50 colours are taken from one property;
- every use is charged to a budget of 1,000,000 per page and extractor: the
  size of each value spliced in and each character substituted. A page that
  spends it gets its remaining `var()`s left unresolved (they count as
  unreadable, as above). The hand-made fixtures spend about 600 at most.

What a property resolves to depends on the stylesheet only, not on which rule
uses it first: a property that reaches a cycle of `var()`s is unreadable, and
so is every property that reaches it. Plain colour words in a variable
are read by the property that uses it (all of them in a colour property;
in another custom property only when the word is the whole value), also
whichever comes first. Only a page that spends the budget is
cut off at a point that depends on its rule order (the same page still gives
the same features every time).

## The website extractors

Versions: palette, fonts, layout, corners-shadows, gradients and dark-mode
`6`; stock phrases `2+rules.2`; the others `1`. "No input" lists when the
extractor returns `status: no-input`.

### website.palette

No input: no HTML and no CSS.

| Feature | Value |
|---|---|
| `colors` | sorted distinct `#rrggbb` from CSS declarations (with `var()` followed), `fill`/`stroke`/`stop-color`/`color`/`bgcolor` attributes, `<meta name="theme-color">` and Tailwind colour utilities |
| `color_count` | number of `colors` |
| `color_classes` | sorted distinct classes of those colours (vocabulary above) |
| `hues` | sorted distinct chromatic hues (no neutrals) |
| `dominant_hue` | the hue used most among colours of chroma 20 or more (each declaration or class use counts once; ties go alphabetically); `none` if there is none |
| `tailwind_colors` | sorted distinct Tailwind colour names used: palette (`indigo-600`, `white`) and theme (`primary-500`, `brand`) |
| `unknown_color_utilities` | number of distinct colour names in colour utilities that are neither in the palette nor in the theme read (`bg-brand-500` with no readable config) |
| `unknown_color_names` | those names, sorted (at most 50) |
| `background` | class of the page background; `default` when nothing sets one (the browser's white); `null` when set through a value that cannot be read |
| `background_hex` | its `#rrggbb`, or null |
| `base_scheme` | `light` or `dark` (background L* under 50); `light` for `default`; null when unknown |
| `unparsed_colors` | count of colour values not read, theme colour uses whose value is not a plain colour included |

The page background is the first found of: a plain `bg-*` class on `<body>`
or `<html>` (a theme colour that cannot be read does not end the search); the last `background`/`background-color` outside `@media` on
`html`, `body` or `:root` (or their `style`); a `bg-*` class on the first
full-height wrapper (`min-h-screen`, `h-screen`...) of the page or its
components. Its first visible colour counts, so a gradient background gives
its first stop. When the page starts dark (`forced_dark` in the dark-mode
extractor), a `dark:bg-*` class wins over the plain one, and rules and
custom properties on `.dark`, `html.dark` or `[data-theme="dark"]` win
over the plain page rules.

Blind spots: colours set by scripts at run time, in images or SVG files, and
in stylesheets loaded from a CDN (a framework's own palette) are not seen.
Specificity is ignored: the last matching page rule wins. Colours in
`@media (prefers-color-scheme: dark)` count in `colors` but never as the
background. Tailwind v4 colours are read with v3 values.

### website.fonts

No input: no HTML and no CSS.

| Feature | Value |
|---|---|
| `families` | sorted named families declared (`font-family`, `font`, Tailwind font classes, the Tailwind theme) or loaded (font services, `@font-face`, `@fontsource`), lower case, quotes removed; icon fonts left out |
| `family_count` | number of `families` |
| `generic_families` | sorted generic names declared: `serif`, `sans-serif`, `monospace`, `system-ui`, `ui-sans-serif`... |
| `loaded_families` | families loaded from a font service URL, `@font-face` or `@fontsource` |
| `font_categories` | sorted categories of all named and generic families: `sans`, `serif`, `mono`, `display`, `script`, `system`, `unknown` (from a table of about 250 common fonts in `fonts.py`) |
| `font_sources` | sorted: `google-fonts`, `bunny-fonts`, `adobe-fonts`, `fontshare`, `rsms-inter`, `fontsource`, `self-hosted` |
| `primary_font` | first family of the page's font: the last `font-family`/`font` outside `@media` on `html`, `body`, `:root` or `*` (`var()` followed); else a Tailwind font class on `<html>`/`<body>`; else the theme's `sans` (config or `@theme --font-sans`); else `default` |
| `primary_category` | its category, or `default` |
| `heading_font` | first family declared for a selector naming `h1`, `h2` or `h3`, else a Tailwind font class on the first `<h1>`; `same` if none (it inherits) |
| `heading_category` | its category, or `same` |
| `system_stack` | true if any stack names `system-ui`, `-apple-system`, `BlinkMacSystemFont`, `ui-sans-serif` or `Segoe UI` |

Blind spots: the font a framework's stylesheet sets (Bootstrap's system
stack, Tailwind's preflight stack when no config names one: `default`);
fonts given through a `var()` that does not resolve (the name is skipped); a theme family behind a spread or reference in a config (the reader skips them); a `tailwind.config.js`
file's theme. A font loaded but never used still appears in `families`.

### website.libraries

No input: no files.

| Feature | Value |
|---|---|
| `libraries` | sorted library slugs (`react`, `tailwindcss`, `lucide`, `aos`...) from `<script src>`, stylesheet `<link>`, `@import`, module imports, import maps and `package.json`; one slug per library (`react-dom` is `react`, `lucide-react` is `lucide`) |
| `library_count` | number of `libraries` |
| `delivery` | sorted ways the recognised libraries arrive: `cdn`, `package`, `local` (a vendored file such as `js/jquery.min.js`) |
| `cdn_hosts` | sorted hosts of every absolute URL referenced as a script, stylesheet, preload or import (font services included) |
| `framework` | first of `next nuxt sveltekit astro react vue svelte angular solid preact lit alpinejs htmx jquery` found, else `none` |
| `css_framework` | first of `tailwindcss bootstrap bulma foundation materialize pico uikit semantic-ui mui chakra-ui antd water.css shoelace`, `tailwindcss` for classes-only Tailwind, else `none` |
| `tailwind_usage` | `referenced`, `classes-only` or `none` |
| `tailwind_evidence` | sorted: `reference`, `package`, `css-directive`, `config-file`, `inline-config` |
| `unrecognised` | sorted package names and CDN hosts that are not in the catalogue, so it can grow |

Resolution (`catalog.py`): CDN URLs that name an npm package (jsDelivr
`/npm/`, unpkg, esm.sh, Skypack, JSPM, cdnjs and Google's `/ajax/libs/`),
hosts that serve one library (`cdn.tailwindcss.com`, `code.jquery.com`,
`kit.fontawesome.com`, BootstrapCDN...), bare imports, and local file names
with `.min` and versions removed. The output's own modules (`./App`, `@/...`)
are not libraries.

Blind spots: libraries pasted inline (minified code without a reference),
globals used without a reference, and packages not in the catalogue (listed
in `unrecognised`).

### website.layout

No input: no HTML (or JSX/Vue/Svelte markup).

| Feature | Value |
|---|---|
| `sections` | the page's top-level blocks in order, each one of `header nav hero features pricing testimonials faq cta contact about menu gallery team stats schedule newsletter blog skills logos steps order dashboard app footer sidebar form other` (at most 30) |
| `section_kinds` | sorted distinct `sections` |
| `section_count` | number of `sections` |
| `hero` | true if `hero` is among them |
| `landmarks` | sorted landmark elements used: `header nav main footer aside section article` |
| `layout_systems` | sorted: `grid`, `flex`, `float`, `columns` (CSS `display`, `float`, `columns` and Tailwind classes) |
| `grid_columns` | sorted column counts: from `grid-template-columns` (`repeat(3, ...)` or a track list) and `grid-cols-N`; `auto-fit`/`auto-fill` for `repeat(auto-fit, ...)` |
| `card_groups` | number of card groups: three or more sibling elements holding a heading or paragraph that share tag and classes, allowing one sibling of the same tag with other classes (a highlighted card, such as the middle pricing tier); plus JSX cards written once inside `.map(...)` (sections, list items, paragraphs, headings, links and table rows are never cards) |
| `card_group_sizes` | sorted sizes of the static groups (a group from `.map(...)` has no known size and is not listed) |
| `mapped_card_groups` | number of JSX card groups written inside `.map(...)` |
| `nav_position` | `sticky` or `fixed` (CSS `position` on a header/nav selector, or Tailwind `sticky`/`fixed` on `<header>`/`<nav>`), `static` if there is a header or nav, `none` if not |
| `max_widths_px` | sorted `max-width` values of 480px or more outside `@media` (rem as 16px) and Tailwind `max-w-*` sizes |
| `container_class` | true if Tailwind's `container` class is used |

Blocks are the children of `<body>`, with a single wrapper (`div`, `main`,
`#root`...) unwrapped and `<main>`'s children brought up; inline elements
(`a`, `span`, `img`, `button`...) and scripts are not blocks. When the entry
page has fewer than two blocks (an empty `#root`), the component file with the
most blocks is used; in JSX, the element rendering two or more components is
the page. A block's kind comes from, in order:

1. a name saying hero: a component name (`<HeroSection>`), `id`, class or
   `aria-label` (so `<header class="hero">` is `hero`); utility classes
   (with `:`, `[`, `(`, `/`, `.` or quotes, such as `bg-[url(...)]`) are not
   names;
2. its tag: `header`, `nav`, `footer`, `aside`, `form`;
3. another kind its name gives (`<PricingTable>`, `id="faq"`);
4. `hero` for the first content block (after any header or nav) that holds
   an `<h1>`, whatever the h1 says;
5. the words of its first `<h2>` or `<h3>` (never the h1).

Names and headings are split into words (`HeroSection`, `hero_section`,
"Ready to get started?"). A single section word wins ("Simple pricing to get
started" is `pricing`, "Get started in three steps" is `steps`); then
multi-word names (`get-started`, `how-it-works`, `call-to-action`) match
whatever separates their words. In heading text the call-to-action phrases
count only when the heading is the call itself: it starts with "ready",
"get started", "start", "let's" or "join", or it is a question. So "Ready to
get started?" is `cta`, and "Everything you need to get started" names
nothing (`other`).

A single wrapper is unwrapped only when its own name (component name, id,
classes, `aria-label`) gives no kind; its headings are not consulted, so a
React root `<div>` or a `<div class="min-h-screen">` holding the whole page
no longer collapses it into one section. `<section>` and `<article>` are
never unwrapped, and neither is a wrapper with an `<h2>` or `<h3>` among
its own children (it is a section with a heading, not a wrapper).

Blind spots: section kinds from keywords miss blocks named in other
languages or by content alone (they become `other`); order across separate
component files is the order of the file with the most blocks; elements
positioned by CSS (absolute, grid areas, `order`) are read in source order;
Bootstrap's `fixed-top`/`sticky-top` classes are not read.

### website.corners-shadows

No input: no HTML and no CSS.

| Feature | Value |
|---|---|
| `radii` | sorted distinct radii from `border-radius` and `border-*-radius` (following `var()`) and Tailwind `rounded` classes: `8px` (rem and em as 16px, to the half pixel), a percentage under 50%, or `full` (50% or more, or 999px or more) |
| `common_radius` | the radius used most, not counting 0 and `full` (ties to the smaller); `full` if only pills; `none` if no radius |
| `corner_style` | from `common_radius`: `square` (none or 0), `subtle` (up to 4px), `rounded` (up to 12px), `very-rounded`, `pill` |
| `pill_shapes` | true if any radius is `full` |
| `shadow_count` | number of `box-shadow` declarations that draw a shadow (`var()` followed, so `box-shadow: var(--shadow-lg)` counts at its use; the custom property's own definition does not), plus Tailwind shadow classes |
| `shadow_kinds` | sorted kinds of each shadow layer: `inset`; `hard` (no blur, offset); `glow` (no offset, blurred); `subtle` (blur under 10px); `soft`; plus `colored` when its colour is not neutral |
| `text_shadow` | true if any `text-shadow` other than none |
| `backdrop_blur` | true if `backdrop-filter: blur(...)` or Tailwind `backdrop-blur*` (glass panels) |

Blind spots: corners and shadows from a framework's stylesheet (Bootstrap's
`.card`, `.btn`), `filter: drop-shadow`, shadows drawn with pseudo-elements
or images.

### website.gradients

No input: no HTML and no CSS.

| Feature | Value |
|---|---|
| `gradient_count` | number of CSS gradient functions (`linear- radial- conic-` and `repeating-`) where they are used, plus elements with a Tailwind gradient class. A gradient kept in a custom property counts at each `var()` that uses it, not where it is defined |
| `gradient_types` | sorted: `linear`, `radial`, `conic` |
| `gradient_directions` | sorted directions of linear gradients: `135deg` (angles in degrees, any unit converted), `to-right`, `to-bottom-right`...; `to-bottom` when none is given (the default) |
| `gradient_hues` | sorted hues (and neutral names) of every colour stop |
| `gradient_pairs` | sorted `first>last` hue of each gradient's first and last visible stop, such as `indigo>purple`; only for gradients with two or more visible stops (a colour fading to `transparent` gives no pair). Tailwind stops with a variant (`dark:from-slate-900`, `hover:to-x`) are left out |
| `gradient_text` | true if gradient-filled text: `background-clip: text` in a rule with a gradient, or Tailwind `bg-clip-text` with a gradient |
| `gradient_targets` | sorted: `page` (html/body/:root), `hero`, `button`, `text`, `other` |

Blind spots: gradients in SVG (`<linearGradient>`), canvas or images; a
gradient and `background-clip: text` in different rules for the same element.

### website.icons-emoji

No input: no HTML.

| Feature | Value |
|---|---|
| `icon_libraries` | sorted icon sets: from library references, and from markup: Font Awesome (`fa-solid fa-x`), Bootstrap Icons (`bi bi-x`), Boxicons, Tabler, Phosphor, Remix Icon (`ri-x-line`), Material Icons/Symbols (class or Google Fonts family), Lucide (`data-lucide`, `lucide` class on an icon), Feather (`data-feather`), Ionicons (`<ion-icon>`), Iconify |
| `inline_svg_count` | number of `<svg>` elements in markup |
| `svg_image_count` | number of `<img>` whose source is an `.svg` file |
| `emoji` | sorted distinct emoji in the page's visible text (whole sequences: skin tones, ZWJ sequences, flags and keycaps count as one) |
| `emoji_count` | emoji occurrences |
| `emoji_led_headings` | headings whose text starts with an emoji |
| `text_symbols` | sorted distinct icon-like text characters: `✓ ✔ ✗ ✘ ★ ☆ ♥ ❤ → ← ↑ ↓ ↗ ➜ ➔ ➝ ⟶ ✦ ✧ ◆ ◇ ● • ✱ ✳` (`©`, `®`, `™` are neither) |
| `icon_kinds` | sorted: `library`, `inline-svg`, `emoji`, `svg-image`, `symbol` |
| `favicon` | the entry page's icon link: `emoji` (an inline SVG drawing an emoji), `data-uri`, `file`, `external`, `none` |

Emoji are code points with emoji presentation by default (Unicode's
Emoji_Presentation, approximated by ranges in `emoji.py`) or followed by
U+FE0F. Blind spots: emoji that only scripts insert at run time from data
that does not read as prose; icons from a component library rendered as
components (`<Settings />` from `lucide-react` is seen through the import,
not counted as SVG).

### website.stock-phrases

No input: no HTML.

| Feature | Value |
|---|---|
| `stock_phrases` | sorted ids of rules that matched |
| `stock_phrase_counts` | `{rule id: hits}`, sorted by id |
| `stock_phrase_hits` | total hits |
| `stock_phrase_matches` | `{matched phrase: count}`, sorted, for the phrase-list rules, so single words grouped in one rule (`robust`, `enhance`) can be counted or dropped one by one. Pattern rules (regular expressions) give no per-match breakdown, only their count in `stock_phrase_counts` |
| `stock_phrase_categories` | sorted categories matched: `cta`, `placeholder`, `marketing`, `ai-vocabulary`, `significance`, `chat-residue`, `construction` |
| `copy_word_count` | words in the page's visible text |
| `em_dash_count` | em dashes (—) in the visible text |
| `exclamation_count` | exclamation marks in the visible text |
| `headings_checked` | `h1`-`h3` headings of three or more words |
| `title_case_headings` | those in Title Case (every word of four or more letters capitalised, not all capitals) |

The rules are in
[extractors/website/stock_phrases.json](../extractors/website/stock_phrases.json),
versioned (`version`, part of the extractor version), with a source URL and
licence note per source, and one source per rule. They paraphrase public
lists of "AI slop" tells (Wikipedia's *Signs of AI writing*, the pixelslop
pattern catalogue, a UX ban list, a design-studio article); the lists were not
copied whole. A rule is a list of lower-case phrases matched on whole words,
or a regular expression restricted to bounded repeats (no `*` or `+`, `{m,n}`
up to 100 and never on a group, no backreferences), checked when the file is
loaded. Text is matched after lower-casing, straightening quotes and
collapsing spaces, one **block element's** text per line: text split by
inline elements (`Ready to <span>get started</span>`) is joined, so the
phrase matches, but a phrase never runs across two blocks. A rule's
`scope` is `copy` (the default: the visible text, plus `placeholder`,
`title` and `aria-label`) or `alt` (image `alt` text only; the stock-photo
descriptions rule uses it, so a stat labelled "Happy Customers" is not a
hit). The visible text is the page's text outside `script`, `style`,
`template`, `noscript` and `head` (plus the title), JSX text, and script
strings that read as prose; `alt`, `placeholder`, `title` and `aria-label`
are matched as well.

A hit means the page uses the phrase, not that a model wrote it: "get
started" is a fine button. The pixelslop catalogue flags generic CTA labels
only when one label repeats three or more times across sections; the `cta-*`
rules here count every occurrence, so that condition is applied downstream
(from `stock_phrase_counts`) and is not part of the rule. Blind spots: text that scripts build from pieces;
copy in images; languages other than English; single-word rules such as
`robust` or `vibrant` that are ordinary words in some pages.

### website.file-structure

No input: no files and none skipped.

| Feature | Value |
|---|---|
| `file_count` | files, skipped ones included |
| `file_kinds` | `{extension: count}`, sorted; `none` for no extension |
| `structure` | `single-html` (HTML only), `html-css`, `html-js`, `html-css-js`, `component-project` (JSX, TSX, Vue, Svelte, Astro or `package.json`), `no-html` |
| `folders` | sorted top-level folder names (lower case) |
| `max_depth` | deepest folder level (0 for files at the top) |
| `entry_file` | the entry page's path, or null |
| `html_files` | number of HTML files |
| `inline_style_blocks`, `inline_script_blocks` | `<style>` and non-empty `<script>` elements in HTML files |
| `external_scripts`, `external_stylesheets` | `<script src>` and `<link rel="stylesheet">` in HTML files |
| `style_attributes` | elements with a `style` attribute in HTML files |
| `has_package_json`, `has_readme`, `has_build_config` | true/false (`vite`, `webpack`, `next`, `tailwind`, `postcss`, `tsconfig`... config files) |
| `total_bytes` | bytes of the files read |

### website.responsiveness

No input: no HTML and no CSS.

| Feature | Value |
|---|---|
| `viewport_meta` | `device-width`, `other`, `absent`; null if there is no entry HTML page |
| `width_media_queries` | `@media` rules with a width condition |
| `breakpoints_px` | sorted distinct widths in those conditions (`min-width`, `max-width` and range syntax; em and rem as 16px) |
| `media_query_style` | `mobile-first` (more min-width), `desktop-first` (more max-width), `mixed`, `none`; `mobile-first` when only Tailwind breakpoint variants are used |
| `tailwind_breakpoints` | breakpoint variants used, in size order: `sm md lg xl 2xl`, then `max-*` |
| `fluid_techniques` | sorted: `clamp`, `min-max`, `viewport-units` (`vw vh dvh svh`...), `auto-fit-grid`, `container-queries`, `flex-wrap` |
| `responsive_images` | true if `srcset` or `<picture>` is used |

Blind spots: responsiveness that comes from a framework's grid (Bootstrap's
`col-md-4`) or from JavaScript; whether the page actually fits a phone (the
renderer's phone screenshots show that).

### website.dark-mode

No input: no HTML and no CSS.

| Feature | Value |
|---|---|
| `dark_mode` | `system` (follows the system setting), `toggle` (switched by a class or attribute), `both`, `dark-only` (the page starts dark and nothing switches it: a forced dark theme with no toggle control or script, or no dark mechanism and a dark page background), `none` |
| `forced_dark` | true if the entry page starts in its dark theme: `class="dark"` or `data-theme`/`data-mode`/`data-bs-theme`/`data-color-scheme="dark"` on `<html>` or `<body>`. The palette then reads the `dark:bg-*` class and `.dark`/`[data-theme="dark"]` rules and variables for the background |
| `mechanisms` | sorted evidence: `prefers-color-scheme-css`, `prefers-color-scheme-js` (`matchMedia`), `color-scheme-property` (CSS or `<meta name="color-scheme">`), `light-dark-function`, `dark-class-selector` (`.dark`, `.dark-mode`...), `data-theme-attribute` (`[data-theme="dark"]`, `data-bs-theme`...), `toggle-script` (a script adds a dark class or sets `data-theme` to dark), `tailwind-dark-variant`, `tailwind-class-strategy` (`darkMode: 'class'` or `'selector'`, or `@custom-variant dark`) |
| `theme_toggle` | true if a control is named for it (id, class, `aria-label` or `title` mentioning theme, dark or night) or a toggle script exists |

Tailwind's `dark:` variant counts as `system` unless a class strategy or toggle
script is found (its default follows the system). Blind spots: dark modes
done entirely in JavaScript styles; a dark theme forced by a script at
load time (counted as a toggle script, not as `forced_dark`).

### website.accessibility

No input: no HTML.

| Feature | Value |
|---|---|
| `html_lang` | `present` or `absent` on the entry page's `<html>`; null without an entry page |
| `lang` | its primary language subtag, lower case (`en`), or null |
| `images` | `<img>` elements |
| `images_missing_alt`, `images_empty_alt` | without `alt`; with `alt=""` (decorative, which is valid) |
| `alt_coverage` | `all` (none missing), `some`, `none`, `no-images` |
| `h1_count` | `<h1>` elements |
| `heading_levels` | sorted distinct heading levels used |
| `heading_skips` | jumps down of more than one level (`h1` then `h3`), in document order |
| `main_landmark` | true if `<main>` or `role="main"` |
| `skip_link` | true if a same-page link whose text mentions skip |
| `form_controls` | `input` (not hidden, submit, button, image, reset), `select`, `textarea` |
| `unlabelled_controls` | of those, without `<label for>`, a wrapping `<label>`, `aria-label`, `aria-labelledby` or `title` (a placeholder is not a label) |
| `buttons_without_name` | `<button>`s with no text, no `aria-label`/`aria-labelledby`/`title`, and no image with alt inside (HTML only; not counted in JSX, where text may come from expressions) |
| `generic_link_text` | links whose whole text is `click here`, `here`, `read more`, `learn more`, `more`, `link` or `this` (HTML only) |
| `aria_attributes`, `role_attributes` | counts of `aria-*` and `role` attributes |
| `positive_tabindex` | elements with `tabindex` above 0 |
| `focus_styles` | true if a `:focus`, `:focus-visible` or `:focus-within` rule, or Tailwind `focus:` variants |
| `outline_removed` | true if `outline: none` or `0` anywhere, or Tailwind `outline-none` |
| `reduced_motion` | true if a `prefers-reduced-motion` query or Tailwind `motion-safe:`/`motion-reduce:` |

Blind spots: colour contrast (needs rendering), focus order, whether `alt`
text is meaningful, labels added by scripts, components that render
accessible markup (counted only as the component).

## Pipeline, math and engineering outputs (T2.8)

Code: [extractors/common/](../extractors/common/),
[extractors/pipeline/](../extractors/pipeline/),
[extractors/math/](../extractors/math/),
[extractors/engineering/](../extractors/engineering/). Versions are `1`,
except `2` for `pipeline.operations`, `pipeline.images`, `pipeline.ci`,
`math.precision`, `math.units`, `math.constants`, `engineering.units`,
`engineering.safety` and `engineering.quantities` (review round 1). Which choice goes to an extractor and which to the model-read rubric is
set in [rubrics.md](rubrics.md), "The split with the extractors".

### What is read

| Part | From | Used by |
|---|---|---|
| **Reply** | the record's `raw_response` | every type |
| **Prose** | the reply outside fenced blocks; an unclosed block runs to the end and is not prose | `*.reply` |
| **Working** | the prose and the untagged, `text`, `math`, `latex` and `tex` blocks that do not look like a program | math prose features |
| **Files** | the record's extracted files, one per fenced block ([record-format.md](record-format.md)); the language comes from the file name, or for an untagged block from a few unmistakable marks (Python, Go, OpenSCAD, DXF, STL, STEP, SVG). Anything else has no language and is not code | pipeline, code and CAD features |
| **Prompt** | the record's `prompt_text`: its numbers are givens, not choices | `math.precision` |

With `--dir`, the reply is `response.md` and its fenced blocks are the files
when the folder holds nothing else. At most 1,000,000 characters of the
reply and 1,000,000 of the files are read (`partial` beyond that). Source is
split into code, comments and strings by a linear scanner; nothing is parsed
by a language's own parser and nothing is run. YAML is loaded with
`safe_load` under limits (100,000 characters, 20 aliases, 2,000 brackets).
Every repeat in the patterns is bounded or runs over a single character
class; [tests/test_extractors_hostile.py](../tests/test_extractors_hostile.py)
holds the hostile cases.

**Status.** `no-input` means there is nothing for that extractor to read: no
reply text; for the pipeline behaviour extractors, no program (so a
configuration-only reply leaves them undetermined). A feature that is `null`
could not be determined. Values such as `"none"`, `"not-stated"` and `[]`
mean the extractor looked. `"not-relevant"`, `"no-spring"`,
`"no-image-code"` and `"no-workflow"` mean the thing the feature describes is
not there; the metrics treat them as not applicable.

**All of these are keyword and pattern readings.** They see what is written,
not what it does. A call that is named and never reached counts; a way of
doing the same thing that is not in a table is missed. Features where a
miss or a false hit is likely are `provisional` in
`analysis/<type>/features.yaml` until outputs have been reviewed (T2.11).

### *.reply (all three types)

`pipeline.reply`, `math.reply`, `engineering.reply`.

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `words` | number | runs of letters in the prose | formulas in prose count as words (`frac`, units) |
| `headings` | number | `#` headings | bold lines used as headings and underlined headings are not counted |
| `list_items` | number | lines starting with a bullet or a number | numbered working steps count |
| `code_blocks` | number | fenced blocks, closed or not | indented code is not a block |
| `tables` | number | Markdown tables (a separator row under a header) | tables drawn in text blocks or HTML are not counted |
| `largest_table_rows` | number | data rows of the longest table: "points reported" and "how much of the schedule" | the values are not read |

### pipeline.language, pipeline.layout

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `primary_language` | categorical | the programming language with most code (comments aside); shell or SQL only where there is no other; `none` for configuration only | usage commands never outweigh a program, by design |
| `languages` | set | every programming and scripting language found | untagged blocks that are not recognised are left out |
| `structure` | categorical | `no-code`, `config-only`, `single-file`, `multiple-files`, `package`; test files and `setup.py` do not count, nor do unnamed blocks under 8 lines of code beside a longer one. `null` where several substantial blocks are unnamed: they may be files or alternatives | code outside fences is not seen, so such a reply reads as `no-code` |
| `source_files` | number | the files behind `structure` | |
| `file_names` | set | names the reply gave, lower case | generic `block-NN` names are left out |
| `has_readme` | boolean | a file named `readme*` | instructions in the reply itself are the rubric's `usage_docs` |
| `dependency_files` | set | `requirements*.txt`, `pyproject.toml`, `package.json`, `go.mod` and the like, when named | an unnamed dependency list is missed |
| `entry_point_guard` | boolean | `if __name__ == "__main__"` in Python; `null` without Python | |

### pipeline.testing, pipeline.comments

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `tests_present` | boolean | test functions or cases in any file; in a Python file not named as a test, an assertion is needed too | checks written as plain `if` statements are not tests |
| `test_files` | number | files holding tests | |
| `test_frameworks` | set | `pytest` (also bare `test_` functions), `unittest`, `go-testing`, `jest`, `vitest`, `mocha`, `node-test`, `rust-test`, `rspec`, `testthat` | JavaScript tests with global `describe` name no framework |
| `comment_lines` | number | lines of comments, shebang aside | |
| `comment_density` | categorical | comment lines over all non-blank lines: `none`, `low` (under 5%), `medium` (under 15%), `high` | |
| `docstrings` | number | Python docstrings; `null` without Python | doc comments of other languages count as comments |
| `has_docstrings` | boolean | as above | |

A **test file**, left out of the behaviour features below, is one that holds
tests and nothing else: named or placed as a test, or an unnamed block whose
definitions are all tests. A script with tests inside it is still the
pipeline.

### pipeline.libraries

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `imports` | set | top-level modules or packages imported (Python, JavaScript/TypeScript, Go, Rust, Ruby, R) | dynamic imports; `null` for other languages |
| `third_party` | set | imports found in a table of known libraries, by distribution name (`pillow`, `pyyaml`); every dotted Go import path | a library not in the table goes to `other_imports` |
| `other_imports` | set | neither the language's own, nor known, nor a file of the output | an unnamed helper block cannot be matched to its import |
| `stdlib_only` | boolean | false with any known library; `null` with unknown imports or a program in an unread language; else true. Python's own modules are those of Python 3.13 | libraries used without an import (a command run by the code) |
| `database_libraries` | set | database drivers and mappers among the imports | storage through a command line client |
| `scheduling_libraries` | set | scheduling libraries among the imports | cron lines and CI schedules are the rubric's and `pipeline.ci`'s |

### pipeline.logging, pipeline.config

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `logging_style` | categorical | `logging-library`, `print`, `both`, `neither`; `null` for a language whose printing is not read | a print used for a report and one used as a log look alike |
| `logging_libraries` | set | `logging`, `loguru`, `structlog`, `winston`, `pino`, `slog`, `go-log`, `zap` and others, by import | |
| `uses_print` | boolean | `print`, `console.*`, `fmt.Print*`, `echo` | |
| `config_sources` | set | `arguments` (argument parsers, `argv`), `environment` (environment variables, dotenv), `config-file` (a config parser, YAML loading, or a file named `config`, `settings`, `rules` or `schema`) | a JSON file with another name read as configuration |
| `key_source` | categorical | where a name like API key, token, secret or password gets its value, on its own line: `environment`, `argument`, `file`, `written-in` (a literal, placeholders included), `several`; `none` with no such name; `null` where it is named and the source is not on that line | a value passed through another variable; keys under other names (`KEY`, `token`) |

### pipeline.operations

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `retry_present` | boolean | a retry library, or `retry`, `backoff`, `max_attempts` or a loop over attempts in the code, strings and comments aside. `urllib3` counts only where its `Retry` object is made | a retry under other words; whether it waits is the rubric's `retry_policy` |
| `retry_libraries` | set | `tenacity`, `backoff`, `urllib3`, `p-retry` and others, by import | |
| `file_reading` | categorical | `whole-file`, `streaming`, `both`, `none`, or `null` where a file is opened and no known read follows. Streaming: a loop over a file, `open(...)`, `fileinput` or `sys.stdin`, chunks, or a streaming call. A loop over content already read whole (`read().splitlines()`) is not streaming. Loading a configuration file (by its name, its handle or the variable it fills: `config`, `settings`, `cfg`, `conf`, `rules`, `schema`) counts for neither, and `Image.open` is not a text file | this is the second reading of "one line at a time"; the first is the sandbox's. A data file named like a configuration file is not counted; a loop over a parameter is seen only when its variable is named `line` |
| `read_calls` | set | the calls behind it: `read`, `readlines`, `read-text`, `table-read`, `json-load`, `list-of-rows`, `read-file`, `line-loop`, `readline`, `chunked`, `stream-api` | a loop over a parameter is seen only when its variable is named `line` |
| `output_formats` | set | writing calls: `csv`, `json`, `jsonl`, `parquet`, `database`, `excel`, `html`, `plot`, `image`, `printed`. In Python with an image library, `image` is a `save` of an object made from an image call (or with a usual name such as `img`) | files written as plain text with a suffix chosen at run time; `json.dumps` for a log line counts as `json`; an image passed in under an unusual name and no type annotation |
| `parallel_work` | set | `process-pool`, `thread-pool`, `asyncio` (`gather`, `TaskGroup`, `create_task`, `as_completed`, `wait`; `asyncio.run` alone is not parallel work), `promise-all`, `worker-threads`, `goroutines`, `rayon`, `shell-parallel` | parallelism inside a library |

### pipeline.images

`null` of image code is `no-image-code`: no image library imported and no
ImageMagick command.

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `image_libraries` | set | `pillow`, `opencv`, `sharp`, `imagemagick`, `go-imaging` and others | |
| `orientation_handling` | categorical | `present` or `absent`; `provisional` | a library that turns images by default shows no keyword (OpenCV's reader, for one) |
| `orientation_calls` | set | `exif-transpose`, `auto-orient`, `orientation-tag`, `sharp-rotate` | |
| `metadata_handling` | categorical | `strips`, `keeps`, `both`, `unmentioned`; `provisional`. `exif` counts only as a keyword argument of a call, or a `["exif"]` entry being set: `exif = img.getexif()` reads and decides nothing | Pillow and sharp drop metadata on saving with no word in the code: `unmentioned` is not "kept". The files the output writes show what happened (T2.7) |
| `metadata_calls` | set | `empty-exif`, `strip-option`, `remove-function`, `pixel-copy`, `delete-exif`, `keeps-exif`, `with-metadata` | removing one tag (the orientation) reads as nothing |

### pipeline.ci

Files are recognised by path (`.github/workflows/`, `.gitlab-ci.yml`, ...)
or, for unnamed YAML, by their keys. A file that does not load safely leaves
what would be read from it `null`.

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `ci_service` | categorical | `github-actions`, `gitlab-ci`, `circleci`, `azure-pipelines`, `travis`, `bitbucket`, `jenkins`, `several`, `none` | other services read as `none`; Jenkins files are not read further |
| `triggers` | set | `push`, `pull-request`, `tag`, `schedule`, `manual`, `release`, `merge-queue`, `called`, `other` | outside GitHub Actions, only what is written in the file; `null` where nothing is (circleci always) |
| `matrix_keys` | set | the keys of every matrix | |
| `matrix_os` | set | `linux`, `windows`, `macos` from matrix values, `runs-on` and images | |
| `matrix_versions` | set | `key=value` for other matrix values | values given by expressions |
| `ci_tools` | set | tools named in commands and actions (`pytest`, `ruff`, `go-vet`, `coverage`, ...) | scripts that call tools; the kind of check is the rubric's `ci_checks` |
| `timeout`, `cancel_superseded` | categorical | `set`, `not-set`, `no-workflow` | |

### math.notation, math.voice, math.currency

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `main_notation` | categorical | `latex`, `unicode`, `plain`, `mixed`, `none`: the form of 70% of the formulas. A LaTeX formula is a `$...$` (opening mark with no blank after it, closing one with no blank before and no digit after), `$$`, `\[`, `\(` or an equation environment; other lines with `=` are Unicode if they hold a mathematical character, else plain | counts formulas, not their length |
| `notation` | set | every form present | one `×` in a sentence with `=` makes it Unicode |
| `has_formula` | boolean | a relation in any of them | |
| `address` | categorical | `you`, `we`, `both`, `neither`; a pronoun counts from 2 uses | an offer of help at the end adds uses of "you" |
| `you_count`, `we_count` | number | | |
| `currency` | set | symbols, ISO codes and words; `["none"]` for a money answer without one; `[]` (not applicable) otherwise. A dollar inside a formula is not money | "pounds" alone is not read (it is a weight too) |

### math.precision

Results are the last number of each bold or boxed span (labels such as
"Step 2" aside); without any, the numbers after "≈". Numbers equal to a
number of the prompt are not results. A whole number ending in zero has no
countable figures.

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `result_sig_figs` | categorical | the most common among the results: `1` to `4`, `5+`, `mixed`; `null` with no result found | results only in a table or in running text are missed; emphasised intermediate values count |
| `result_decimals` | categorical | the same for decimal places: `0` to `2`, `3+` | |
| `result_basis` | categorical | `marked`, `approximation`, `none` | |
| `result_numbers` | number | | |
| `max_decimals` | number | most decimals of any number in the working | code output is not in the working unless in a text block |
| `long_decimals` | boolean | a number with 7 or more significant figures | |

### math.units, math.methods, math.code

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `unit_system` | categorical | as for engineering, below | the givens fix it in most tasks |
| `unit_style` | categorical | compound units written with `/` (`slash`), with negative powers (`exponent`), `both`, `none` | |
| `unit_symbols` | set | units found after numbers or in brackets | |
| `concentration_notation` | set | `molar`, `mol-per-litre-slash`, `mol-per-litre-exponent`, `mol-per-dm3` | |
| `methods` | set | names found anywhere in the reply: `euler`, `heun`, `runge-kutta`, `ode-solver`, `charge-balance`, `henderson-hasselbalch`, `t-test`, `wilcoxon`, `shapiro-wilk`, `centered-sums`, `annuity-formula`, `microstates` and others (the table in `math/values.py`) | a method named and rejected counts; which one the result rests on is the rubric's |
| `code_present` | boolean | a file in a programming or scripting language | |
| `code_languages` | set | | |
| `plot_code` | boolean | plotting calls of matplotlib, seaborn, plotly, ggplot, base R, MATLAB, Julia, or a TikZ picture | plots described or drawn in text are the rubric's |
| `plot_libraries` | set | | |

### math.constants

Each is a categorical: the value, `several` (more than one distinct value),
`not-stated`, or `not-relevant` (the reply is not about a projectile, or not
about a titration). Values outside a plausible range are ignored.

| Feature | Value | Read from |
|---|---|---|
| `g_value` | `9.81` | `g =`, or a 9.8 followed by m/s |
| `drag_coefficient` | `0.47` | `C_d =`, "drag coefficient ..." |
| `air_density` | `1.225` | `ρ =`, "air density ..." |
| `projectile_mass` | `0.145 kg` | "mass ...", `m =`, with kg or g |
| `projectile_diameter` | `0.074 m` | "diameter ...", `d =`, with m, cm or mm |
| `ka_value`, `pka_value`, `kw_value` | `1.8e-05`, `4.74`, `1e-14` | `K_a`, `Kₐ`, `pK_a`, `K_w`, followed by `=`, `:`, "is" or "of", with a bracket or "of/for ..." between if need be; `10^-14` alone is a value |

Blind spots: a value given only in code or only in a table without a symbol
or name beside it; a radius given instead of a diameter reads as
`not-stated`.

### engineering.units, engineering.safety, engineering.standards

The engineering extractors read the whole reply, code and comments included.
Quantities are the exception: they are read from the working, the code's
comments and the code outside its strings, so that a plot label or its closing
quote is no dimension. A fraction is read whole (`1 1/2 in` is 1.5 in), and
`2g` closed up is twice gravity and is not read (so two grams written `2g` are
missed).

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `unit_system` | categorical | `metric`, `us-customary` (4 in 5 or more of the units found), `both`, `none`. Units count only after a number or alone in brackets; `in` only before punctuation or a word of size. Time, speed of rotation and electrical units count for neither | dimensions given only as variable names (`width_mm`) |
| `metric_mentions`, `us_mentions` | number | | |
| `unit_symbols` | set | | |
| `safety_factor` | categorical | the value stated beside "safety factor", "factor of safety", "design factor", FoS, SF or FS (also after `>=` or `≥`, and as ", n = 2"): a number from 1 to 20, `several`, `range`, `none` (never mentioned), `null` (mentioned, no value read). Values that read as results are skipped: "achieved", "gives", "about", "≈", part of a sum or an inequality, "so FS ≥ 1.3", or two decimals not ending in 0 or 5 | a round achieved value stated plainly reads as the chosen one; a factor given only as "n = 2" |
| `safety_factor_mentioned` | boolean | | |
| `safety_factor_values` | set | | |
| `standard_bodies` | set | `ISO`, `DIN`, `EN`, `BS`, `ASTM`, `ASME`, `ANSI`, `AGMA`, `AISC`, `Eurocode`, `NEMA` and others | textbooks and catalogues are the rubric's `formula_source` |
| `standards` | set | designations with a number (`EN 1993-1-1`, `ASTM A228`) | AISI and SAE numbers are material grades and are not counted |
| `standards_cited` | boolean | | |

### engineering.checks, engineering.materials, engineering.quantities, engineering.cad

| Feature | Type | Normalisation | Blind spots |
|---|---|---|---|
| `checks` | set | checks **named**: `bending`, `shear`, `torsion`, `deflection`, `yield`, `buckling`, `fatigue`, `natural-frequency`, `coil-bind`, `bearing-stress`, `screw-load`, `stress-concentration`, `creep`, `cavitation`, `weld`, `junction-temperature` | a check dismissed in words counts; one done with numbers and never named is missed (the rubric's `checks_performed`) |
| `spring_end_type` | categorical | `squared-and-ground`, `squared`, `plain-and-ground`, `plain`, `open`, `several`, `not-stated`, `no-spring`; a line or row declaring the end type wins over other mentions | |
| `stress_correction` | categorical | `wahl`, `bergstrasser`, `both`, `not-mentioned`, `no-spring` | |
| `materials` | set | material families found anywhere | a rejected material counts; which one is designed in is the rubric's `material_assumed` |
| `supply_voltage` | categorical | the one voltage of 3 V or more, `several`, `not-stated` | a velocity written `5 V` |
| `supply_voltages` | set | | |
| `pipe_roughness_mm` | categorical | a roughness height in mm, `several`, `not-stated`, `not-relevant` (no pipe) | a Hazen-Williams C is not a height |
| `water_temperature_c` | categorical | a temperature written beside "water" | a temperature given elsewhere in a table |
| `quantities` | set | every `value unit` found, at most 200: the numbers and chosen dimensions, for the answer checker | which number is which dimension is not read |
| `cad_format` | categorical | `openscad`, `dxf`, `step`, `stl`, `svg`, `gcode`, `cadquery`, `build123d`, `freecad`, `ezdxf`, `solidpython`, `svg-python`, `several`, `none` | drawings in text characters; macros of CAD programs |
| `cad_formats` | set | | |
| `code_languages` | set | programming languages and OpenSCAD | |
| `cad_parameters` | set | `name=value` for numbers assigned at the start of a line in OpenSCAD or in a Python CAD file: the default dimensions | values inside calls |

### Not read

- **Stock phrases** for these types (the rubric's `opening` and `closing`
  cover how a reply starts and ends).
- **The motor speed, section shape, pump type** and the other items the split
  gives to the rubric.

## Relation to the prompts

Some features can be dictated by an L2 prompt (an L2 bakery brief names a
cyan accent and square corners). Extractors record what the page does either
way; deciding which features a prompt fixed, and leaving them out of a
default, is done by the metrics ([metrics.md](metrics.md), "Open choices"),
from the list in
[analysis/website/dictated.yaml](../analysis/website/dictated.yaml), which
was read from
[prompts/website/leak-check.md](../prompts/website/leak-check.md). How each
feature is counted (its type, role and bins) is in
[analysis/website/features.yaml](../analysis/website/features.yaml); raising
an extractor's version means updating that file. The other types have the
same two files in `analysis/<type>/`.
