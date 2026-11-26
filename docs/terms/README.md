# Provider terms (T0.7)

**This is not legal advice.** It summarises what four providers' published terms
say about storing, sharing and publishing model outputs, so that the Human can
decide what may enter this public repository (T6.3). Generated outputs stay out
of git until then.

One page per provider: [Anthropic](anthropic.md), [OpenAI](openai.md),
[Google](google.md), [DeepSeek](deepseek.md). Each links every claim to the
document it comes from, gives that document's date, quotes the decisive words,
and keeps interpretation under a separate "Reading" heading.

## How this was made

- All documents were fetched on 2026-11-26 with plain HTTPS requests and read as
  text. Quotes were copied from that text; only typographic quotes and dashes
  were normalised. No account was created, no terms were accepted and no
  personal details were sent.
- The Gemini API terms page builds its text in the browser; its wording was read
  from the source text embedded in the page.
- Not read: the DeepSeek copy at platform.deepseek.com (HTTP 403; the CDN copy
  was read instead), the documents the terms incorporate but which say nothing
  on outputs (payment, credit and Cloud billing terms), and Anthropic's and
  Google's version histories. Some help and docs pages show no date; the tables
  say so.
- Written by an AI model (Claude Opus 5.5, made by Anthropic, one of the four
  providers). Read the linked documents before relying on any summary.
- Terms change. Anthropic's Commercial Terms change 30 days after posting;
  DeepSeek's Open Platform Terms 7 days after release. Re-check before T6.3.

## Comparison: API use

| | Anthropic | OpenAI | Google | DeepSeek |
|---|---|---|---|---|
| Main API terms | Commercial Terms, Jun 17, 2025 | Services Agreement, Jan 1, 2026 | Gemini API Additional Terms, Mar 23, 2026, with Google APIs Terms, Nov 9, 2021 | Open Platform Terms, Apr 29, 2026, with Terms of Use, Mar 27, 2026 |
| Who owns outputs | user (assigned, "if any") | user (assigned, "if any") | Google claims no ownership; nothing assigned | user (assigned, "if any") |
| API data used for training by default | no | no | paid: no; unpaid: yes, with human review | not stated in API terms; Terms of Use allow de-identified use with opt-out |
| Default retention | deleted within 30 days; flagged content up to 2 years | abuse logs up to 30 days; Responses API state at least 30 days unless `store` is false | paid: abuse logs 55 days; Interactions API keeps state unless `store` is false | no period; input kept "for as long as you have an account" |
| Storing outputs | no restriction found | no restriction found | unclear: APIs Terms §5(e) bars "permanent copies" without the content owner's permission | no restriction found |
| Publishing outputs | no restriction found | allowed: review each one, attribute, label as AI | unclear: APIs Terms §5(e) | allowed: label as AI, verify first |
| Training other models on outputs | not for competing models, or at all without authorisation | not for substitute models, including "supply" of data | not for competing models | expressly allowed |
| Benchmarking, comparison | not mentioned | expressly allowed | not mentioned | not mentioned |
| AI disclosure when sharing | no general duty; no misleading origin | label AI-generated | do not claim human-made to deceive | label AI-generated |
| Naming the provider | no restriction found | §10 "No Publicity" | no implied endorsement | §5.2: not "in any way" without permission |
| Governing law | Ireland (EEA, CH, UK), else California | Ireland (EEA, CH, UK), else California | California | People's Republic of China |

## Comparison: consumer products (T5.1, prompts typed by hand)

| | Claude.ai | ChatGPT | Gemini Apps |
|---|---|---|---|
| Automation | forbidden except through an API key | no automatic or programmatic extraction | no automated access against robots-style instructions |
| Ownership | assigned to user | user owns | Google claims no ownership |
| Chats used for training | yes unless opted out; even then feedback and chats flagged for safety review | yes unless opted out | per Gemini History settings; with the setting off, still used for training if you provide feedback; used for safety with human review regardless |
| Publication duties | none found beyond the Usage Policy (no plagiarism, no misleading origin) | Sharing & Publication Policy applies: review each one, attribute, label as AI | do not mislead others that AI content was made by a human |
| Training other models on outputs | not to develop competing products, "including to develop or train any artificial intelligence or machine learning algorithms or models"; Usage Policy distillation rule | not for substitute models (Usage Policies); "Use Output to develop models that compete with OpenAI" | not "to develop machine learning models or related AI technology", with no competition limit |

Reading: typing prompts by hand and saving the answers fits all three products'
automation rules.

## Points that apply to several providers (reading, not legal advice)

1. No document read forbids publishing outputs outright. Google's is the unclear
   case: the APIs Terms limit distributing "content returned from the APIs"
   without the content owner's permission, and Google names no owner.
2. Explicit disclosure duties come from DeepSeek (label and verify) and OpenAI
   (review, attribute, label; for the API and for ChatGPT alike). A visible
   AI-generated label on every published record, with model and date, appears
   to meet the labelling part for all four; it does not cover review,
   verification or attribution.
3. Through the API, Anthropic, OpenAI and Google forbid training competing (or,
   for OpenAI, substitute) models on outputs; a public dataset lets anyone do
   that. Anthropic's §D.4(c) ("support any third party's attempt") and OpenAI's
   "supply" go furthest. None says whether publishing counts.
4. The consumer products are stricter in one case. The Google Terms that govern
   Gemini Apps forbid "using AI-generated content from our services to develop
   machine learning models or related AI technology", with no competition limit.
   Claude.ai's rule is framed as competition, but it names training "any
   artificial intelligence or machine learning algorithms or models". The text
   does not say whether sibar's own tagger or scoring (T2.5, T4) run on T5.1
   outputs, or publishing those outputs, is caught.
5. OpenAI §10 and DeepSeek §5.2, read literally, restrict naming them on a
   website. Both seem aimed at marketing, but neither has an exception for
   factual reference, and sibar records must name the model.
6. Ownership is assigned "if any": the terms do not say whether outputs are
   protected by copyright, and outputs may contain third-party material (OpenAI
   says code output may carry open source licences). That is a legal question
   the terms leave open.
7. The runner currently leaves `store` at its default for OpenAI and Google, so
   both keep response state (OpenAI at least 30 days).
8. Storing, not only publishing, may be affected for Google: APIs Terms §5(e)
   also covers building databases or permanent copies of returned content.

## Decisions for the Human

All unmade. Tick and date each one; T6.3 records the final decision.

Scope
- [ ] Which providers' API outputs may enter the repository:
  [ ] Anthropic [ ] OpenAI [ ] Google [ ] DeepSeek
- [ ] Whether consumer-product outputs from T5.1 may enter:
  [ ] Claude.ai [ ] ChatGPT [ ] Gemini Apps
- [ ] What is published: full raw responses, extracted files, excerpts, or
  metrics only.

Conditions on anything published
- [ ] Wording and placement of the AI-generated label (each record, dataset
  README, or both).
- [ ] Attribution for OpenAI's "your name or your company" condition (OpenAI API
  and ChatGPT outputs from T5.1), given that the repository publishes no
  personal names (for example, the project name).
- [ ] How to meet OpenAI's "Manually review each generation" (OpenAI API and
  ChatGPT outputs) and DeepSeek's "verify the authenticity and accuracy": full
  review, a sample with a notice, or asking the providers.
- [ ] How published records describe authorship and who takes responsibility,
  given OpenAI's sentence that people "should not represent API-generated
  content as being wholly generated by a human or wholly generated by an AI"
  (written for co-authored work; sibar's records are unedited model output).
- [ ] Licence for published outputs, and whether it forbids training models on
  them.
- [ ] How records name providers and models given OpenAI §10 and DeepSeek §5.2,
  and whether to ask either for permission.

Data handling
- [ ] Google tier: unpaid quota (outputs may be used for training and read by
  reviewers) or paid.
- [ ] Whether the runner sends `store: false` to OpenAI and Google. It limits
  retention but departs from sending provider defaults only.
- [ ] Whether DeepSeek is acceptable, given storage in China, PRC law and terms
  that do not settle training on API data.
- [ ] Account settings for T5.1: training opt-out on or off; temporary or
  incognito chats; no thumbs-up or thumbs-down ratings or other feedback
  (Claude.ai counts ratings as Feedback used for training even after opting
  out; Gemini Apps, with the setting off, does not train on future chats
  "unless you provide feedback").
- [ ] Whether sibar's own tagger or scoring (T2.5, T4) may be run on T5.1
  outputs from Gemini Apps and Claude.ai, given their consumer training rules,
  and whether those outputs may be published.
- [ ] Which account type is used with each provider, and whether sibar counts as
  "professional or business purposes" (Google) and a business "Customer"
  (Anthropic, OpenAI).

Process
- [ ] Whether to get legal advice, or written confirmation from a provider,
  before T6.3 (Google §5(e) first).
- [ ] Date on which these terms are re-checked before T6.3.
