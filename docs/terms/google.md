# Google: storing, sharing and publishing outputs

**Not legal advice.** A summary of Google's published terms as fetched on
2026-11-26, for the decisions in [README.md](README.md). Models in scope:
`gemini-4-hydrogen`, `gemini-3.5-flash-lite` ([models.yaml](../../models.yaml)).
Quotes are short and verbatim (typographic quotes changed to ASCII); everything
under "Reading" is interpretation.

## Documents read

| Document | Covers | Date shown |
|---|---|---|
| [Gemini API Additional Terms of Service](https://aistudio.google.com/docs/terms) (old address ai.google.dev/gemini-api/terms redirects here) | Gemini API, AI Studio | effective Mar 23, 2026 |
| [Google APIs Terms of Service](https://developers.google.com/terms) | all Google APIs | last modified Nov 9, 2021 |
| [Generative AI Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy) | API and Gemini Apps | last modified Dec 17, 2024 |
| [Abuse monitoring](https://aistudio.google.com/docs/usage-policies), [Zero data retention](https://aistudio.google.com/docs/zdr), [Available regions](https://aistudio.google.com/docs/available-regions) | API retention, regions | none shown |
| [Google Terms of Service](https://policies.google.com/terms) | Gemini Apps (T5.1) | effective Jul 30, 2026 |
| [Gemini Apps Privacy Hub](https://support.google.com/gemini/answer/13594961) | Gemini Apps data | notice updated Nov 16, 2026 |

The Gemini API needs both the Google APIs Terms and the Additional Terms; "If
there is a conflict ..., the additional terms will control for that conflict."

## What the text says: API

- **Ownership.** Additional Terms, "Use of Generated Content": "Google won't
  claim ownership over that content", and "Google may generate the same or
  similar content for others". There is no assignment to the user.
- **Sharing and publishing.** "You're responsible for your use of generated
  content, and for the use of that content by anyone you share it with." The
  disclaimers say: "Use discretion before relying on, publishing, or otherwise
  using content provided by the Services."
- **Content returned from APIs.** Google APIs Terms §5(e): "Unless expressly
  permitted by the content owner or by applicable law", you will not, "with
  content returned from the APIs", "Scrape, build databases, or otherwise create
  permanent copies of such content" or "distribute, publicly display, or
  sublicense to any third party".
- **Restrictions.** "You may not use the Services to develop models that compete
  with the Services (e.g., Gemini API or Google AI Studio)", nor "reverse
  engineer, extract or replicate any component of the Services". The API is
  "for developers building with Google AI models for professional or business
  purposes, not for consumer use."
- **Benchmarking.** Not mentioned in any document above. The Prohibited Use
  Policy allows exceptions "based on educational, documentary, scientific, or
  artistic considerations".
- **Attribution and disclosure.** Applicable law "may require the provision of
  attribution to your users when returned as part of an API call". You must
  not "falsify or delete any author attributions ... or other labels of the
  origin or source of material" (§5(e)) or misrepresent "the provenance of
  generated content by claiming it was created solely by a human, in order to
  deceive" (Prohibited Use Policy). Publicity (§6(c)): no statement that
  "suggests partnership with, sponsorship by, or endorsement by Google".
- **Training and review.** Unpaid Services (free AI Studio, unpaid API quota):
  Google uses prompts and responses "to provide, improve, and develop Google
  products", and "human reviewers may read, annotate, and process your API input
  and output". Paid Services (API through a Cloud project with active billing):
  "Google doesn't use your prompts ... or responses to improve our products".
- **Retention.** Paid: prompts and responses logged "for a limited period of
  time" for abuse detection; the abuse monitoring page gives "fifty-five (55)
  days". The Interactions API, which the runner uses: "By default, the
  Interactions API enables state storage"; set `store` to `false` to avoid it.
  Grounding with Google Search (not used) stores data 30 days and restricts
  storing its results.
- **Region.** Only from an available region. In the EEA, Switzerland or UK the
  paid-data terms apply even to free use, and "You may use only Paid Services
  when making API Clients available to users" there. Disputes: California law,
  Santa Clara County courts (APIs Terms).

## What the text says: Gemini Apps (T5.1, hand-typed prompts)

- Terms: "The Google Terms of Service and the Generative AI Prohibited Use Policy
  apply to Gemini Apps." The Google Terms forbid "misleading others into
  thinking that generative AI content was created by a human", "using automated
  means to access content ... in violation of the machine-readable instructions
  on our web pages", and "using AI-generated content from our services to
  develop machine learning models or related AI technology".
- Ownership: "Google won't claim ownership over that content."
- Data: history auto-deletes after 18 months by default; chats seen by human
  reviewers "are retained for up to three years". Settings "control whether your
  data is used to train generative AI models", but "Regardless of your
  settings, Google uses your chats to respond to you and help protect Google,
  our users, and the public, including with help from human reviewers." With
  history off, chats are still "saved for around 2 months".
- Training exception: with the setting off, "Your future chats won't be used to
  train generative AI models, unless you provide feedback." If you submit
  feedback with History off, Google collects "your feedback" and "context that
  can help us better understand your feedback, including the last 24 hours of
  your chats"; reviewed feedback and associated conversations are "retained for
  up to 3 years".

## Reading (not legal advice)

- §5(e) is the largest open question across all four providers. Read literally,
  publishing generated content needs permission from the "content owner", and
  Google disclaims ownership without naming an owner. The Additional Terms
  expect sharing ("anyone you share it with") and override on conflict; §5(e)
  appears aimed at third-party content (its §5(a) is about it). Neither text
  settles the point for a public dataset.
- §5(e) also bears on storing: read literally, "build databases, or otherwise
  create permanent copies" covers keeping outputs in `data/` or `runs/` even
  before anything is published. The same ownership question decides it.
- Using unpaid quota means outputs may be read by reviewers and used for
  training. Paid use avoids this; the global constraints currently forbid paid
  calls, so the tier is a decision for the Human.
- Whether a research baseline is a "professional or business purpose" is not
  defined.
- Comparing Gemini with other models is not restricted in the text read.
- Scope differs by surface. The API rule is limited to models "that compete
  with the Services"; the Google Terms rule for Gemini Apps has no such limit
  ("to develop machine learning models or related AI technology"). It is listed
  under "Don't abuse our services". The text does not say whether running
  sibar's own tagger or scoring (T2.5, T4) on Gemini Apps outputs, or
  publishing them where others may train on them, counts as developing "related
  AI technology".
