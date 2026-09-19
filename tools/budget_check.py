#!/usr/bin/env python3
"""Pre-flight a batch against limits.json before you send it.

    python3 tools/budget_check.py --provider openai --images 24 --image-bytes 1500000
    python3 tools/budget_check.py --provider fireworks --images 61 --image-bytes 1000000
    python3 tools/budget_check.py --provider gemini --images 950 --image-bytes 32768
    python3 tools/budget_check.py --list

Hard caps (exact numbers resolved by the squeeze runs) are checked first; where only a bracket is
known, the output says so instead of pretending. Exit code 1 if any wall is predicted to reject.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LIMITS = Path(__file__).resolve().parent.parent / "limits.json"


def mib(n: int | None) -> str:
    return "-" if n is None else f"{n:,} B ({n / 1048576:.1f} MiB)"


def check(p: dict, images: int, image_bytes: int | None, body_bytes: int | None) -> tuple[list[str], bool]:
    caps = p.get("caps") or {}
    m = p.get("measured") or {}
    walls = m.get("walls") or {}
    lines, bad = [], False

    def verdict(ok: bool | None, name: str, msg: str) -> None:
        nonlocal bad
        tag = "ok   " if ok else ("NO   " if ok is False else "?    ")
        if ok is False:
            bad = True
        lines.append(f"  {name:<14} {tag} {msg}")

    # item count
    if caps.get("max_items"):
        verdict(images <= caps["max_items"], "item_count",
                f"{images} images vs cap {caps['max_items']}")
    elif walls.get("item_count"):
        w = walls["item_count"]
        verdict(None, "item_count",
                f"{images} images; first rejection observed at {w.get('images')} images "
                f"(HTTP {w['status']}) - bracket only")
    else:
        verdict(None, "item_count", f"{images} images; no count cap found on this host")

    # per item
    if image_bytes is not None and caps.get("per_item_bytes"):
        n = caps["per_item_bytes"]
        verdict(image_bytes < n, "item_bytes",
                f"{mib(image_bytes)} per image vs cap {mib(n)}")
    elif image_bytes is not None and walls.get("item_bytes"):
        verdict(None, "item_bytes", f"{mib(image_bytes)} per image; rejection observed at a comparable size")
    elif image_bytes is not None:
        verdict(None, "item_bytes", f"{mib(image_bytes)} per image; no per-item cap found")

    # image total (a budget over all images, not the body)
    total = None if image_bytes is None else image_bytes * images
    if walls.get("image_total"):
        w = walls["image_total"]
        if total is not None:
            metered = (caps.get("budget_note") or "").lower()
            if "normalis" in metered or "metered" in metered:
                verdict(False if total > w["body_bytes"] else True, "image_total",
                        f"{mib(total)} of raw image bytes; budget is metered on the vendor's own copy "
                        f"({caps.get('budget_note')}). A small-image payload was rejected at "
                        f"{w['body_bytes']:,} B of body; a larger ALL-LARGE payload passed, so a NO here "
                        f"is not final - shrink the images rather than the count")
            else:
                verdict(False if total > w["body_bytes"] else True, "image_total",
                        f"{mib(total)} of image bytes vs first rejection at {mib(w['body_bytes'])} body")

    # body
    if body_bytes is not None:
        if caps.get("body_bytes"):
            verdict(body_bytes <= caps["body_bytes"], "body", f"{mib(body_bytes)} vs cap {mib(caps['body_bytes'])}")
        elif walls.get("body"):
            verdict(False if body_bytes >= walls["body"]["body_bytes"] else True, "body",
                    f"{mib(body_bytes)} vs first rejection {mib(walls['body']['body_bytes'])}")
        else:
            verdict(None, "body", f"{mib(body_bytes)}; no body wall reached on this host")

    # tokens
    if caps.get("token_budget"):
        tip = caps.get("tokens_per_image") or {}
        per = None
        if isinstance(tip, dict):
            per = next((v for k, v in tip.items() if isinstance(v, int)), None)
        est = images * per if per else None
        verdict(None if est is None else est <= caps["token_budget"], "tokens",
                f"~{est:,} tokens at {per}/image vs budget {caps['token_budget']:,}"
                if est else f"budget {caps['token_budget']:,} tokens; per-image cost unknown for this shape")
    return lines, bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider")
    ap.add_argument("--images", type=int, default=1)
    ap.add_argument("--image-bytes", type=int, default=None, help="encoded bytes per image")
    ap.add_argument("--body-bytes", type=int, default=None, help="full JSON body size, if known")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    doc = json.loads(LIMITS.read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in doc["providers"]}
    if a.list or not a.provider:
        w = max(len(k) for k in by_id)
        for k, p in by_id.items():
            caps = p.get("caps") or {}
            bits = [f"{k2}={v:,}" for k2, v in caps.items() if isinstance(v, int)]
            print(f"{k:<{w}}  {p.get('model_tested') or 'unmeasured':<28} "
                  f"{p.get('binding_constraint') or '-':<26} {' '.join(bits)}")
        print(f"\n{len(by_id)} providers. Data measured {doc['scope']['measured_window']}; "
              f"rerun the probes before trusting a row.")
        return 0
    if a.provider not in by_id:
        sys.exit(f"unknown provider {a.provider!r}; try --list")
    p = by_id[a.provider]
    print(f"{p['id']} ({p.get('host')}, {p.get('model_tested') or 'unmeasured'}, "
          f"{p.get('binding_constraint')}): {a.images} images"
          + (f" / {mib(a.image_bytes)} each" if a.image_bytes else ""))
    lines, bad = check(p, a.images, a.image_bytes, a.body_bytes)
    print("\n".join(lines))
    doc_fig = (p.get("documented") or {}).get("current") or {}
    if doc_fig.get("text"):
        print(f"  documented:  {doc_fig['text'][:150]}")
    if p.get("confidence") and p["confidence"] != "measured":
        print(f"  confidence:  {p['confidence']} - not measured in this dataset; treat as advisory")
    print("VERDICT:", "one or more walls will reject this batch" if bad else "no wall reached")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
