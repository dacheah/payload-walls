# Measured request ceilings

Generated 2026-09-19T11:56:24+00:00 from 540 probe rows in 19 files. Do not edit by hand - run `python3 tools/build_limits.py`.

Body sizes are JSON request-body bytes. A dash means that wall was not reached - a lower
bound, not 'unlimited'. Four walls are tracked separately: whole body, one item, item count,
and the model's input-token budget.

| Provider | Host | Model tested | Largest accepted | Body wall | Image-total wall | Item wall | Count wall | Token wall | Binding constraint |
|---|---|---|---|---|---|---|---|---|---|
| `openai` | api.openai.com | gpt-4.1-mini | 129,541,440 B / 123.5 MiB (8 img) | - | 49,294,630 B / 47.0 MiB (error states 52,428,800 B) **400** | - | - | - | total_image_bytes_budget |
| `alibaba` | dashscope-intl.aliyuncs.com | qwen3.8-flash | 537,173,033 B / 512.3 MiB (96 img) | - | - | 21,244,312 B / 20.3 MiB (error states 20,971,520 B) **400** | 512 img (error states 250) **400** | - | items_per_request |
| `gemini` | generativelanguage.googleapis.com | gemini-3.5-flash-lite | 340,234,555 B / 324.5 MiB (64 img) | - | - | - | - | 1024 img **400** | input_tokens |
| `fireworks` | api.fireworks.ai | accounts/fireworks/models/kimi-k2p6 | 318,855,849 B / 304.1 MiB (30 img) | - | - | - | 61 img **400** | - | images_per_request |
| `anthropic` | api.anthropic.com | claude-haiku-4-5-20251001 | 33,452,885 B / 31.9 MiB (6 img) | 33,571,037 B / 32.0 MiB **413** | - | 10,587,865 B / 10.1 MiB **400** | - | - | body_bytes |
| `deepseek` | api.deepseek.com | deepseek-flash | 42,512,201 B / 40.5 MiB (1 img) | 50,353,869 B / 48.0 MiB **413** | - | 44,739,581 B / 42.7 MiB (error states 33,554,432 B) **400** | - | - | body_bytes |
| `zai` | api.z.ai | glm-4.5v | 201,954,077 B / 192.6 MiB (19 img) | 233,821,302 B / 223.0 MiB **400** | - | - | - | - | body_bytes |
| `kimi-coding` | api.moonshot.ai | kimi-k3 | 148,808,301 B / 141.9 MiB (14 img) | 159,405,776 B / 152.0 MiB **413** | - | - | - | - | edge_body_bytes |
| `minimax` | api.minimax.io | MiniMax-M3 | 126,880,646 B / 121.0 MiB (192 img) | 169,366,662 B / 161.5 MiB (error states 134,217,728 B) **413** | - | 21,245,198 B / 20.3 MiB (error states 10,485,760 B) **400** | - | - | body_bytes |
| `deepinfra` | api.deepinfra.com | Inkling-Small | 67,615,733 B / 64.5 MiB (text only - no image accepted) | - | - | - | 11 img (error states 8) **400** | - | images_per_request |
| `novita` | api.novita.ai | qwen3-vl-235b | 53,141,331 B / 50.7 MiB (5 img) | 95,643,543 B / 91.2 MiB **400** | - | - | - | - | body_bytes |
| `nvidia` | integrate.api.nvidia.com | meta/llama-3.2-11b-vision-instruct | 16,906,577 B / 16.1 MiB (text only - no image accepted) | 31,881,685 B / 30.4 MiB (error states 26,214,400 B) **400** | - | - | - | - | body_bytes |
| `ollama-cloud` | ollama.com | gemma4:31b | 16,721,049 B / 15.9 MiB (text only - no image accepted) | 17,251,293 B / 16.5 MiB **400** | - | - | - | - | body_bytes |
| `gmi` | api.gmi-serving.com | gemini-3.5-flash | 42,518,826 B / 40.5 MiB (text only - no image accepted) | 106,285,377 B / 101.4 MiB **413** | - | - | - | - | edge_body_bytes |
| `nebius-token-factory` | api.tokenfactory.nebius.com | google/gemma-3-27b-it | 106,228,993 B / 101.3 MiB (text only - no image accepted) | - | - | - | - | - | per_item_bytes |
| `upstage` | api.upstage.ai | solar-pro4 | 109 B / 0.0 MiB (text only - no image accepted) | - | - | - | - | - | capability |
| `xai` | api.x.ai | unmeasured | - | - | - | - | - | - | unknown |
| `openai-codex` | chatgpt.com/backend-api/codex | unmeasured | - | - | - | - | - | - | unknown |
| `copilot` | api.githubcopilot.com | unmeasured | - | - | - | - | - | - | unknown |
| `alibaba-token-plan` | token-plan.ap-southeast-1.maas.aliyuncs.com | unmeasured | - | - | - | - | - | - | unknown |

## Documented versus enforced

| Provider | Documented figure | Documented source | Measured | Delta |
|---|---|---|---|---|
| `openai` | Request size: Up to 512 MB total payload per request. Image count: Up to 1,500 images per request. | https://developers.openai.com/api/docs/guides/images-vision | 129,541,440 B / 123.5 MiB (8 img) | The current doc's 512 MB is unreachable: the API rejects at a 50 MB image-byte budget. The rule enforced today is the one the vendor deleted from this page between 2026-04-19 and 2026-04-24. See docs/findings.md. |
| `alibaba` | Requests without Base64: body max 16 MiB. Requests with Base64 (Anthropic protocol): single Base64 item max 32 MiB. Requests with Base64 (other protocols): single Base64 item max 20 MiB. Req... | https://help.aliyun.com/zh/model-studio/rate-limit | 537,173,033 B / 512.3 MiB (96 img); 250 items at item cap 20,971,520 B | Body: 512 MiB accepted against a documented 64 MiB cap and a promised HTTP 413 - the rejection actually returned HTTP 400. Per-item: 20,971,520 B enforced, matching the rate-limit page for 'other protocols' while the error-code page still says 10,485,760. The vendor's own two pages disagree. |
| `gemini` | Inline data: 100 MB per request or payload (50 MB for PDFs). File API upload: 2 GB per file, up to 20 GB per project. | https://ai.google.dev/gemini-api/docs/file-input-methods | 340,234,555 B / 324.5 MiB (64 img) | 324 MiB (340,234,555 B) accepted inline - 3.4x the documented 100 MB inline ceiling. The binding constraint at small image sizes is the 1,048,576-token input budget (~963 images at 32 KiB), not bytes; larger images carry more bytes per token, so the byte ceiling rises with image size. Documented figure is a floor, not a wall. |
| `fireworks` | 30 images maximum per request; the total base64-encoded images must be less than 10MB. | https://docs.fireworks.ai/guides/querying-vision-language-models | 318,855,849 B / 304.1 MiB (30 img); 60 items | Enforced count is 60, documented 30 (2x). Bytes: 304.1 MiB (318,855,849 B, 30 x 8 MiB) accepted against a documented 'less than 10MB' for base64 images. Count cap binds first, so the byte wall is unreachable through this endpoint. |
| `anthropic` | Request size: 32 MB for the Messages API (256 MB Batches, 500 MB Files). Per image: 10 MB base64 on the direct API (5 MB on Amazon Bedrock and Google Cloud). | https://platform.claude.com/docs/en/api/errors | 33,452,885 B / 31.9 MiB (6 img) | None - the live docs and the measurement agree exactly (32 MiB body, 10 MiB per image). Row included as a control, not as a divergence. |
| `deepseek` | Request body 48 MiB; image file size limit 32 MB; up to 600 images. | https://api-docs.deepseek.com/guides/vision | 42,512,201 B / 40.5 MiB (1 img); 600 items at item cap 33,554,432 B | None found - measurement matches the documented figures exactly on both axes (48 MiB body, 32 MiB per image). Row included as a control. |
| `zai` | No numeric request-size figure located on the vendor's error-code page. | https://docs.z.ai/api-reference/api-code | 201,954,077 B / 192.6 MiB (19 img) | The rejection is code 1214 with the size placeholder left uninterpolated: 'Request size exceeds the limit of {0}' - the vendor never states the number. Measured bracket 192.6 - 223.0 MiB. |
| `kimi-coding` | 100 MB request body (vision guide). | https://platform.moonshot.ai/docs/guide/use-kimi-vision-model | 148,808,301 B / 141.9 MiB (14 img) | 141.9 MiB accepted against a documented 100 MB ceiling. The first failure is a bare nginx 413 from the Cloudflare edge (cf-ray present, sub-second reply), so the wall measured here is the CDN tier, not necessarily the origin. |
| `minimax` | No numeric body-cap figure located; error-code page lists the 413 wording only. | https://platform.minimax.io/docs/api-reference/errorcode | 126,880,646 B / 121.0 MiB (192 img) | Exact cap measured: 413 'request body too large: 169366662 bytes exceeds limit of 134217728 bytes' = 128 MiB. Per-image 10 MiB exact. Neither number is published. |
| `deepinfra` | No numeric request-size figure located; rate-limit page documents concurrency only. | https://docs.deepinfra.com/account/rate-limits | 67,615,733 B / 64.5 MiB; 8 items | Count cap 8 binds before any byte cap (64.5 MiB accepted with a single image). At 8 large images the backend fails at the gRPC layer instead: 500 StatusCode.RESOURCE_EXHAUSTED at 202.8 MiB and 324.4 MiB - an oversize condition surfacing as a server error. |
| `novita` | Error catalogue lists INVALID_REQUEST_BODY and IMAGE_FILE_EXCEEDS_MAX_SIZE without numeric ceilings. | https://novita.ai/docs/api-reference/basic-error-code | 53,141,331 B / 50.7 MiB (5 img) | Rejection text states 'must be less than 20MB' while 50.7 MiB (53,141,331 B) was accepted - the stated figure is stale by more than 2.5x. Bracket 50.7 - 91.2 MiB. |
| `nvidia` | No numeric request-size figure located in the API reference. | https://docs.nvidia.com/nim/large-language-models/latest/reference/api-reference.html | 16,906,577 B / 16.1 MiB | Hard cap 25 MiB (26,214,400 B) inferred from the rejection text about the Assets API, with 16.9 MiB accepted and 31.9 MiB rejected. The number appears in the error, not in the docs. |
| `ollama-cloud` | No numeric payload figure located; the pricing page documents plan tiers only. | https://ollama.com/pricing | 16,721,049 B / 15.9 MiB | Wall bracketed to exactly 16 MiB (16,721,049 B accepted / 17,251,293 B rejected), 400 'failed to read request body' - not a 413. |
| `gmi` | Rate-limit page documents RPM/TPM and concurrency, no body ceiling. | https://docs.gmicloud.ai/inference-engine/api-reference/rate-limit | 42,518,826 B / 40.5 MiB | Cloudflare 503 page at 91.2 MiB, 413 at 101.4 MiB - consistent with a 100 MB CDN tier in front of the origin, not with an origin cap. Floor established at 40.5 MiB. |
| `nebius-token-factory` | No numeric payload figure located. | - | 106,228,993 B / 101.3 MiB | No body cap found to 106.3 MiB (16 x 5 MiB, 106,228,993 B). Per-image wall bracketed at 10 MiB (9.98 MiB accepted / 10.23 MiB rejected). |
| `upstage` | Images are handled by separate products (Document Parse / Document OCR / Information Extraction), not by the chat endpoint. | https://console.upstage.ai/api-keys | 109 B / 0.0 MiB | Not a size question: every chat model returns 400 'Image input is not allowed for this model' at 333,757 B. Included so the row is not mistaken for an unmeasured ceiling. |
| `xai` | Per-image limit 20 MiB documented; Batch API states 25 MB per request. No chat-body ceiling published. | https://docs.x.ai/docs/guides/chat-completions | no probe rows | UNMEASURED in this dataset - no API key on the measuring host (consumer access is OAuth). A separate session observed a 413 'length limit exceeded' at roughly 64 MiB of base64, so the practical ceiling is assumed to be the 25 MB figure and is NOT verified here. |
| `openai-codex` | No published payload ceiling for this private backend. | - | no probe rows | Unmeasured by quota, not by size: every attempt returned 429 usage_limit_reached and the window did not reopen during the measurement campaign. |
| `copilot` | No published payload ceiling. | - | no probe rows | Repeated 413 observed on screenshot-heavy sessions but no ladder was run, so no bracket is claimed here. |
| `alibaba-token-plan` | No published payload ceiling for this endpoint variant. | - | no probe rows | Not a size finding: this endpoint returned HTTP 401 invalid_request_error for a workspace key that authenticates on dashscope-intl. Recorded so the id is not mistaken for a measured row. |

## Caps resolved to a number

Rows marked *measured* were squeezed to an exact value by the probe; *documented only* are the
vendor's figure for a host this dataset did not ladder.

| Provider | Cap | Value | Basis |
|---|---|---|---|
| `alibaba` | bytes per image / data-URI item | 20,971,520 | measured |
| `alibaba` | images per request | 250 | measured |
| `gemini` | input tokens | 1,048,576 | measured |
| `fireworks` | images per request | 60 | measured |
| `anthropic` | request body bytes | 33,554,432 | measured |
| `anthropic` | bytes per image / data-URI item | 10,485,760 | measured |
| `deepseek` | request body bytes | 50,331,648 | measured |
| `deepseek` | bytes per image / data-URI item | 33,554,432 | measured |
| `deepseek` | images per request | 600 | measured |
| `minimax` | request body bytes | 134,217,728 | measured |
| `minimax` | bytes per image / data-URI item | 10,485,760 | measured |
| `deepinfra` | images per request | 8 | measured |
| `nvidia` | request body bytes | 26,214,400 | measured |
| `ollama-cloud` | request body bytes | 16,777,216 | measured |
| `nebius-token-factory` | bytes per image / data-URI item | 10,485,760 | measured |
| `xai` | bytes per image / data-URI item | 20,971,520 | documented only |

## How to read this

1. `binding_constraint` in `limits.json` names the wall a well-formed client hits first.
2. Vendor documentation is compared, not trusted - `docs/findings.md` carries the divergences.
3. Every row is one model, one region, one key tier, on one date (`measured_at`).
4. `largest_accepted` is evidence, not a ceiling: it proves the wall is above that number.
