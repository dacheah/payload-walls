#!/usr/bin/env bash
# Verify this repo's headline claim in one run:
#   OpenAI's vision page documented a 50 MB payload rule, was changed to 512 MB in April 2026,
#   and the API still enforces ~50 MB over the images.
#
# Checks only the DOC side (the enforcement side is in data/ and docs/findings.md).
# Exit 0 = the documented change is real and reproducible. Exit 1 = it is not; distrust the claim.
set -uo pipefail

LIVE="https://developers.openai.com/api/docs/guides/images-vision"
ARCH="http://web.archive.org/web/20260305204402/${LIVE}"
PHRASE='Up to [0-9,]+ ?(MB|GB) [^<]{0,60}'
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fetch() {
  if ! curl -sL --max-time 90 "$1" -o "$2"; then
    echo "FETCH FAILED: $1" >&2
    return 1
  fi
  [ -s "$2" ] || { echo "EMPTY RESPONSE: $1" >&2; return 1; }
}

echo "== live page =="
fetch "$LIVE" "$tmp/live.html" || exit 1
live_hits="$(grep -oE "$PHRASE" "$tmp/live.html" | sort -u)"
echo "${live_hits:-  (no 'Up to N MB' phrase found - the page may have been restructured)}"

echo
echo "== archived capture 2026-03-05 =="
fetch "$ARCH" "$tmp/arch.html" || exit 1
arch_hits="$(grep -oE "$PHRASE" "$tmp/arch.html" | sort -u)"
echo "${arch_hits:-  (no 'Up to N MB' phrase found)}"

echo
echo "== capture window (Wayback CDX, one line per changed digest) =="
curl -s --max-time 60 "http://web.archive.org/cdx/search/cdx?url=${LIVE}&output=json&limit=200&collapse=digest&fl=timestamp,statuscode" \
  | python3 -c 'import json,sys
try:
    rows=json.load(sys.stdin)
except Exception as e:
    print("  CDX unavailable:", e); raise SystemExit(0)
for ts,code in rows[1:]:
    print(f"  {ts[:4]}-{ts[4:6]}-{ts[6:8]}  {ts[8:10]}:{ts[10:12]}  HTTP {code}")'

echo
if printf '%s' "$arch_hits" | grep -q '50 MB' && printf '%s' "$live_hits" | grep -q '512 MB'; then
  echo "VERIFIED: the archived page states a 50 MB payload rule; the live page states 512 MB."
  echo "The delta between the two is the finding - see docs/findings.md section 1."
  exit 0
fi
echo "NOT VERIFIED: expected '50 MB' in the 2026-03-05 capture and '512 MB' live."
exit 1
