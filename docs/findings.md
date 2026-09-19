# Documentation versus enforcement

Every claim here is one of three things: a **quote** from a vendor page with the URL and the date it
was retrieved, a **measurement** from `data/`, or a **delta** between the two. Where a vendor page is
current and correct, it says so — a doc that matches reality is a result too.

## 1. OpenAI: the enforced rule is the one the vendor deleted

| When | What the page said |
|---|---|
| captures 2026-01-07 → 2026-03-05 (still listed 2026-04-19) | "Size limits — Up to 50 MB total payload size per request - Up to 500 individual image inputs per request" |
| captures from 2026-04-24 to today | "Request size: Up to 512 MB total payload per request. Image count: Up to 1,500 images per request." |

Primary sources: `http://web.archive.org/web/20260305204402/https://developers.openai.com/api/docs/guides/images-vision`
(quoted above) and the live page `https://developers.openai.com/api/docs/guides/images-vision`
(retrieved 2026-09-19).

**Enforcement, measured 2026-09-18 on `gpt-4.1-mini`:**

| Shape | Sent | Result |
|---|---|---|
| 17 × 2,053,887 B (many small) | body 46,556,047 B | `200` |
| 18 × 2,053,887 B | body 49,294,630 B (raw 36,969,966 B) | `400` — `Total image size is 50.56MB, which exceeds the allowed limit of 50MB.` |
| 8 × 12,144,448 B (few large) | body 129,541,440 B (raw 97,155,560 B) | `200` |
| 1 × 53,155,670 B image | body 67,622,675 B | `200` |

**Delta:** the documented 512 MB is unreachable — the API rejects at a ~50 MB budget over the images.
The figure being enforced is the one removed from this page between 2026-04-19 and 2026-04-24, and it
is metered on **OpenAI's own normalised copy** of the images, not on the bytes sent: the rejected
small-image payload was 36,969,966 B of image bytes, the accepted large-image payload was
97,155,560 B — 3.5× larger. Rejection is `400`, never `413`, so `413`-keyed recovery never fires.

Verify it in one minute: `bash verify/check_doc_change.sh` (Wayback capture + live page, diffed).

## 2. Alibaba (DashScope international): the body cap is not enforced, and their pages disagree

Documented on the rate-limit page (`https://help.aliyun.com/zh/model-studio/rate-limit`, zh-CN,
retrieved 2026-09-19):

| Rule | Documented |
|---|---|
| Requests without Base64 | body max **16 MiB** |
| With Base64 — Anthropic protocol | single Base64 item max **32 MiB** |
| With Base64 — other protocols | single Base64 item max **20 MiB** |
| With Base64 — whole body | max **64 MiB** |
| Note | after server-side decoding the whole body must still not exceed **16 MiB**; over the limit is "rejected by the gateway with HTTP 413" |

Measured on `dashscope-intl.aliyuncs.com/compatible-mode/v1`, `qwen3.8-flash`:

| Sent | Result |
|---|---|
| 96 images, body 537,173,033 B (512 MiB) | `200` |
| 200 items, body 267,075,137 B | `200` |
| 512 items, body 21,438,089 B | `400` — `Exceeded limit on max data-uri per request: 250` |
| 1 item of 21,244,312 B | `400` — `Exceeded limit on max bytes per data-uri item : 20971520` |
| 250-item rung | `403` — `The free quota has been exhausted` (free tier; the wall, not the size, stopped it) |

**Deltas:**
1. **Body: 512 MiB accepted against a documented 64 MiB cap** — 8×, and the promised `HTTP 413` was
   never observed; the size rejection that did occur came back `400`.
2. **The vendor contradicts itself.** The error-code page still quotes
   `Exceeded limit on max bytes per data-uri item : 10485760` (10 MiB) while the rate-limit page says
   20 MiB for the same protocol, and enforcement measured **20,971,520 B exactly**. The EN vision page
   separately says "the original file size must be less than 7 MB".
3. Per-item enforcement matches the rate-limit page for "other protocols" — the one documented number
   in this dataset that is exactly right.

## 3. Gemini: the documented inline limit is a floor, and the real wall is tokens

Documented: "Inline data … 100 MB per request or payload (50 MB for PDFs)"
(`https://ai.google.dev/gemini-api/docs/file-input-methods`, page last updated 2026-07-30,
retrieved 2026-09-19).

Measured on `gemini-3.5-flash-lite`:

| Sent | Result |
|---|---|
| 64 × 4 MiB, body 340,234,555 B (324 MiB) | `200` |
| 950 tiny images | `200` (1,034,558 prompt tokens) |
| 1,024 tiny images | `400` — `The input token count exceeds the maximum number of tokens allowed 1048576.` |

**Delta:** 324 MiB accepted inline, 3.4× the documented 100 MB — the doc is a floor, not a wall. The
binding constraint at small image sizes is the **1,048,576-token** input budget, costing ~1,089 tokens
per 32-KiB image (512 images → 557,576; 700 → 762,308; 900 → 980,108), i.e. ~963 tiny images before
rejection. Larger images carry more bytes per token, so the byte ceiling rises with image size: this
is why "no byte cap found" is a lower bound and not a licence to send 2 GB.

Earlier apparent ceilings on this host were a per-model quota (`429`) and transient `503 high demand`
— retried, not real walls.

## 4. Fireworks: count is double the doc, bytes are nothing like the doc

Documented: "30 images maximum" and the total base64-encoded images "must be less than 10MB"
(`https://docs.fireworks.ai/guides/querying-vision-language-models`, retrieved 2026-09-19).

Measured on `accounts/fireworks/models/kimi-k2p6`: **60 × 1 MiB accepted** (body 80,168,259 B),
**61 rejected** with `400 Too many images were provided, we currently limit the number of images per
conversation to 60`; 30 × 8 MiB (body 318,855,849 B / 304 MiB) accepted.

**Delta:** the count cap is 2× the documented figure and the byte figure is false by ~30×. The count
cap binds first, so the byte wall is unreachable through this endpoint.

Note: the 60-image rejection string was **already public** before this measurement — see
`docs/prior-art.md` (`browser-use/browsercode#127`, merged 2026-07-30). Our contribution here is the
delta against the vendor's own doc, not the discovery of the cap.

## 5. Where documentation matches enforcement

Stating these matters as much as the divergences — and one of them killed an earlier claim of ours.

| Provider | Documented | Measured | Verdict |
|---|---|---|---|
| DeepSeek | 48 MiB body; 32 MiB per image; 600 images | `413` openresty at 50,353,869 B; `400 image file size exceeds limit 32 MB` at 44,739,581 B body | matches |
| Anthropic | 32 MB Messages request; 10 MB per image | `413 request_too_large` at 33,571,037 B; per-image `400` at 10,587,865 B | matches |
| Alibaba per-item | 20 MiB (rate-limit page, other protocols) | 20,971,520 B exact | matches |
| MiniMax | (no numeric doc located) | `128 MiB` exact body, `10 MiB` exact per image | measured only |

An earlier iteration of this work accused Anthropic of understating a 100 MB limit by 2×. That was
**wrong**: the 100 MB figure belongs to the Files API, and the Messages request size documented as
32 MB is exactly what we measured. The lesson is in `docs/methods.md`: re-read the current vendor page
before calling a vendor stale.

## 6. Open questions we could not close

1. **Alibaba's three numbers for one rule** (64 MiB / 16 MiB post-decode / the actual 512 MiB
   acceptance) — unresolved without a paid account: the free quota ran out at the 250-item rung, so the
   body wall was never found, only shown to be ≥ 512 MiB.
2. **OpenAI's normalisation function.** The budget is metered on a downscaled copy; the exact
   downscale rule is not published, so a payload's fate is not computable from its raw bytes. We can
   only bound it (36,969,966 B of small images rejected; 97,155,560 B of large images accepted).
3. **`xai`, `openai-codex`, `copilot`** — not laddered (no API key / subscription usage window spent).
   Documented figures exist for xAI (20 MiB per image, 25 MB per request for Batch); unverified here.
4. **Novita** rejects with `must be less than 20MB` while accepting a 53,141,331 B body (2.5× the
   message), and its wall sits in the 50.7–91.2 MiB bracket. Untested beyond that bracket.
