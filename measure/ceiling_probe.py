#!/usr/bin/env python3
"""Measure a provider's request-size ceilings by climbing, not guessing.

Three ladders, cheapest first:

  --mode count    escalate the NUMBER of tiny images (finds item-count and token walls)
  --mode bytes    escalate ONE image's size (finds per-item walls)
  --mode squeeze  bisect between a known-accepted and a known-rejected size (resolves an exact byte cap)
  --mode ping     one minimal request (is the key/endpoint/quota working at all?)

Every attempt appends one JSONL row: payload bytes, image count, status, the verbatim error, timing.
Nothing about your key is written - only the env var NAME is recorded.

    export MYHOST_API_KEY=...
    python3 measure/ceiling_probe.py --id myhost --url https://api.example.com/v1 \
        --model my-vision-model --key-env MYHOST_API_KEY --mode count --max-images 400 --dry-run

Why tiny images first: a failure on one huge payload cannot tell you WHICH limit you hit (body,
per-item, item count, or the model's token budget), and 2 GB costs minutes of upload per attempt.
A count ladder with 32 KiB images hits the count and token walls in seconds and costs almost nothing.

No third-party dependencies. Data and prose in this repository are CC BY 4.0
(see LICENSE-DATA).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

RETRY_STATUS = {429, 500, 502, 503, 504}   # quota/proxy: retry, do not record as a size wall
BACKOFF = (30, 60, 90, 120)


# ---------------------------------------------------------------- payload building

def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def noise_png(target_bytes: int) -> bytes:
    """A valid PNG of EXACTLY `target_bytes`.

    Random pixel data does not compress, so the encoded image tracks the raw size; the last few
    hundred bytes are an ancillary chunk (`prVt` - lowercase first letter, so decoders skip it),
    which lets the squeeze ladder land on an exact size without corrupting the image. A truncated
    or zero-padded PNG would be rejected as an invalid image and silently corrupt the ladder.
    """
    target = max(512, target_bytes)
    px = max(8, int(((target - 200) / 3) ** 0.5))
    rnd = random.Random(0xC0FFEE)
    while px > 8:
        # each PNG scanline is prefixed with a filter byte: raw = px * (3*px + 1) bytes
        raw = b"".join(b"\x00" + bytes(rnd.getrandbits(8) for _ in range(px * 3))
                       for _ in range(px))
        ihdr = struct.pack(">IIBBBBB", px, px, 8, 2, 0, 0, 0)
        base = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
                + _chunk(b"IDAT", zlib.compress(raw, 0)) + _chunk(b"IEND", b""))
        pad = target - len(base) - 12
        if pad >= 0:
            if pad:
                base = base[:-12] + _chunk(b"prVt", b"\x00" * pad) + base[-12:]
            assert len(base) == target, (len(base), target)
            return base
        px -= 1
    raise ValueError(f"cannot build a PNG of {target_bytes} bytes")


def data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def body_openai(model: str, images: list[bytes], max_tokens: int = 1) -> dict:
    content = [{"type": "text", "text": "ok"}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": data_uri(img)}})
    return {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}]}


def body_anthropic(model: str, images: list[bytes], max_tokens: int = 1) -> dict:
    content = [{"type": "text", "text": "ok"}]
    for img in images:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.b64encode(img).decode()}})
    return {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}]}


def body_gemini(model: str, images: list[bytes]) -> dict:
    parts = [{"text": "ok"}]
    for img in images:
        parts.append({"inline_data": {"mime_type": "image/png",
                                      "data": base64.b64encode(img).decode()}})
    return {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": 1}}


BUILDERS = {"openai": body_openai, "anthropic": body_anthropic, "gemini": body_gemini}


def endpoint(url: str, wire: str, model: str) -> str:
    if wire == "openai":
        return url.rstrip("/") + "/chat/completions"
    if wire == "anthropic":
        return url.rstrip("/") + "/v1/messages"
    # gemini: url is the full models/<model> path
    return url.rstrip("/") + ":generateContent"


def headers(wire: str, key: str) -> dict:
    if wire == "openai":
        return {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    if wire == "anthropic":
        return {"Content-Type": "application/json", "x-api-key": key,
                "anthropic-version": "2023-06-01"}
    return {"Content-Type": "application/json", "x-goog-api-key": key}


# ---------------------------------------------------------------- transport

def send(url: str, wire: str, key: str, body: dict, timeout: int) -> dict:
    payload = json.dumps(body).encode()
    req = urllib.request.Request(endpoint(url, wire, body.get("model", "")), data=payload,
                                 headers=headers(wire, key), method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"status": r.status, "body": r.read(4000).decode("utf-8", "replace"),
                    "elapsed_s": round(time.time() - t0, 2), "body_bytes": len(payload)}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read(4000).decode("utf-8", "replace"),
                "elapsed_s": round(time.time() - t0, 2), "body_bytes": len(payload)}
    except Exception as e:                                    # timeout, reset, DNS
        return {"status": 0, "body": f"{type(e).__name__}: {e}",
                "elapsed_s": round(time.time() - t0, 2), "body_bytes": len(payload)}


def attempt(cfg, images: list[bytes], label: str, out) -> dict:
    body = BUILDERS[cfg.wire](cfg.model, images)
    if cfg.dry_run:
        payload = json.dumps(body).encode()
        row = {"probe": cfg.id, "label": label, "model": cfg.model, "wire": cfg.wire,
               "images": len(images), "json_bytes": len(payload),
               "jpeg_bytes": sum(len(i) for i in images), "status": None,
               "dry_run": True, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        print(f"  {label:>16}  {len(images):>4} img  body {len(payload):>12,} B  (dry run)")
        return row
    for i, wait in enumerate((0,) + BACKOFF):
        if wait:
            print(f"    proxy/quota {wait}s backoff …", file=sys.stderr)
            time.sleep(wait)
        r = send(cfg.url, cfg.wire, cfg.key, body, cfg.timeout)
        if r["status"] not in RETRY_STATUS or i == len(BACKOFF):
            break
    row = {"probe": cfg.id, "label": label, "model": cfg.model, "wire": cfg.wire,
           "endpoint": endpoint(cfg.url, cfg.wire, cfg.model),
           "images": len(images), "json_bytes": r["body_bytes"],
           "jpeg_bytes": sum(len(i) for i in images), "status": r["status"],
           "elapsed_s": r["elapsed_s"], "class": classify(r["status"], r["body"]),
           "body": " ".join(r["body"].split())[:600],
           "key_env": cfg.key_env, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    out.write(json.dumps(row, ensure_ascii=False) + "\n")
    out.flush()
    flag = "ok " if r["status"] == 200 else "FAIL"
    print(f"  {label:>16}  {len(images):>4} img  body {r['body_bytes']:>12,} B  "
          f"{flag} {r['status']}  {row['class']}")
    return row


def classify(status: int, body: str) -> str:
    b = " ".join(body.split()).lower()
    if status == 200:
        return "ok"
    if status == 0:
        return "read_timeout"
    if status in (401, 402, 403):
        return "auth"
    if status == 429:
        return "quota"
    if status in (502, 503, 504):
        return "proxy"
    for cls, pats in (
        ("count_cap", ("too many images", "max data-uri per request")),
        ("image_budget", ("total image size",)),
        ("item_bytes", ("media exceeds", "image exceeds", "image size", "max bytes per data-uri")),
        ("token_cap", ("input token count", "maximum number of tokens", "context length")),
        ("body_cap", ("entity too large", "payload too large", "exceeds limit of",
                      "exceeds the limit", "body too large", "request_too_large",
                      "length limit exceeded", "must be less than", "payload is below")),
    ):
        if any(p in b for p in pats):
            return cls
    if status == 413:
        return "body_cap"
    return f"http_{status}"


# ---------------------------------------------------------------- ladders

def climb_count(cfg, out):
    """Tiny images, rising count. Finds the count wall and the token wall, cheaply."""
    img = noise_png(cfg.tiny_bytes)
    n, last_ok, steps = cfg.min_images, 0, 0
    while n <= cfg.max_images and steps < cfg.max_steps:
        steps += 1
        row = attempt(cfg, [img] * n, f"count-{n}", out)
        if row["status"] is None:                       # dry run: no verdicts, just walk the ladder
            if n >= cfg.max_images:
                return
        elif row["status"] == 200:
            last_ok = n
        else:
            if row["class"] in ("count_cap", "token_cap"):
                print(f"  -> wall between {last_ok} and {n} images ({row['class']})")
            return
        nxt = min(cfg.max_images, max(n + 1, int(n * cfg.growth)))
        if nxt <= n:
            return
        n = nxt


def climb_bytes(cfg, out):
    """One image, rising size. Finds a per-item wall (and the body wall if it hits first)."""
    size, steps, last_ok = cfg.min_bytes, 0, 0
    while size <= cfg.max_bytes and steps < cfg.max_steps:
        steps += 1
        row = attempt(cfg, [noise_png(size)], f"bytes-{size}", out)
        if row["status"] is None:                       # dry run
            if size >= cfg.max_bytes:
                return
        elif row["status"] == 200:
            last_ok = size
        else:
            print(f"  -> wall between {last_ok:,} and {size:,} B (one image, {row['class']})")
            return
        nxt = min(cfg.max_bytes, max(size + 1, int(size * cfg.growth)))
        if nxt <= size:
            return
        size = nxt


def squeeze(cfg, out):
    """Bisect one image's size between a known pass and a known fail, to the exact byte."""
    lo, hi = cfg.lo, cfg.hi
    if not (0 < lo < hi):
        sys.exit("--mode squeeze needs --lo and --hi (lo = known accepted, hi = known rejected)")
    print(f"  bisecting {lo:,} (accepted) .. {hi:,} (rejected), tolerance {cfg.tolerance} B")
    step = 0
    while hi - lo > cfg.tolerance and step < 24:
        step += 1
        mid = (lo + hi) // 2
        row = attempt(cfg, [noise_png(mid)], f"squeeze-{mid}", out)
        if row["status"] is None:                      # dry run: one rung, no verdicts to act on
            if step == 1:
                print("  (dry run: verdicts come from the API; nothing sent, nothing to bisect)")
            return
        if row["status"] == 200:
            lo = mid
        elif row["status"] is not None:
            hi = mid
    if not cfg.dry_run:
        print(f"  -> cap between {lo:,} and {hi:,} B")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, help="label for these rows (e.g. myhost)")
    ap.add_argument("--url", required=True,
                    help="base URL; for gemini pass .../v1beta/models/<model>")
    ap.add_argument("--model", required=True)
    ap.add_argument("--wire", choices=sorted(BUILDERS), default="openai")
    ap.add_argument("--key-env", default=None, help="env var holding the key (name is logged, value is not)")
    ap.add_argument("--mode", choices=("ping", "count", "bytes", "squeeze"), default="count")
    ap.add_argument("--out", default=None, help="JSONL output (default data/probe_<id>.jsonl)")
    ap.add_argument("--min-images", type=int, default=1)
    ap.add_argument("--max-images", type=int, default=1024)
    ap.add_argument("--tiny-bytes", type=int, default=32 * 1024, help="image size for the count ladder")
    ap.add_argument("--min-bytes", type=int, default=64 * 1024)
    ap.add_argument("--max-bytes", type=int, default=16 * 1024 * 1024)
    ap.add_argument("--growth", type=float, default=1.35)
    ap.add_argument("--max-steps", type=int, default=64, help="hard cap on ladder rungs")
    ap.add_argument("--lo", type=int, default=0, help="squeeze: known-accepted size")
    ap.add_argument("--hi", type=int, default=0, help="squeeze: known-rejected size")
    ap.add_argument("--tolerance", type=int, default=4096)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true", help="build bodies and print sizes; send nothing")
    cfg = ap.parse_args()

    if not cfg.dry_run:
        if not cfg.key_env:
            sys.exit("--key-env is required unless --dry-run (the value is read from the environment)")
        cfg.key = os.environ.get(cfg.key_env, "")
        if not cfg.key:
            sys.exit(f"environment variable {cfg.key_env} is empty")
    else:
        cfg.key = ""

    out_path = Path(cfg.out) if cfg.out else Path("data") / f"probe_{cfg.id}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as out:
        print(f"{cfg.id}: {cfg.mode} ladder on {cfg.url} ({cfg.wire}, model {cfg.model})"
              + (" [dry run]" if cfg.dry_run else ""))
        if cfg.mode == "ping":
            attempt(cfg, [noise_png(1024)], "ping", out)
        elif cfg.mode == "count":
            climb_count(cfg, out)
        elif cfg.mode == "bytes":
            climb_bytes(cfg, out)
        else:
            squeeze(cfg, out)
    if not cfg.dry_run:
        print(f"rows appended to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
