# Anthropic: storing, sharing and publishing outputs

**Not legal advice.** A summary of Anthropic's published terms as fetched on
2026-11-26, for the decisions in [README.md](README.md). Models in scope:
`claude-opus-5-5`, `claude-haiku-5-5` ([models.yaml](../../models.yaml)).
Quotes are short and verbatim (typographic quotes changed to ASCII); everything
under "Reading" is interpretation.

## Documents read

| Document | Covers | Effective |
|---|---|---|
| [Commercial Terms of Service](https://www.anthropic.com/legal/commercial-terms) | API keys, Console | Jun 17, 2025 |
| [Usage Policy](https://www.anthropic.com/legal/aup) | everyone, API and apps | Nov 12, 2026 |
| [Service Specific Terms](https://www.anthropic.com/legal/service-specific-terms) | API add-ons | Aug 31, 2026 |
| [Supported Regions Policy](https://www.anthropic.com/legal/supported-regions) | everyone | Nov 12, 2026 |
| [Privacy center: organization data](https://privacy.claude.com/en/articles/7996866) | API retention | dated July 1, 2026 |
| [Consumer Terms of Service](https://www.anthropic.com/legal/consumer-terms) | Claude.ai (T5.1) | Oct 8, 2025 |
| [Privacy center: consumer data](https://privacy.claude.com/en/articles/10023548) | Claude.ai retention | dated July 1, 2026 |

## What the text says: API

- **Ownership.** Commercial Terms §B: Customer "owns its Outputs", and Anthropic
  "assigns to Customer its right, title and interest (if any) in and to Outputs".
- **Training on API data.** §B: "Anthropic may not train models on Customer
  Content from Services." The exception is opt-in: in Development Partner Mode,
  Anthropic "may use the data that Customer submits ... including to train
  models" (Service Specific Terms §E).
- **Storing, sharing, publishing.** No clause found that limits how the customer
  stores, shares or publishes Outputs. §D.3 puts the check on the customer: it
  must evaluate Outputs "before using or sharing Outputs", and tell its users
  that "factual assertions in Outputs should not be relied upon without
  independently checking their accuracy".
- **Restrictions.** §D.4: the customer may not "(a) access the Services to build
  a competing product or service, including to train competing AI models ...
  (b) reverse engineer or duplicate the Services; or (c) support any third
  party's attempt at any of the conduct restricted in this sentence." Usage
  Policy ("Do Not Abuse Our Platform"): do not "Use outputs to train an AI model
  (e.g., "model scraping" or "model distillation") without prior authorization
  from Anthropic".
- **Benchmarking or comparison.** None of the documents above mention
  benchmarking, evaluation of other models or comparative studies.
- **Attribution and disclosure.** No general duty to label published outputs as
  AI-generated was found. The Usage Policy forbids using the services to
  "Plagiarize or submit AI-assisted work without proper permission or
  attribution", and to "mislead audiences about its origin". §G (Publicity) lets
  Anthropic name the customer; nothing found limits the customer naming Claude.
- **Retention.** "For Anthropic API users, we automatically delete inputs and
  outputs on our backend within 30 days of receipt or generation", with
  exceptions (Files API, agreements, Usage Policy enforcement, law). Flagged
  content: inputs and outputs kept "for up to 2 years".
- **Region.** The contracting party is Anthropic Ireland for customers in the
  EEA, Switzerland or UK and Anthropic, PBC elsewhere; governing law is Irish or
  Californian accordingly (§M.7.a). Services are "available only in the
  countries and regions listed" in the Supported Regions Policy. The Commercial
  Terms say: "Services under these Terms are not for consumer use."

## What the text says: Claude.ai (T5.1, hand-typed prompts)

- Forbidden: "Except when you are accessing our Services via an Anthropic API Key
  ..., to access the Services through automated or non-human means, whether
  through a bot, script, or otherwise" (Consumer Terms §3). Also forbidden: "To
  crawl, scrape, or otherwise harvest data or information from our Services".
- Outputs: "we assign to you all of our right, title, and interest—if any—in
  Outputs" (§4).
- Training: Anthropic may use Materials for "training our models, unless you
  opt out of training through your account settings" (§4). If training is
  allowed, data may be kept de-identified "for up to 5 years" (consumer privacy
  article). Deleted chats leave back-end storage "within 30 days".

## Reading (not legal advice)

- Nothing read forbids publishing API or Claude.ai outputs in a public
  repository, and ownership is assigned to the user.
- The open point is §D.4(c) together with the distillation rule: a public
  dataset can be used by anyone to train models. The text does not say whether
  publishing counts as "support" for such a third party. A dataset notice or
  licence term against training would narrow this; that is a decision for the
  Human.
- Measuring defaults and comparing providers does not look like building a
  competing product or training a model. Using Claude to tag or score other
  models' outputs (T2.5, T4) is not named in any restriction.
- Typing L0 prompts by hand into Claude.ai fits the automation clause. Whether
  chats are used for training depends on the account's setting at the time.
