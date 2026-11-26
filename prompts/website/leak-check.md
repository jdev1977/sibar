# Leak check of the website prompts (T1.2)

All 36 prompts in this folder were read as sent and judged against the rules
in [docs/leak-check.md](../../docs/leak-check.md).

**Result: 20 pass as written, 16 rewritten.**

| Level | Pass | Rewritten |
| --- | --- | --- |
| L0 | 12 | 0 |
| L1 | 8 | 4 (pricing page A and B, dashboard A and B) |
| L2 | 0 | 12 |

No run had used these texts, so `prompt_set_version` stays "1" under the
pre-run rule in [README.md](README.md). The fingerprints in
[tests/test_website_prompts.py](../../tests/test_website_prompts.py) were
updated. The text before this check is in git at commit `004c3e6`.

## Rulings that apply to every task

The reasons are in [docs/leak-check.md](../../docs/leak-check.md).

1. **An L2 brief does not name a default in order to forbid it.** Every such
   line was rewritten to say what is wanted. This is why all twelve L2
   prompts changed.
2. **Wording B stays a longer question, and first-person prose at L2.** A
   against B is one bundled wording factor. The pairs were checked for equal
   information, and one inequality was fixed (pricing page L2 B fixed the
   order of the sections).
3. **"Make" against "Can you build" stays.** Neither names a technology, and
   the pair is the same in every cell.
4. **B says "please" once at L2 and never at L0 or L1; A never does.** Four
   of the six L2 B texts had one "please". The other two now have one too.
5. **US spelling throughout.** "Grey", "labelled" and "cancelling" were
   changed, and the British idiom "weigh up" was removed from an L1.
6. **The single accent color of an L2 must lie outside the expected default
   for its task and outside the violet family.** Two accents changed (bakery,
   portfolio).

Phrases that were flagged and kept are listed under each task.

## bakery-landing

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The plan's own L0 example. It gives the verb, "website" and the subject, and nothing else. |
| L0 B | pass | The same request in B's fixed form. It gives the same facts as A. |
| L1 A | pass | The plan's own L1 example. "Neighborhood" is the audience and "takes weekend pre-orders" is the purpose. |
| L1 B | pass | The same three facts as A: local to the neighborhood, sourdough, weekend pre-orders. |
| L2 A | rewritten | The tone and visual lines named defaults to forbid them, and the one accent was in the hue family of the expected default. |
| L2 B | rewritten | As L2 A. |

Flagged and kept:

- "Sourdough" (L1) suggests a handmade, warm look. It describes the business,
  not the site, and it is in the plan's example. A shift from L0 to L1 on
  palette or type includes this association.
- "Takes weekend pre-orders" (L1) implies an order form. That is the purpose,
  not a component: the prompt does not say how orders are taken.
- "Off-white background" (L2) is close to the expected cream background. It is
  the paper of the newsprint look, so it stays. Do not read background color
  as a persisting default for this task.

Rewrites:

**L2 A**

Old:
> Tone: plain and matter-of-fact. Short sentences, no exclamation marks, no puns.

New:
> Tone: plain and matter-of-fact. Short, literal sentences that end in a period.

Old:
> Visual direction: a stark, newsprint-like look. Black text on an off-white background, with signal orange as the only accent. Condensed sans-serif headings, and a monospace face for prices and hours. Square corners, thin black rules between sections, no shadows and no gradients.

New:
> Visual direction: a stark, newsprint-like look. Black text on an off-white background, with cyan as the only accent. Condensed sans-serif headings, and a monospace face for prices and hours. Square corners, thin black rules between sections, and flat, solid color throughout, like ink on paper.

**L2 B**

Old:
> Please keep the writing plain and matter-of-fact: short sentences, with no exclamation marks and no puns. For the look, we want something stark and newsprint-like: black text on an off-white background, and signal orange as the one accent. Headings in a condensed sans-serif, prices and hours in a monospace face. Square corners, thin black rules between sections, and no shadows or gradients.

New:
> Please keep the writing plain and matter-of-fact: short sentences that mean exactly what they say and end in a period. For the look, we want something stark and newsprint-like: black text on an off-white background, and cyan as the one accent. Headings in a condensed sans-serif, prices and hours in a monospace face. Square corners, thin black rules between sections, and every color flat and solid, like ink on paper.

Why the accent changed: the expected bakery default is cream and brown with
amber or orange accents. Brown is a dark orange, so a signal-orange accent
sits in the same hue family as the default. A model that obeyed the brief
would then show no movement in accent hue. Cyan is the opposite hue, fits a
print look, and is not the plain blue of an unstyled link.

## pricing-page

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | "Pricing page" is the task and "a software product" is the subject. |
| L0 B | pass | "A piece of software" means the same as "a software product". |
| L1 A | rewritten | "Compare the plans" shares its root with a page pattern, the comparison table, and B had no such word. |
| L1 B | rewritten | "Weigh up" is a British idiom. A locale hint can steer currency and spelling, which are open choices at L1. |
| L2 A | rewritten | The tone and visual lines named defaults to forbid them and quoted three stock phrases. |
| L2 B | rewritten | As L2 A. B also fixed the order of the sections, which A leaves open, and used two British spellings. |

Flagged and kept:

- "Page" (all levels) may suggest a single page. It is the task as the plan
  names it, and it is the same at every level.
- "The plans" (L1) says that there is more than one plan. The purpose,
  choosing a plan, cannot be stated without it. It gives no number and no
  layout.
- "Comparison table" and "the plan comparison" (L2) are a dictated layout,
  which L2 may give. They point away from the expected three cards.
- "Credit card", "PDF" and "CSV" (L2) are facts about the product, not about
  how the page is built.
- L2 does not repeat the L1 purpose in words. The sign-up buttons carry it.

Rewrites:

**L1 A**

Old:
> Make a pricing page for an invoicing tool for freelancers, so they can compare the plans and pick the right one.

New:
> Make a pricing page for an invoicing tool for freelancers, so they can pick the plan that suits them.

**L1 B**

Old:
> Can you build a pricing page for invoicing software aimed at freelancers? It should help them weigh up the plans and choose one that fits.

New:
> Can you build a pricing page for invoicing software aimed at freelancers? It should help them decide which of the plans is right for them.

**L2 A**

Old:
> Tone: plain and honest. No hype words such as "supercharge" or "seamless".

New:
> Tone: plain and honest. Describe each feature in everyday words, and claim only what a plan includes.

Old:
> Visual direction: an account-book feel. A warm paper-cream background with dark green ink, and one book-style serif for all text. Show the plans in a single comparison table with ruled lines, not as separate cards. Do not mark any plan as "most popular". No gradients and no rounded corners.

New:
> Visual direction: an account-book feel. A warm paper-cream background with dark green ink, and one book-style serif for all text. Show the plans in a single comparison table with ruled lines, and give all three plans equal weight. Flat, solid color and square corners throughout.

**L2 B**

Old:
> They can all be exported as PDF or CSV, and they remain available for 90 days after cancelling.

New:
> They can all be exported as PDF or CSV, and they remain available for 90 days after canceling.

Old:
> The page should open with a short heading and introduction, then compare the plans, then show the FAQ, and finish with a line inviting questions to hello@example.com. Every plan needs its own sign-up button, labelled "Start free" for Starter and "Start 30-day trial" for Solo and Studio.

New:
> The page needs a short heading and introduction, a comparison of the plans, the FAQ and, to close, a line inviting questions to hello@example.com. Every plan needs its own sign-up button, labeled "Start free" for Starter and "Start 30-day trial" for Solo and Studio.

Old:
> Keep the copy plain and honest, without hype words like "supercharge" or "seamless". As for the look, think of an account book: a warm paper-cream page, dark green ink, and a single book-style serif for every bit of text. The plans belong in one comparison table with ruled lines, rather than in separate cards. No plan should be marked "most popular", and there should be neither gradients nor rounded corners.

New:
> Please keep the copy plain and honest: everyday words for each feature, and claims kept to what a plan includes. As for the look, think of an account book: a warm paper-cream page, dark green ink, and a single book-style serif for every bit of text. The plans belong in one comparison table with ruled lines, all three carrying equal weight. Color should be flat and solid everywhere, and every corner square.

## portfolio

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | "Personal" says whose portfolio it is, not how it looks. The profession is left open, which is a default to measure. |
| L0 B | pass | "For an individual" means the same as "personal". |
| L1 A | pass | "Freelance furniture maker" is the person. "Win commissions from homeowners" is the purpose and the audience. |
| L1 B | pass | The same facts as A: "independent" for "freelance", and "get homeowners to commission pieces". |
| L2 A | rewritten | One visual line named a default to forbid it, the one accent was in the violet family, and "grey" was British spelling. |
| L2 B | rewritten | As L2 A. |

Flagged and kept:

- "Furniture maker" (L1) suggests wood tones and a craft look. It describes
  the person, not the site. A shift from L0 to L1 includes this association.
- "Pale gray-blue background" with "charcoal text" (L2) is close to a common
  light default (a very pale blue-gray page with dark gray text). It differs
  from both defaults expected for this task, warm beige and a dark page, so
  it stays. Check it against the pilot.
- "Plenty of empty space" (L2) is a positive direction and a common one. It
  stays as part of the gallery look.
- "Placeholder image" (L2) is content: the brief has no photos to give.

Rewrites:

**L2 A**

Old:
> Visual direction: cool and gallery-like. A pale grey-blue background, charcoal text and one muted lilac accent. Headings in a high-contrast didone serif, body text in a humanist sans-serif. An asymmetric, left-aligned layout with plenty of empty space. Images run full width with square corners. No icons.

New:
> Visual direction: cool and gallery-like. A pale gray-blue background, charcoal text and one hot-pink accent. Headings in a high-contrast didone serif, body text in a humanist sans-serif. An asymmetric, left-aligned layout with plenty of empty space. Images run full width with square corners. Links and labels are words only.

**L2 B**

Old:
> Visually it should feel cool, like a gallery. The background is a pale grey-blue, the text is charcoal, and a muted lilac is the only accent. For type, a high-contrast didone serif on the headings and a humanist sans-serif for the body. The layout should be asymmetric and aligned left, with lots of empty space; images go full width with square corners; and there are no icons.

New:
> Visually it should feel cool, like a gallery. The background is a pale gray-blue, the text is charcoal, and hot pink is the only accent. For type, a high-contrast didone serif on the headings and a humanist sans-serif for the body. The layout should be asymmetric and aligned left, with lots of empty space; images go full width with square corners; and every link and label is in words alone.

Why the accent changed: lilac is a pale violet. Violet and indigo accents
are the best-known model default, and this set's own comments name them as
the expected default for the pricing page and the to-do app. A model that
obeyed the brief would then match the default on accent hue. Hot pink is far
from violet, from wood browns and from the muted pinks of a craft look.

## event-page

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | "Web page" and "event" are the task. |
| L0 B | pass | The same request in B's fixed form. |
| L1 A | pass | "Free", "one-day", "repair", the volunteers and the household items say what the event is. "Local residents who might bring something in" is the audience and the purpose. |
| L1 B | pass | The same facts as A: "at no charge" for "free", "may want to bring something along". |
| L2 A | rewritten | One visual line named a default to forbid it. |
| L2 B | rewritten | As L2 A. B also lacked the one "please" that the other L2 B texts have. |

Flagged and kept:

- "Web page" (all levels) suggests one page. It is the task as the plan names
  it ("event page").
- "Repair event" (L1) suggests green, community looks. It describes the event.
- "No gas appliances or microwaves" and "fixes are not guaranteed" (L2) are
  the event's house rules, which are page content.
- "Teal" (L2) is next to the expected green default. It is one of two inks,
  beside fluorescent pink on yellow paper, so the palette as a whole is far
  from the default. Check it against the pilot.
- "Small electricals" (L2) is British usage. It is vocabulary in dictated
  content, not spelling, and both wordings have it.

Rewrites:

**L2 A**

Old:
> Headings in a heavy slab serif, body text in a typewriter-style face. No emoji. It should feel handmade and a little rough.

New:
> Headings in a heavy slab serif, body text in a typewriter-style face. Headings and labels are words only. It should feel handmade and a little rough.

**L2 B**

Old:
> the booking form and how to volunteer. Keep the tone welcoming and practical.

New:
> the booking form and how to volunteer. Please keep the tone welcoming and practical.

Old:
> A heavy slab serif for the headings and a typewriter-style face for the body. Leave out emoji. It should come across as handmade and slightly rough.

New:
> A heavy slab serif for the headings and a typewriter-style face for the body. Keep headings and labels to words alone. It should come across as handmade and slightly rough.

## todo-app

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | "Web app" keeps the output inside the website type and names no technology. |
| L0 B | pass | "Runs in a web browser" means the same as "web app". It is the longest L0, about twice the length of A, and adds no fact. |
| L1 A | pass | "A university student" is the audience. "Keep track of assignments and deadlines" is the purpose. |
| L1 B | pass | The same facts as A: "coursework and when each piece is due". |
| L2 A | rewritten | The last visual line named three defaults to forbid them. |
| L2 B | rewritten | As L2 A. |

Flagged and kept:

- "Deadlines" (L1) implies a due date for each task. That is content the
  purpose needs, not a layout.
- "No accounts or sign-in" (L2) names something to leave out. It is a
  functional limit, and accounts are not a default being measured for this
  task, so the reason for ruling 1 does not apply.
- "Keep tasks on this device after the page is reloaded" (L2) is a need and
  names no technology.
- "Show at the top" (L2) is a dictated position, which L2 may give.
- Primary blue and "a heavy geometric sans-serif" (L2) are near common
  defaults (a blue accent, a geometric sans). They belong to the Bauhaus look
  and are one part of a palette of four colors, so they stay. Expect less
  movement on fonts for this task, and check both against the pilot.
- The due dates (L2) stay in March 2027. A page rendered before then shows
  nothing overdue, and one rendered later shows everything overdue. Dates in
  the prompt cannot fix this; the renderer should use a fixed clock (see
  [docs/leak-check.md](../../docs/leak-check.md)).

Rewrites:

**L2 A**

Old:
> Headings in a heavy geometric sans-serif. Square checkboxes, no rounded corners, no shadows and no gradients.

New:
> Headings in a heavy geometric sans-serif. Square checkboxes, square corners on every shape, and flat, solid color throughout.

**L2 B**

Old:
> For headings, a heavy geometric sans-serif. Checkboxes should be square, and I don't want rounded corners, shadows or gradients anywhere.

New:
> For headings, a heavy geometric sans-serif. Checkboxes should be square, as should the corners of every other shape, and I want all the color flat and solid.

## dashboard

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | "Web page" keeps the output a web page. "Dashboard" is the task, and its subject is left open, which is a default to measure. |
| L0 B | pass | "A web page that works as a dashboard" means the same as "a dashboard web page". |
| L1 A | rewritten | "At a glance" says how the page should read. It adds nothing to "dashboard" as a purpose, and as a direction it favors a few large figures. |
| L1 B | rewritten | "A quick overview" is the same hint in other words. |
| L2 A | rewritten | The tone and visual lines named defaults to forbid them, "grey" was British spelling, and "at a glance" was removed to match L1. |
| L2 B | rewritten | As L2 A. |

Flagged and kept:

- "Food bank" and "volunteers" (L1) suggest a charity look. They describe the
  audience.
- "It cannot rely on an internet connection" (L2) is a real constraint,
  written as a need. It moves the library choice for this task by design.
- "Shown as a chart" and "drawn as simple bars" (L2) are dictated, which L2
  may do.
- "Flagged as low" (L2) leaves open how the flag looks.
- "312 kg" with a US date format, "food parcels" and "chiller" (L2) lean
  British. They are dictated figures and vocabulary, and both wordings have
  them.

Rewrites:

**L1 A**

Old:
> Make a dashboard web page for the volunteers at a food bank, so they can see at a glance how the day's distribution is going.

New:
> Make a dashboard web page for the volunteers at a food bank, so they can see how the day's distribution is going.

**L1 B**

Old:
> Can you build a web page that works as a dashboard for a food bank? Its volunteers want a quick overview of how the day's distribution is going.

New:
> Can you build a web page that works as a dashboard for a food bank? Its volunteers want to know how the day's distribution is going.

**L2 A**

Old:
> Make a dashboard web page for the volunteers at Ostrey Food Bank, so they can see at a glance how today's distribution is going.

New:
> Make a dashboard web page for the volunteers at Ostrey Food Bank, so they can see how today's distribution is going.

Old:
> Tone: plain labels, no jargon.

New:
> Tone: plain labels in everyday words.

Old:
> Visual direction: light and editorial, like a printed report. A warm white background with dark grey text. Numbers set in a serif with old-style figures. Charts in a single oxblood red with greys, drawn as simple bars. Separate the areas with thin hairline rules, with no boxes or cards. No icons and no rounded corners.

New:
> Visual direction: light and editorial, like a printed report. A warm white background with dark gray text. Numbers set in a serif with old-style figures. Charts in a single oxblood red with grays, drawn as simple bars. Separate the areas with thin hairline rules alone, and keep every corner square. Labels are words only.

**L2 B**

Old:
> Can you build a web page that works as a dashboard for Ostrey Food Bank? Our volunteers want to see at a glance how today's distribution is going.

New:
> Can you build a web page that works as a dashboard for Ostrey Food Bank? Our volunteers want to see how today's distribution is going.

Old:
> So the page needs the header, the key figures, households per hour, the stock levels with the low ones flagged, and the notes. Use plain labels without jargon.

New:
> So the page needs the header, the key figures, households per hour, the stock levels with the low ones flagged, and the notes. Keep the labels plain, in everyday words.

Old:
> As for the look, it should be light and editorial, in the manner of a printed report. Text in dark grey over a warm white background. Numbers in a serif, using old-style figures. Charts as plain bars in one oxblood red, plus greys. Thin hairline rules to divide the areas rather than boxes or cards, and no icons or rounded corners anywhere.

New:
> As for the look, it should be light and editorial, in the manner of a printed report. Text in dark gray over a warm white background. Numbers in a serif, using old-style figures. Charts as plain bars in one oxblood red, plus grays. Thin hairline rules, and nothing else, to divide the areas; square corners wherever a corner appears; and labels in words alone.

## What each L2 dictates

For the metrics (T1.5): the look choices each L2 brief fixes. Everything else
is left open at L2 as well, such as responsiveness, dark mode, accessibility,
libraries and file structure (except where noted).

| Task | Dictated at L2 | Close to the expected default |
| --- | --- | --- |
| bakery-landing | Palette, heading and price fonts, corners, flat color, section rules, copy tone | Off-white background |
| pricing-page | Palette, one font, plans in a table with equal weight, corners, flat color, copy tone | None found |
| portfolio | Palette, heading and body fonts, layout, image corners, words-only labels, copy voice | Pale gray-blue background, empty space |
| event-page | Palette, overprint effect, heading and body fonts, words-only headings and labels, copy tone | Teal as one of two inks |
| todo-app | Palette, a color per course, heading font, corners, flat color, interface text; tasks kept on the device | Blue as one of four colors, geometric sans |
| dashboard | Palette, number font, bar charts, rules as dividers, corners, words-only labels, label tone; works offline | None found |

The expected defaults are guesses until the pilot measures them.
