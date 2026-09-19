# measure/

`ceiling_probe.py` is the tool that produced `data/`. It is deliberately dependency-free (stdlib only)
so a reader can rerun it against their own key, region and model.

## The three ladders, cheapest first

```bash
pip install --no-deps .            # or just run it in place: no dependencies either way

# 1. COUNT: escalate the number of TINY images. Cheapest signal, and on most hosts the binding one.
python3 measure/ceiling_probe.py --id myprov --url https://api.example.com/v1 --model my-model \
    --key-env MY_API_KEY --mode count --max-images 1024 --tiny-bytes 32768 --out data/probe_mine.jsonl

# 2. BYTES: one image, escalating size. Finds the per-item wall (and the body wall if it lands first).
python3 measure/ceiling_probe.py --id myprov --url https://api.example.com/v1 --model my-model \
    --key-env MY_API_KEY --mode bytes --min-bytes 65536 --max-bytes 268435456 --growth 1.5

# 3. SQUEEZE: bisect between a size you know passes and one you know fails, to the exact byte.
python3 measure/ceiling_probe.py --id myprov --url https://api.example.com/v1 --model my-model \
    --key-env MY_API_KEY --mode squeeze --lo 25165824 --hi 26214400 --tolerance 1024

# sanity check first - no API calls, just prints the ladder and the body sizes
python3 measure/ceiling_probe.py --id dry --url https://x --model m --mode count --dry-run
```

`--wire openai|anthropic|gemini` picks the request shape. `--key-env NAME` reads the key from that
environment variable (never from the command line, never logged; the log stores the variable *name*).
Transport-style failures (5xx, 503, Cloudflare pages, read timeouts) get retried at 30/60/90/120 s
before they are recorded, so a CDN hiccup is not mistaken for a vendor ceiling.

## Why the images are built the way they are

`noise_png(n)` returns a **valid PNG of exactly `n` bytes**: incompressible pixel data for the bulk, then
an ancillary `prVt` chunk (lowercase first letter, so decoders ignore it) to close the last few hundred
bytes. This matters twice:

- A **truncated or zero-padded** image is rejected as an *invalid image*, which would silently corrupt a
  ladder — you would record a "cap" that is really a decoder error.
- An image whose size you cannot set exactly makes the squeeze ladder unable to resolve a cap to the byte.

Each PNG is 8-bit RGB with a filter byte per scanline; if you change the generator, re-run a ladder
against a host whose answer you already know before trusting a new one. (The first version of this
generator omitted the filter bytes and Anthropic answered `400 Could not process image` — the live ping
caught it, which is exactly why the tool ships with a ping mode.)

## Cost discipline

Tiny images, one output token, `max_tokens` small, and **count before bytes**: the count ladder answers
the question on most hosts for a fraction of the tokens, and it tells you whether a byte ladder is worth
running at all. Never blast the maximum — you learn less and pay more.

## Output

One JSON row per rung, same schema as `data/` (see `data/README.md`). Feed it to
`tools/build_limits.py` to fold a new round into `limits.json`.
