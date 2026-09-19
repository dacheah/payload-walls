# Verification

Nothing here needs to be taken on trust. Three recipes, in order of cost.

## 1. The documented-limit change (30 seconds, no key)

```bash
bash verify/check_doc_change.sh
```

It fetches the live OpenAI vision page and the 2026-03-05 Wayback capture, prints the two limit lines,
and exits 1 if either has moved. Or do it by hand:

```bash
curl -s 'http://web.archive.org/cdx/search/cdx?url=developers.openai.com/api/docs/guides/images-vision&output=json&fl=timestamp,digest'
curl -sL 'http://web.archive.org/web/20260305204402/https://developers.openai.com/api/docs/guides/images-vision' \
  | grep -oE 'Up to [0-9,]+ ?(MB|GB) [^<]{0,60}'
curl -sL 'https://developers.openai.com/api/docs/guides/images-vision' \
  | grep -oE 'Up to [0-9,]+ ?(MB|GB) [^<]{0,60}'
```

Order in the output is the whole argument: `50 MB … 500 images` on the archived page, `512 MB … 1,500
images` live, while the API still answers `400 Total image size is 50.56MB, which exceeds the allowed
limit of 50MB.`

## 2. Any documented figure in this repo (no key)

```bash
python3 - <<'PY'
import json, urllib.request, re
row = next(p for p in json.load(open("limits.json"))["providers"] if p["id"] == "fireworks")
print(row["documented"]["current"]["url"], row["documented"]["current"]["retrieved"])
PY
```

Then open that URL yourself and grep for the quoted phrase. Every `documented` block carries the URL and
the retrieval date; if the quote is no longer on the page, that row is stale and the measurement stands
on its own.

## 3. Re-measure a ceiling (needs your own key)

```bash
python3 measure/ceiling_probe.py --id myprov --url https://api.example.com/v1 --model my-model \
    --key-env MY_API_KEY --mode count --max-images 1024 --tiny-bytes 32768 --out data/probe_mine.jsonl
python3 tools/build_limits.py           # folds the new rows into limits.json + docs/table.md
python3 tools/build_limits.py --check   # CI mode: fails if the committed files no longer match data/
```

Use a small `max_tokens` and a tiny `--tiny-bytes` image: the count ladder is the cheap one. Compare the
first `FAIL` row's error text with `limits.json[provider].walls` — if the text differs, the vendor has
changed something and your row is the newer truth.

## What verification cannot establish

- **One model, one region, one key tier, one week** (2026-09-15 → 2026-09-19). A ceiling may be per-model,
  per-tier or per-region; treat every row as "this host, this key, this model, that week".
- **Free-tier and quota walls mask size walls.** A `403`/`429` is recorded as a quota wall, never as a
  size limit — see `alibaba` and `openai-codex` for rows that stopped for that reason.
- **Absence of a cap is a lower bound.** "No byte cap found" means the ladder reached the structural cap
  (count or tokens) before any byte wall. It does not mean "unlimited".
- **Absolute byte ceilings for the token-bound hosts** were not reached: the ladders stopped at the item
  and token walls. Getting past them needs a streaming client (the probe builds bodies in memory, so the
  box's RAM is the real ceiling above ~1 GB):
