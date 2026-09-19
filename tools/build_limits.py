#!/usr/bin/env python3
"""Build limits.json (and docs/table.md) from the raw probe logs.

Measured fields are DERIVED from data/*.jsonl on every run - never typed by hand.
Documented figures, the exact caps resolved by the squeeze runs, and the prose come
from tools/providers_overlay.json, which is the only file a human edits.

Four kinds of wall are tracked separately, because collapsing them is the mistake
this dataset exists to document:
    body        - the whole request body
    item_bytes  - one image / one data-URI item
    item_count  - how many items may appear in one request
    tokens      - the model's input-token budget
A row may carry any subset. A missing wall means "not reached under the other caps",
which is a lower bound, never "unlimited".

Usage:  python3 tools/build_limits.py            # writes limits.json + docs/table.md
        python3 tools/build_limits.py --check     # exit 1 if limits.json is stale
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OVERLAY = ROOT / "tools" / "providers_overlay.json"
OUT_JSON = ROOT / "limits.json"
OUT_TABLE = ROOT / "docs" / "table.md"

WALL_CLASSES = ("body_cap", "image_total_cap", "item_bytes_cap", "item_count_cap", "token_cap")

WALL_KEYS = {"body_cap": "body", "image_total_cap": "image_total", "item_bytes_cap": "item_bytes",
             "item_count_cap": "item_count", "token_cap": "tokens"}


def classify(status: int, body: str) -> str:
    """Classify a rejection. Recomputed for every row so all rounds compare like-for-like.

    The probe scripts carried a weaker list as the campaign went on; their stored label is
    kept in the output as `stored_class` for traceability but is not trusted here.
    """
    if status == 200:
        return "ok"
    b = " ".join((body or "").split()).lower()
    if status == 0:
        return "read_timeout"
    if status in (401, 402, 403):
        return "auth"
    if status == 429:
        return "rate_limit"
    if status in (502, 503, 504):
        return "proxy"
    if "not allowed for this model" in b or "does not accept image" in b:
        return "capability"
    if "total image size" in b:            # OpenAI meters a budget over the whole image set
        return "image_total_cap"
    if "too many images" in b or "max data-uri per request" in b:
        return "item_count_cap"
    if any(s in b for s in (
            "media exceeds", "image exceeds", "image size", "max bytes per data-uri",
            "string value length", "maximum length", "image file size")):
        return "item_bytes_cap"
    if any(s in b for s in (
            "payload too large", "request entity too large", "length limit exceeded",
            "exceeds limit of", "exceeds the limit", "exceeds the allowed limit",
            "body too large", "request_too_large", "must be less than",
            "failed to read request body", "payload is below", "request size exceeds",
            "size exceeds the limit")):
        return "body_cap"
    if status == 413:
        return "body_cap"
    if any(s in b for s in ("context window", "context length", "too many tokens",
                            "input length", "input token count", "token count exceeds",
                            "maximum number of tokens")):
        return "token_cap"
    if status in (400, 404, 405, 410, 422):
        return "client_error"
    return f"http_{status}"


def norm_row(r: dict) -> dict | None:
    """Fold the three log schemas used across the campaign into one shape."""
    sid = r.get("id") or r.get("probe") or r.get("label")
    if not sid:
        return None
    payload = r.get("json_bytes", r.get("json_body", r.get("body_bytes")))
    if payload is None:
        return None
    body = r.get("body") or r.get("error") or ""
    status = int(r.get("status") or 0)
    images = r.get("images")
    if images is None:
        kind = str(r.get("kind") or "")
        m = re.match(r"multi-(\d+)$", kind)
        if m:
            images = int(m.group(1))
        elif kind == "ping":
            images = 0
        elif kind == "single":
            images = 1
    raw = (r.get("jpeg_bytes") or r.get("decoded_total") or r.get("raw_image_bytes")
           or (r.get("per_image_bytes") or 0) * (images or 0))
    return {
        "source_id": sid,
        "model": r.get("model"),
        "images": images,
        "payload_bytes": int(payload),
        "image_raw_bytes": int(raw or 0),
        "status": status,
        "class": classify(status, body),
        "stored_class": r.get("class") or r.get("cls"),
        "error": " ".join(body.split())[:400],
    }


def load_rows() -> list[dict]:
    rows = []
    for path in sorted(glob.glob(str(DATA / "*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            n = norm_row(rec)
            if n:
                n["file"] = Path(path).name
                rows.append(n)
    return rows


CAP_PATTERNS = (
    (r"max bytes per data-uri item\s*:\s*([\d,]+)", 1),
    (r"max data-uri per request\s*:\s*([\d,]+)", 1),
    (r"exceeds size limit:\s*max\s*([\d,]+)\s*bytes", 1),
    (r"media exceeds[^0-9]{0,30}max\s*([\d,]+)\s*bytes", 1),
    (r"below\s*([\d,]+)\s*bytes", 1),
    (r"exceeds limit of\s*([\d,]+)\s*(?:bytes)?", 1),
    (r"exceeds the limit of\s*\{?([\d,]+)", 1),
    (r"image file size exceeds limit\s*([\d.]+)\s*MB", 1048576),
    (r"allowed limit of\s*([\d.]+)\s*MB", 1048576),
    (r"limit\s*\.{0,3}\s*to\s*([\d,]+)", 1),
    (r"Too many images[^0-9]{0,30}[\d,]+\s*>\s*([\d,]+)", 1),
    (r"maximum allowed\s*\(([\d,]+),", 1),
)


def cap_from_text(text: str) -> int | None:
    """Recover the numeric ceiling a vendor's own error message states, when it states one.

    Several of these messages contain an uninterpolated placeholder (`{0}`) or no number at all;
    those return None rather than a guess.
    """
    if not text:
        return None
    for pat, mult in CAP_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return int(float(m.group(1).replace(",", ""))) * mult
            except ValueError:
                continue
    return None


def slim(r: dict | None, *, count_wall: bool = False) -> dict | None:
    if not r:
        return None
    err = r["error"]
    out = {"status": r["status"], "class": r["class"],
           "error": (err[:240] + ("..." if len(err) > 240 else ""))}
    cap = cap_from_text(err)
    if cap and r["class"] in ("body_cap", "item_bytes_cap", "item_count_cap", "image_total_cap"):
        out["cap_stated_in_error"] = cap
    if not count_wall:
        out = {"body_bytes": r["payload_bytes"], **out}
    if r.get("images") is not None:
        out["images"] = r["images"]
    if r.get("model"):
        out["model"] = r["model"]
    return out


def aggregate(rows: list[dict]) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for r in rows:
        a = by_id.setdefault(r["source_id"], {
            "rows": 0, "files": set(), "accepted": [], "walls": {}, "other_failures": {},
        })
        a["rows"] += 1
        a["files"].add(r["file"])
        if r["class"] == "ok":
            a["accepted"].append(r)
        elif r["class"] in WALL_CLASSES:
            cur = a["walls"].get(r["class"])
            if r["class"] == "item_count_cap":
                better = cur is None or (r.get("images") or 0) < (cur.get("images") or 0)
            else:
                better = cur is None or r["payload_bytes"] < cur["payload_bytes"]
            if better:
                a["walls"][r["class"]] = r
        else:
            a["other_failures"][r["class"]] = a["other_failures"].get(r["class"], 0) + 1

    for a in by_id.values():
        acc = [r for r in a["accepted"] if r["payload_bytes"] > 0]
        with_img = [r for r in acc if (r["images"] or 0) > 0]
        # a text-only control request is not a vision ceiling: only fall back to it if the ladder
        # never sent an image at all (e.g. a capability-gap row)
        pool = with_img or acc
        a["largest_accepted"] = max(pool, key=lambda r: r["payload_bytes"]) if pool else None
        if not with_img:
            a["no_image_accepted"] = True
        a["most_images_accepted"] = max(pool, key=lambda r: (r["images"] or 0)) if pool else None
        a["files"] = sorted(a["files"])
    return by_id


def build() -> dict:
    rows = load_rows()
    agg = aggregate(rows)
    overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
    mapped = {s for p in overlay["providers"] for s in p["source_ids"]}
    unmapped = sorted(set(agg) - mapped)

    providers = []
    for p in overlay["providers"]:
        entry = {k: v for k, v in p.items() if k != "source_ids"}
        walls: dict[str, dict] = {}
        accepted: dict | None = None
        ev = []
        for sid in p["source_ids"]:
            a = agg.get(sid)
            if not a:
                continue
            ev.append({
                "source_id": sid,
                "rows": a["rows"],
                "files": a["files"],
                "largest_accepted": slim(a["largest_accepted"]),
                "most_images_accepted": slim(a["most_images_accepted"]),
                "walls": {k: slim(v, count_wall=(k == "item_count_cap"))
                          for k, v in sorted(a["walls"].items())},
                "non_wall_failures": a["other_failures"],
            })
            for k, v in a["walls"].items():
                cur = walls.get(k)
                if k == "item_count_cap":
                    if cur is None or (v.get("images") or 0) < (cur.get("images") or 0):
                        walls[k] = v
                elif cur is None or v["payload_bytes"] < cur["payload_bytes"]:
                    walls[k] = v
            if a["largest_accepted"] and (
                    accepted is None
                    or a["largest_accepted"]["payload_bytes"] > accepted["payload_bytes"]):
                accepted = a["largest_accepted"]

        entry["measured"] = {
            "largest_accepted": slim(accepted),
            "walls": {WALL_KEYS[k]: slim(v, count_wall=(k == "item_count_cap"))
                      for k, v in sorted(walls.items())},
        }
        entry["evidence"] = ev or [{"note": "no probe rows present in data/ for this provider"}]
        providers.append(entry)

    return {
        "schema_version": "1.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "scope": overlay["scope"],
        "conventions": {
            "size_unit": "JSON request-body bytes, reported in binary MiB (1 MiB = 1,048,576 B)",
            "measured_field": "measured.largest_accepted.body_bytes is HTTP 200 evidence; "
                              "measured.walls.<wall>.body_bytes is the first rejection of that kind",
            "bracket": "largest accepted - first failure; only exact where the squeeze run resolved it",
            "no_cap_means": "the ladder reached a structural cap (item count, token budget) before any "
                            "byte wall, so the byte ceiling is a LOWER BOUND, never 'unlimited'",
            "cap_stated_in_error": "the number the vendor's own error message asserted, when it asserts one",
        },
        "row_count": len(rows),
        "data_files": sorted({r["file"] for r in rows}),
        "generated_from": sorted({r["file"] for r in rows}),
        "providers": providers,
        "unmapped_source_ids": unmapped,
    }


def _has_rows(p: dict) -> bool:
    return any(isinstance(e, dict) and "source_id" in e for e in (p.get("evidence") or []))


def fmt(b: int | None) -> str:
    return "-" if b is None else f"{b:,} B / {b / 1048576:.1f} MiB"


def table(doc: dict) -> str:
    strip = lambda s, n=190: (s.replace("|", "\\|")[:n] + ("..." if len(s) > n else "")) \
        if isinstance(s, str) else "-"
    out = [
        "# Measured request ceilings",
        "",
        f"Generated {doc['generated_at']} from {doc['row_count']} probe rows in "
        f"{len(doc['data_files'])} files. Do not edit by hand - run `python3 tools/build_limits.py`.",
        "",
        "Body sizes are JSON request-body bytes. A dash means that wall was not reached - a lower",
        "bound, not 'unlimited'. Four walls are tracked separately: whole body, one item, item count,",
        "and the model's input-token budget.",
        "",
        "| Provider | Host | Model tested | Largest accepted | Body wall | Image-total wall | Item wall | Count wall | Token wall | Binding constraint |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in doc["providers"]:
        m = p["measured"]
        w = m["walls"]
        acc = m["largest_accepted"]
        acc_s = "-" if not acc else (fmt(acc["body_bytes"]) +
                                     (f" ({acc['images']} img)" if acc.get("images") else ""))
        if acc and not acc.get("images"):
            acc_s = f"{fmt(acc['body_bytes'])} (text only - no image accepted)"
        def cell(key, byte_key="body_bytes"):
            x = w.get(key)
            if not x:
                return "-"
            val = f"{x.get(byte_key)} img" if byte_key == "images" else fmt(x.get(byte_key))
            cap = x.get("cap_stated_in_error")
            if cap and cap != x.get(byte_key):
                val += (f" (error states {cap:,})" if byte_key == "images"
                        else f" (error states {cap:,} B)")
            return f"{val} **{x['status']}**"
        out.append("| `{}` | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            p["id"], p.get("host") or "-", p.get("model_tested") or "unmeasured",
            acc_s, cell("body"), cell("image_total"), cell("item_bytes"),
            cell("item_count", "images"), cell("tokens", "images"),
            p.get("binding_constraint") or "-"))
    out += [
        "",
        "## Documented versus enforced",
        "",
        "| Provider | Documented figure | Documented source | Measured | Delta |",
        "|---|---|---|---|---|",
    ]
    for p in doc["providers"]:
        d = p.get("documented") or {}
        cur = d.get("current") or {}
        if not cur.get("text"):
            continue
        m = p["measured"]
        acc = m["largest_accepted"]
        meas = "no probe rows"
        if acc:
            meas = fmt(acc["body_bytes"])
            if acc.get("images"):
                meas += f" ({acc['images']} img)"
        caps = p.get("caps") or {}
        if caps.get("max_items"):
            pi = caps.get("per_item_bytes")
            meas += f"; {caps['max_items']} items"
            if pi:
                meas += f" at item cap {pi:,} B"
        out.append("| `{}` | {} | {} | {} | {} |".format(
            p["id"], strip(cur["text"]), strip(cur.get("url") or "-", 120),
            meas, strip(d.get("delta") or "-", 400)))
    out += [
        "",
        "## Caps resolved to a number",
        "",
        "Rows marked *measured* were squeezed to an exact value by the probe; *documented only* are the",
        "vendor's figure for a host this dataset did not ladder.",
        "",
        "| Provider | Cap | Value | Basis |",
        "|---|---|---|---|",
    ]
    label = {"body_bytes": "request body bytes", "per_item_bytes": "bytes per image / data-URI item",
             "max_items": "images per request", "token_budget": "input tokens"}
    for p in doc["providers"]:
        basis = "measured" if _has_rows(p) else "documented only"
        for k, v in (p.get("caps") or {}).items():
            if k in label and v:
                out.append(f"| `{p['id']}` | {label[k]} | {v:,} | {basis} |")
    out += [
        "",
        "## How to read this",
        "",
        "1. `binding_constraint` in `limits.json` names the wall a well-formed client hits first.",
        "2. Vendor documentation is compared, not trusted - `docs/findings.md` carries the divergences.",
        "3. Every row is one model, one region, one key tier, on one date (`measured_at`).",
        "4. `largest_accepted` is evidence, not a ceiling: it proves the wall is above that number.",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if limits.json is stale")
    a = ap.parse_args()
    doc = build()
    new_json = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if a.check:
        old = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.exists() else {}
        old.pop("generated_at", None)
        fresh = json.loads(new_json)
        fresh.pop("generated_at", None)
        if old != fresh:
            print("limits.json is stale - rerun tools/build_limits.py", file=sys.stderr)
            return 1
        print("limits.json is current")
        return 0
    OUT_JSON.write_text(new_json, encoding="utf-8")
    OUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
    OUT_TABLE.write_text(table(doc), encoding="utf-8")
    print(f"wrote {OUT_JSON.name} ({len(doc['providers'])} providers, {doc['row_count']} rows) "
          f"and {OUT_TABLE.relative_to(ROOT)}")
    if doc["unmapped_source_ids"]:
        print("WARNING unmapped source ids:", doc["unmapped_source_ids"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
