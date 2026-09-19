# Method

## The one rule

**Climb the cheapest ladder first, and never conclude anything from a single oversized request.**

Blasting a 2 GB payload tells you almost nothing: whichever of the four walls fires, you learn one
number — "not this" — and you cannot tell the vendor's cap from a CDN tier, a proxy, a token budget or
your own egress. The approach here was three ladders, ordered by cost:

1. **Count ladder, tiny images.** Climb the number of images with ~6–32 KiB images. Cheap in tokens,
   cheap in bytes, isolating the item-count wall and the token wall from the byte walls.
2. **Single-image byte ladder.** Climb one image's size; isolates `item_bytes`.
3. **Squeeze to exact.** Once a wall is bracketed, bisect to the byte. This is what turned
   "somewhere between 15.9 and 16.5 MiB" into "exactly 16,777,216" for MiniMax and "exactly
   20,971,520" for Alibaba's per-item cap.

Round-7 example: Fireworks' 60-image wall is invisible if you climb bytes (304 MiB passes); it appears
immediately if you climb *count* with small images. Alibaba's 250-item wall behaves the same way, and
Gemini's binding wall — 1,048,576 input tokens — is only reachable through a count ladder.

## Measurement bookkeeping

- **Unit:** JSON request-body bytes, binary units (MiB = 1024²). Sizes in this repo are the bytes on
  the wire, not the decoded image bytes; `data/` records both (`jpeg_bytes` and `json_bytes`).
- **Bracket convention:** "largest accepted – first failure". A bracket is not a cap unless a squeeze
  run resolved one.
- **`largest accepted`** = HTTP 200 with a minimal completion. A row with no reachable wall is a
  **lower bound**, never "unlimited".
- **One model, one region, one key tier, one date** per row (`measured_at`). Free and paid tiers
  differ; Alibaba's free quota expired mid-campaign at the 250-item rung.
- **Retries:** connection walls were retried at 30/60/90/120 s and classified `proxy` so a CDN 503 is
  never mistaken for a vendor ceiling. Gemini's early "caps" were per-model `429` quota and transient
  `503 high demand`; both cleared on retry and are not walls.

## Classifying a rejection

Status codes are not the contract people assume. Measured oversize rejections:

| Status | Hosts |
|---|---|
| `400` | OpenAI, Alibaba, Z.ai, Novita, Fireworks, MiniMax (item), DeepSeek (item), NVIDIA, Ollama Cloud, Nebius |
| `413` | Anthropic, DeepSeek (body), Moonshot/Kimi, GMI, MiniMax (body) |
| `500` | DeepInfra (`RESOURCE_EXHAUSTED`) |

Consequences worth designing for:

- Recovery logic keyed on `413` never fires on more than half of this list.
- Z.ai's oversize rejection reuses a generic invalid-parameter code (`1214`) with an uninterpolated
  `{0}` placeholder in the message — the error text cannot be parsed for the limit.
- A **token** wall and a **byte** wall need different remedies (send fewer items / downscale images /
  chunk the conversation), so they must be separate classes. Deployments that retry a token-wall
  failure with backoff burn quota forever.

The classifier lives in `tools/build_limits.py::classify` and is applied to every historical row on
every build, so rounds measured with an earlier, weaker list stay comparable.

## What went wrong, and the lessons

1. **In-memory payload building caps out around 1 GB.** Images + base64 + JSON ≈ 2.2× the body size in
   RAM, and the test box had 2.8 GB free. Absolute byte ceilings for the three largest hosts need a
   streaming client (build the base64 on disk, POST the file) — noted as future work, not guessed at.
2. **Egress is a real cost:** ~21 MB/s from the test box, so a 2 GB rung costs ~100 s of upload. The
   ladders were run as parallel background probes with per-target JSONL, so a single timeout did not
   lose a round.
3. **Probe two payload shapes for total-based budgets.** OpenAI's 50 MB budget looks like a per-image
   or per-count rule if you only climb one shape: many-small images are rejected *earlier* than a
   3.5×-larger few-large payload, because the budget is metered on a downscaled copy of each image.
4. **Re-read the current vendor page before calling a vendor stale.** An early claim that Anthropic's
   docs were wrong by 2× was false — the 100 MB figure belongs to the Files API, and 32 MB for Messages
   is exactly right. It was corrected before publication.
5. **Do not trust your own tooling's summary.** A helper reported success from a provider that had
   silently fallen back to a different provider; the provider id in the response is the evidence, not
   the presence of an answer.

## Reproducing

```bash
cp .env.example .env                       # keys you actually have; none are required to read the data
python3 measure/ceiling_probe.py --id myhost --url https://api.example.com/v1 \
        --model my-vision-model --api-key-env MYHOST_API_KEY --mode count --max-images 400
python3 tools/build_limits.py              # regenerate limits.json and docs/table.md from data/
python3 tools/build_limits.py --check      # CI-style staleness check
```

`measure/ceiling_probe.py` writes one JSONL row per request (payload bytes, image count, status,
verbatim error, timestamp). Point it at a different region or tier and the same four walls will
usually appear at different values — which is the point of measuring rather than citing.
