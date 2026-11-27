# WebDev Arena dataset: licence and import (T5.2)

Checked 2026-11-26 from the publisher's own pages. This is a reading of the
published terms, not legal advice.

**State:** the importer is written and tested on invented rows. **No dataset
row or data file has been downloaded, and nothing has been imported.** Getting
the data means accepting an agreement, which is the owner's decision
([below](#decision-for-the-owner)).

## Source and version

| | |
|---|---|
| Dataset | WebDev Arena Preference Dataset, [`lmarena-ai/webdev-arena-preference-10k`](https://huggingface.co/datasets/lmarena-ai/webdev-arena-preference-10k) on Hugging Face |
| Publisher | LMArena (now Arena) |
| Revision | `7c397e652ffb8c2384e6d71d21d8388c19365fdc` |
| Dates | repository created 2025-01-15, last changed 2025-03-10 ([API record](https://huggingface.co/api/datasets/lmarena-ai/webdev-arena-preference-10k)) |
| Contents | the card says "10K real-world Webdev Arena battle with 10 state-of-the-art LLMs"; one file, `data/webdev-arena-preference-10k.json` (the repository uses about 194 MB) |
| Columns | `model_a`, `model_b`, `conversation_a`, `conversation_b`, `winner`, `tstamp`, `anony`, `question_id` (as the dataset page lists them) |
| Background | [WebDev Arena blog post](https://arena.ai/blog/webdev-arena/), 2025-03-10 |

## Licence

The card's licence tag is `other`. The repository's `LICENSE` file is empty (0
bytes); the terms are the "Dataset License Agreement" in the
[card](https://huggingface.co/datasets/lmarena-ai/webdev-arena-preference-10k#dataset-license-agreement).
It is not an open licence. Some third-party pages call the dataset CC BY 4.0;
the publisher's card does not.

How it binds:

> "By clicking to accept, accessing the Arena Dataset, or both, you hereby
> agree to the terms of the Agreement."

The grant:

> "a limited, non-exclusive, non-transferable, non-sublicensable license to
> use the Arena Dataset, including the conversation data and annotations, to
> research, develop, and improve software, algorithms, machine learning
> models, techniques, and technologies for both research and commercial
> purposes."

The conditions:

| Clause | Short quote or summary |
|---|---|
| Prohibited Transfers | "You should not distribute, copy, disclose, assign, sublicense, embed, host, or otherwise transfer the dataset to any third party." |
| Right to Request Deletion | "At any time, we may require you to delete all copies of the dataset", with written confirmation on request |
| Termination | at any time, for any reason, on notice; then stop using it and destroy all copies |
| Model Specific Terms | "Users must adhere to the terms of use of model providers." |
| Non-Identification | "You must not attempt to identify the identities of any person (individuals or entities) or infer any sensitive personal data" |
| Safety and Moderation | it "contains unsafe conversations"; apply filters |
| Legal Compliance | follow applicable laws |
| Liability, endorsement | no indirect or consequential damages; the content is not the publisher's view |

## What it permits

| Use | Reading |
|---|---|
| Download | Only by someone who accepts the agreement. |
| Local analysis | Yes, for research and commercial purposes, under the conditions, until terminated. |
| Redistribution | **No.** No rows, prompts, replies, extracted files or record files may be committed, hosted or sent to anyone. |
| Publishing screenshots or excerpts | Treat as not allowed: they copy and disclose the data. |
| Publishing aggregate figures (shares of fonts, colours and so on) | **Not addressed.** The agreement neither allows nor forbids statistics derived from the data. |
| Sending content to a model provider (such as the tagger) | Unclear, and could count as disclosure to a third party. Do not do it without the owner's decision. |

Each model's replies are also under its provider's terms
([terms/](terms/README.md)); several of the models in a 2025 dataset are from
providers not reviewed there.

## Gating

The card configures a gate: a prompt ("You agree to the Dataset License
Agreement"), the button "I agree to the terms and conditions", and a form
asking for **Name, Email, Affiliation and Country**. On the day of the check
Hugging Face's API reported `"gated": false`, so the form appeared not to be
switched on. A missing technical gate does not remove the agreement: access
alone is said to be acceptance. Nothing was accepted, no account was used and
no contact details were given.

## Data protection

- The rows are conversations: prompts typed by members of the public, and the
  replies. The card of this dataset says nothing about removing personal data,
  so assume some may be present.
- Do not try to identify anyone (a condition of the agreement).
- Keep input and output on this machine under `data/` (gitignored), and delete
  all of it, including the extracted files, if asked or if the licence ends.
- Prompts and replies are not scrubbed or filtered by the importer.

## Newer datasets that are openly licensed

The same publisher released two datasets on 2026-11-12, ungated, whose cards
say "User prompts are licensed under CC-BY-4.0, and model outputs are governed
by the terms of use set by the respective model providers" and that they were
"run through PII de-identification":

| Dataset | Contents |
|---|---|
| [`arena-webdev-preferences`](https://huggingface.co/datasets/lmarena-ai/arena-webdev-preferences) | 6,390 pairs of websites from agentic build sessions, with prompts, traces and votes; one Parquet file of about 655 MB |
| [`arena-webdev-correctness`](https://huggingface.co/datasets/lmarena-ai/arena-webdev-correctness) | 189 versions of agent-built games labelled working or broken; about 12 MB of Parquet and 134 MB of assets |

They were not downloaded and the importer does not read them. They are not a
drop-in replacement: the outputs come from agent sessions, not single replies;
their cards give no date range, so whether they cover retired models is not
known; and the licence statement covers prompts, not model outputs. See the
[announcement](https://arena.ai/blog/interaction-as-a-judge).

## Decision for the owner

1. **Accept the 10k agreement?** If yes, you accept it and fetch the file
   yourself, into a new empty folder under `data/`. The project then keeps the
   data private, publishes at most aggregate figures (which the agreement does
   not address; asking the publisher first would settle it) and deletes it on
   request.
2. **Or** do without the historical baseline.
3. **Or** have a separate task look at the CC BY 4.0 datasets above.

## Importing

```
python -m importers.webdev_arena data/webdev-arena/source/webdev-arena-preference-10k.json data/webdev-arena/records.jsonl --revision 7c397e652ffb8c2384e6d71d21d8388c19365fdc --limit 20
python -m runner.record --files data/webdev-arena/records.jsonl
```

The input is read as a stream (JSON array or JSON Lines; at most 16 MB per
row), only parsed as JSON, never executed. `--limit` reads only the first rows:
use it first, to check the assumed shape. The output file must be new, and
inside a git checkout it must be under `data/`, `runs/` or `outputs/`. The
command prints counts, never prompts or replies. To run an import again,
delete the earlier output file and its `files/` folder first, or use a new
folder.

### Assumed row shape

**Not verified against the dataset.** The card names the columns only.

- `conversation_a` and `conversation_b` are lists of messages with `role`
  (`system`, `user` or `assistant`) and `content`: text, or a list of parts of
  which those with `type: "text"` hold `text`.
- `tstamp` is seconds since 1970, or ISO 8601 text with a time zone.
- A reply may be a JSON object with `file_path` and `code`, the format the blog
  post says the arena asked models for; the dataset may store it differently.

Anything else is skipped and counted. If most of a sample is skipped, the
assumption is wrong and the importer needs changing.

### Rows to records

Each row gives up to two records, one per side
([record-format.md](record-format.md)).

| Field | Value |
|---|---|
| `source` | `uncontrolled_import` |
| `source_note` | dataset, revision, `question_id`, side, and what is missing or inferred |
| `record_id` | derived from dataset, `question_id` and side, so a row imports under the same id every time |
| `project_type`, `task_id` | `website`, `uncontrolled-prompt` |
| `model_id` | the model name as given |
| `provider` | from the brand at the start of the model name, else `unknown` |
| `surface` | `product` (made through the arena's web app) |
| `timestamp` | `tstamp`; a side without a usable one is skipped, never dated by guess |
| `prompt_text`, `raw_response` | the first user message and the reply to it; later turns are left out and noted |
| `status` | `ok`: reply text is present. Whether it was cut off is not reported |
| `files` | `code` saved as `file_path`, else code blocks and HTML documents, under the rules of `runner.files` |
| everything else | null or empty: no batch, level, wording, run index, settings, tokens or cost |

The vote (`winner`) and `anony` are not imported.

## Kept apart from controlled runs

The metrics take only `controlled` records on the `api` surface
([metrics.md](metrics.md#which-runs-count)), and report how many others they
left out. Imported records also have no batch id, so no batch selects them.
`tests/test_webdev_arena.py` checks both. Any later historical comparison must
label these figures as uncontrolled prompts.
