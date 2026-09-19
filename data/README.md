# data/

Raw probe logs. Every number in `limits.json` and `docs/table.md` is derived from these files by
`tools/build_limits.py`; nothing is typed in by hand. **540 rows across 19 files.**

Three schemas appear here because the campaign ran in seven rounds and the logging evolved. All three
are handled by `tools/build_limits.py::norm_row`:

| File | Rows | What it is |
|---|---|---|
| `probe_results.jsonl` | 263 | rounds 1–4: byte ladders and image ladders across the first providers (`minimax`, `kimi-coding`, `zai`, `novita`, `gmi`, `nvidia`, `nebius`, `deepinfra`, `ollama-cloud`, `deepseek`, `alibaba`, `upstage`, `anthropic`, `openai_41mini`, …) |
| `probe_round5_*.jsonl` | 249 | round 5: focused ladders per provider — `gemini`, `gemini-lite`, `gemini-count`, `fireworks-60`, `fireworks-60big`, `fireworks-count`, `qwencloud`, `qwencloud-250`, `qwencloud-count`, `deepseek`, `anthropic` (+ `_refine`), `openai_41mini` |
| `probe_round5_gemini-tok.jsonl` | 16 | round 7 token ladder: image count → prompt tokens (950 images = 1,034,558 tokens) |
| `probe_round5_squeeze.jsonl` | 9 | squeeze runs that resolved exact caps (e.g. DeepSeek's 32 MiB per image) |
| `probe_openai_limits.jsonl` | 59 | round 6: OpenAI, two payload shapes plus a count ladder with tiny images |
| `probe_codex.jsonl` | 1 | the ChatGPT/Codex subscription host, which returned `429 usage_limit_reached` — recorded rather than guessed |

## Row fields

- `id` / `probe` / `label` — which ladder produced the row (`source_id` after parsing)
- `kind` — `single`, `multi-<N>`, or `ping`
- `images` — how many images were in the body
- `jpeg_bytes` / `decoded_total` / `raw_image_bytes` — raw image bytes, before base64
- `json_bytes` / `json_body` / `body_bytes` — **the measurement**: the exact JSON body length on the wire
- `status` — HTTP status, or `0` for a transport failure
- `class` — the label the probe script applied at the time; `tools/build_limits.py` recomputes the class
  for every row on every build so rounds stay comparable, and keeps the original as `stored_class`
- `body` / `error` — the verbatim response, truncated to 600 characters

## Hygiene

The logs were scrubbed before publication: the `ak-…` account id and `org-…` id that one vendor echoed
back inside an insufficient-balance error were replaced with `ak-REDACTED` / `org-REDACTED`. No API key,
token, account name or billing detail appears in this directory. Environment variable **names** appear
only in `.env.example` and in each row's `key_env` field.
