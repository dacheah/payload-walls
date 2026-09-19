# Prior art and disclosure

Four adversarial sweeps (GitHub search/code/issues, vendor docs and Wayback, social platforms and
non-English communities, academic/press/patents) were run before publishing anything here. This file
records what was already public, so nobody re-credits this repo for someone else's finding — and so a
reader can tell which parts of the table are a measurement contribution and which are corroboration.

## Already published elsewhere

| Fact | Where it was already public | What this repo adds |
|---|---|---|
| Fireworks rejects the 61st image with `Too many images were provided … 60` | `browser-use/browsercode#127`, merged 2026-07-30 (same error string verbatim) | the delta against Fireworks' own doc ("30 images maximum"), and 304 MiB accepted vs a documented "less than 10MB" |
| Alibaba enforces a 250 data-URI cap and `max bytes per data-uri item` | `attackingjensen/paper-30min#38` (measured 2026-09-07 on the same model family, raw JSONL published) and `infiniflow/ragflow#9244` (2025-08-05) | the intl-host value 20,971,520 B vs the error-code page's 10,485,760; the 512 MiB body acceptance against a documented 64 MiB cap |
| Alibaba's 20 MiB per-base64-item rule | Alibaba's own rate-limit page (`help.aliyun.com/zh/model-studio/rate-limit`) | nothing — cited as documented, and as the one documented number that is exactly right |
| Gemini accepts an inline payload beyond the documented cap | `discuss.google.dev/t/payload-size-limit/194225` — a user ran a ~100 MB base64 video; a Google-program staffer described it as "some undocumented leniency" | the measured 340,234,555 B acceptance, and the 1,048,576-token budget as the wall that actually binds |
| OpenAI's `Total image size … exceeds the allowed limit of 50MB` error and the 50 MB figure | `open-webui#26967`; an older doc revision and a Mintlify mirror still carrying "Up to 20MB per image / Up to 500 individual images / Up to 50 MB image bytes" | the dated doc change (50 MB → 512 MB between 2026-04-19 and 2026-04-24) with enforcement unmoved, and the normalised-copy metering |
| Byte limits and token limits are distinct failure modes | `sherkevin/codex-multi-model` ADR-0004 (`字节超限与 token 超限是两类故障，不得混用同一个信号`) | independent confirmation from a different measurement campaign |
| The metered unit may not be the bytes you send | `sherkevin/codex-multi-model` ADR-0009: declared 6,291,456 B cap is really 4,718,592 B, with a 5-point bisection showing the vendor meters **ASCII-escaped** bytes | a second, different instance of the same class of bug (OpenAI's normalised image copy) — worth citing together |
| Oversize is not reliably `413` | `httpwg/http-extensions#3450` ("recommend Upload-Limits in all 4xx responses"), IIS `404.14/404.15/413.1` substitution, `block/goose#11173`, vLLM `#34340`, Groq's documented `400` | a per-vendor status map (400 / 413 / 500) rather than a single instance |
| A per-item cap is not a per-body cap; hosts compose several limits | IETF `draft-ietf-httpbis-resumable-upload-10` (an `Upload-Limit` structure with max-size, min-size and max-append-size); Google Cloud Vision quotas; Databricks serving limits | measured ceilings for the composition on 16 hosts, including the token-budget wall |
| A 50-image count cap with count separated from payload explicitly | `Azure/azure-rest-api-specs#46145` (measured 2026-09-06) | a cross-provider version rather than a single-vendor one |
| A multi-provider size-limit table | `QwenPaw#7201` (documentation-derived, per media kind, no byte values) | the measured version: byte values, error strings, dates |
| Byte-versus-token and error-semantics divergence in adjacent layers | GateScope (IMC 2026), `arXiv:2605.02821`, `arXiv:2609.12770`, FailureAtlas | the payload layer specifically, measured |
| The `413` byte-layer framing in Chinese engineering blogs | juejin `7679977795864068136`, `blog.4sapi.com/blog/openai-responses-api-413-error-fix`, CSDN `163540333` | a per-provider measurement, not a self-hosted-gateway diagnosis |

**This author's own earlier slices, cited as prior art:** the NVIDIA payload error string
(`Please make sure your payload is below 26214400 bytes…`) appears publicly only in
`NousResearch/hermes-agent#112473`, filed by the author. It is listed here as self-citation so that no
reader mistakes it for independent corroboration.

## What the sweeps did not find

- No public artefact reproducing a **consolidated, measured, cross-provider payload table** with byte
  values, first-rejection error text and the binding rule per host. The closest artefacts are
  documentation-derived (QwenPaw#7201; a serverless table in `arXiv:2012.00992`).
- No publication of **OpenAI's normalised-copy metering**, or of the fact that the 512 MB figure now on
  the page is unreachable.
- No publication of Alibaba's **512 MiB acceptance against its documented 64 MiB cap**.
- Nothing at all found for the undocumented ceilings of **MiniMax (128 MiB), Novita, DeepInfra (8
  images), NVIDIA (25 MiB), Ollama Cloud, Nebius, GMI**.

"Not found" is not "novel". The sweeps could not reach Zhihu, linux.do, CSDN article bodies, V2EX,
WeChat public accounts or Discord from the test box, arXiv has no full-text search of the kind used,
and `x_search` returned fluent prose that partly restated numbers supplied in the query — so X
evidence should be treated as weak in both directions.

## Neighbouring work in progress

`attackingjensen/paper-30min` is an agent harness publishing measured multimodal request limits
(its issue #38 is titled "measured multimodal message shapes, per-request image count and size
limits"). Anyone citing this repo should read that one too, and vice versa; two independent
measurement campaigns converging is more useful than either alone.

## Not endorsed

No vendor was contacted about this work, reviewed it, or endorses it. No account identifiers, keys,
latency figures or pricing details from the test environment appear in this repository.
