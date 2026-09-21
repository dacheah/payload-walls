# payload-walls

Measured request-size **ceilings** for LLM APIs — the whole body, one image, how many images,
and the input-token budget — with each vendor's documentation checked against what the API
actually does.

Everything here was measured by sending oversized JSON bodies and reading the rejections, not by
reading docs. 20 provider rows, 540 probe requests, 2026-09-15 → 2026-09-19.

- **`limits.json`** — machine-readable: per provider, the largest accepted payload, each wall
  (body / image-total / per-item / item-count / tokens), the verbatim error, and the documented figure.
- **`docs/table.md`** — the same data as a table, generated from `limits.json`.
- **`docs/findings.md`** — the divergences between documentation and enforcement, with primary-source quotes.
- **`measure/`** — the probe tool, so you can measure your own key, region and model.
- **`data/`** — the raw logs every number in this repo is derived from.

## The walls

A payload can be rejected by any of five independent limits, and a client that only knows about one of
them misdiagnoses the others:

| Wall | Meaning | Example |
|---|---|---|
| `body` | whole request body | Anthropic 33,571,037 B → `413 request_too_large` |
| `image_total` | a budget over all images summed | OpenAI 49,294,630 B → `400 Total image size is 50.56MB, which exceeds the allowed limit of 50MB.` |
| `item_bytes` | one image / one data-URI item | Alibaba 21,244,312 B single item → `400 max bytes per data-uri item : 20971520` |
| `item_count` | how many items per request | Fireworks 61 images → `400 Too many images were provided … limit the number of images per conversation to 60` |
| `tokens` | the model's input-token budget | Gemini 1,024 tiny images → `400 The input token count exceeds the maximum number of tokens allowed 1048576` |

The counter-intuitive result: **for the hosts with the largest accepted bodies, the binding limit is
not bytes at all.** Gemini accepts 324 MiB but dies at ~963 32-KiB images because of a 1,048,576-token
budget. Fireworks accepts 304 MiB but dies at 61 images. Alibaba accepts 512 MiB but dies at 250
data-URI items. If you size a batch against a byte budget, you will be rejected by a count.

Two more things that break naive clients:

- **The metered unit is not always the bytes you send.** OpenAI's 50 MB is applied to OpenAI's own
  normalised (downscaled) copy: 18 × 2.05 MB images were rejected, while 8 × 12.1 MB — a **3.5× larger
  payload** (129,541,440 B body) — was accepted.
- **Oversize is not reliably `413`.** Measured: `400` on OpenAI, Alibaba, Z.ai, Novita, Fireworks,
  MiniMax and others; `500` on DeepInfra; `413` on Anthropic, DeepSeek, Moonshot, GMI and MiniMax's
  body wall. Recovery logic keyed on `413` will silently never fire for most of this list.

## Documented versus enforced

| Provider | Documented | Enforced (measured) | Delta |
|---|---|---|---|
| OpenAI | 512 MB payload, 1,500 images (live page) | 50 MB **image-byte budget** on the normalised copy | doc raised 10×; the enforced rule is the text the vendor deleted from that page in April 2026 |
| Alibaba (DashScope intl) | 64 MiB body, 20 MiB per base64 item, "rejected by the gateway with HTTP 413" | 512 MiB body accepted; 20,971,520 B per item exact; rejection returned **400** | body 8× the doc; 413 never seen. The vendor's error-code page says 10 MiB/item, its vision page says 7 MB |
| Gemini | 100 MB inline per request | 324 MiB accepted; 1,048,576 tokens is the real wall | doc is a floor, not a wall; the constraint is tokens |
| Fireworks | 30 images max, base64 images "less than 10MB" | 60 images; 304 MiB accepted | count 2× the doc; byte figure false |
| DeepSeek | 48 MiB body, 32 MiB per image | 48 MiB (`413`, openresty) and 32 MiB per image | matches — cite as confirmation, not novelty |
| Anthropic | 32 MB Messages request, 10 MB per image | 32 MiB body, 10 MiB per image | matches |

Full quotes and URLs: `docs/findings.md`, `limits.json` (`documented` per provider).

## Use it

**Pre-flight a batch before you send it:**

```console
$ python3 tools/budget_check.py --provider openai --images 30 --image-bytes 2053887
openai (api.openai.com, gpt-4.1-mini, total_image_bytes_budget): 30 images / 2,053,887 B (2.0 MiB) each
  item_count     ?     30 images; no count cap found on this host
  item_bytes     ?     2,053,887 B (2.0 MiB) per image; no per-item cap found
  image_total    NO    61,616,610 B (58.8 MiB) of raw image bytes; budget is metered on the vendor's own
                       copy (50 MB applied to OpenAI's own normalised (downscaled) copy of the images,
                       not to the bytes sent). A small-image payload was rejected at 49,294,630 B of body;
                       a larger ALL-LARGE payload passed, so a NO here is not final - shrink the images
                       rather than the count
  documented:  Request size: Up to 512 MB total payload per request. Image count: Up to 1,500 images per request.
VERDICT: one or more walls will reject this batch
```

`?` means no cap of that kind was established - not that the batch is safe. Exit code is 1 when any
wall is predicted to reject, so it drops straight into a pipeline.

**Pick a route by the wall that binds.** 60 images of 1 MiB each: Fireworks (cap 60) and Alibaba
(cap 250) take them; Gemini runs out of tokens near 963 small images; DeepInfra stops at 8. A 100 MB
body: Gemini, Fireworks, Alibaba, Z.ai (192 MiB), MiniMax (121 MiB), Kimi (141 MiB) and Nebius
(101 MiB) accept it; Anthropic (32 MiB), DeepSeek (48 MiB), NVIDIA (25 MiB) and Ollama Cloud (~16 MiB)
reject it.

**Classify rejections correctly.** Treat `400`/`413`/`500` with a size-ish message as oversize, and
separate a token wall from a byte wall — different remedies (downscale vs. send fewer items vs.
chunk the conversation). `limits.json` carries the verbatim error per wall so you can match on the
strings that hosts actually emit, rather than on the status code.

## Reproduce it, or extend it

```bash
cp .env.example .env      # add the provider keys you have; nothing here needs them all
python3 measure/ceiling_probe.py --help
python3 measure/ceiling_probe.py --id myhost --url https://api.example.com/v1 \
        --model some-vision-model --key-env MY_API_KEY --mode count --max-images 400 \
python3 tools/build_limits.py        # regenerate limits.json + docs/table.md
```

`measure/ceiling_probe.py` climbs a count ladder with tiny images first, then a single-image byte
ladder, then squeezes to an exact cap. Going straight at a huge payload is the trap this tool exists
to avoid: a failure at 2 GB tells you nothing about which of the four walls you hit, and costs ~100 s
of upload per attempt.

## Scope, and how these numbers go stale

- One model per provider, one region, one key tier, measured **2026-09-15 → 2026-09-19**. A paid tier
  can behave differently from a free one (Alibaba's free quota ran out mid-campaign at a 250-item rung).
- A dash/absent wall means **not reached under the other caps** — a lower bound, never "unlimited".
- `largest_accepted` is evidence, not a ceiling.
- Vendor limits move without notice. OpenAI's documented number changed twice inside five months while
  enforcement stayed put. Re-run the probe before relying on any row, and check `measured_at`.
- Three rows are unmeasured: `xai` (no API key on the test box), `openai-codex` (subscription usage
  window), `copilot` (not laddered). They are listed, not guessed.

Credential handling: no key, token or account identifier appears anywhere in this repo; the raw logs
were scrubbed of the one account id a vendor echoed back inside an error message. Only environment
variable *names* appear, in `.env.example`.

## Credit where the findings already existed

The method and the table are ours; several individual facts are not. Before quoting anything here as
new, read **`docs/prior-art.md`** — it lists what independent sources had already published
(Fireworks' 60-image cap, Alibaba's 20 MiB per-item rule, DeepSeek's documented 48/32 MiB, the
byte-versus-token failure distinction, the unreliability of `413`), including two slices filed
against Hermes by this repo's author. Vendors were not told about, and have not endorsed, any of this.

## Licence

Code MIT (`LICENSE`).

Measurement data and prose — `data/`, `limits.json`, `docs/` — CC BY 4.0
(`LICENSE-DATA`): reuse the tables, including commercially, keeping the attribution and the
`measured_at` date with them. The retrieval date is part of the attribution, not a formality —
these numbers rot.
