#!/usr/bin/env python3
"""Build the app's offline barcode database from the Open Food Facts export.

Streams openfoodfacts-products.jsonl.gz (about 7 GB compressed), keeps every
product sold in a European country that carries usable per-100g nutrition,
and writes compact JSON shards keyed by barcode prefix:

    OUT/index.json      {"built", "count", "countries", "shards": [prefixes], ...}
    OUT/<prefix>.json   {"<barcode>": [name, kcal, protein, carbs, fat, stores?]}

The phone fetches index.json once and then only the one shard a scanned
barcode falls in, so the whole of Europe costs a few kilobytes per lookup.

Usage: build_off_db.py SOURCE OUT_DIR      (SOURCE is a URL or a local path)
Data: Open Food Facts contributors, Open Database License (ODbL).
"""
import gzip
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.request
from collections import Counter

try:
    import orjson
    loads = orjson.loads
except ImportError:  # still works, just slower
    loads = json.loads

# Open Food Facts country tags for Europe (both spellings where they differ).
EUROPE = [
    "slovakia", "czech-republic", "czechia", "austria", "hungary", "poland", "germany",
    "slovenia", "croatia", "romania", "bulgaria", "serbia", "bosnia-and-herzegovina",
    "montenegro", "north-macedonia", "albania", "kosovo", "greece", "cyprus", "malta",
    "italy", "san-marino", "vatican-city", "switzerland", "liechtenstein", "france",
    "monaco", "andorra", "spain", "portugal", "belgium", "netherlands", "luxembourg",
    "united-kingdom", "ireland", "denmark", "sweden", "norway", "finland", "iceland",
    "estonia", "latvia", "lithuania", "ukraine", "moldova", "belarus", "european-union",
]
EUROPE_TAGS = {"en:" + c for c in EUROPE}
COUNTRY_RE = re.compile(rb'"en:(?:' + b"|".join(re.escape(c.encode()) for c in EUROPE) + rb')"')
MAX_SHARD = int(os.environ.get("OFF_MAX_SHARD", "2500"))
MAX_DEPTH = 11  # deepest prefix length a shard can be keyed on (the app searches 11..3)
NAME_FIELDS = ["product_name_sk", "product_name_cs", "product_name", "product_name_en",
               "product_name_de", "product_name_hu", "product_name_pl"]


def num(v):
    if isinstance(v, str):
        v = v.strip().replace(",", ".")
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x >= 0 else None


def macros(n):
    """Same rules as the app: kcal, else kJ / 4.184. Reject impossible values."""
    if not isinstance(n, dict):
        return None
    kcal = num(n.get("energy-kcal_100g"))
    if kcal is None:
        kj = num(n.get("energy_100g"))
        if kj is None:
            kj = num(n.get("energy-kj_100g"))
        if kj is not None:
            kcal = kj / 4.184
    if kcal is None or kcal > 950:
        return None
    vals = [num(n.get(k)) for k in ("proteins_100g", "carbohydrates_100g", "fat_100g")]
    if all(v is None for v in vals) and kcal > 0:
        return None  # energy alone is too thin to be useful
    vals = [0.0 if v is None else v for v in vals]
    if any(v > 100 for v in vals):
        return None
    r = lambda x: round(x, 1)
    return [r(kcal), r(vals[0]), r(vals[1]), r(vals[2])]


def clean(s, limit):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s[:limit].rstrip()


def product_name(p):
    name = ""
    for f in NAME_FIELDS:
        if p.get(f) and str(p.get(f)).strip():
            name = clean(p.get(f), 80)
            break
    if not name:
        return ""
    brand = clean(str(p.get("brands") or "").split(",")[0], 40)
    if brand and brand.lower() not in name.lower():
        return brand + " — " + name
    return name


def stores_of(p):
    seen, out = set(), []
    for s in str(p.get("stores") or "").split(","):
        s = clean(s, 30)
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return ", ".join(out[:4])


def open_source(src):
    if src.startswith(("http://", "https://")):
        req = urllib.request.Request(src, headers={"User-Agent": "BlazeCookBook/1.0 (offline barcode snapshot)"})
        return gzip.GzipFile(fileobj=urllib.request.urlopen(req, timeout=120))
    return gzip.open(src, "rb")


def shard(codes, depth, out):
    groups = {}
    for c in codes:
        groups.setdefault(c[:depth], []).append(c)
    for prefix in sorted(groups):
        g = groups[prefix]
        if len(g) > MAX_SHARD and depth < MAX_DEPTH and any(len(c) > depth for c in g):
            shard(g, depth + 1, out)
        else:
            out.append((prefix, g))


def main(src, out_dir):
    t0 = time.time()
    recs, by_country, lines, with_stores = {}, Counter(), 0, 0
    with open_source(src) as fh:
        for line in fh:
            lines += 1
            if lines % 500000 == 0:
                print(f"  {lines:,} lines read, {len(recs):,} kept, {time.time() - t0:.0f}s", flush=True)
            if b"_100g" not in line or not COUNTRY_RE.search(line):
                continue
            try:
                p = loads(line)
            except Exception:
                continue
            tags = set(p.get("countries_tags") or [])
            hit = tags & EUROPE_TAGS
            if not hit:
                continue
            code = str(p.get("code") or "").strip()
            if not code.isdigit() or not 8 <= len(code) <= 14:
                continue
            m = macros(p.get("nutriments"))
            if not m:
                continue
            name = product_name(p)
            if not name:
                continue
            st = stores_of(p)
            rec = [name] + m + ([st] if st else [])
            prev = recs.get(code)
            if prev is None or (st and len(prev) < 6):
                if prev is None:
                    for t in hit:
                        by_country[t[3:]] += 1
                recs[code] = rec
    with_stores = sum(1 for r in recs.values() if len(r) > 5)
    if len(recs) < 1000:
        sys.exit(f"Only {len(recs)} products kept from {lines:,} lines - refusing to publish a broken database.")

    pieces = []
    shard(sorted(recs), 3, pieces)
    tmp = out_dir.rstrip("/") + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for prefix, codes in pieces:
        with open(os.path.join(tmp, prefix + ".json"), "w", encoding="utf-8") as f:
            json.dump({c: recs[c] for c in codes}, f, ensure_ascii=False, separators=(",", ":"))
    top = dict(by_country.most_common())
    index = {
        "built": time.strftime("%Y-%m-%d", time.gmtime()),
        "count": len(recs),
        "with_stores": with_stores,
        "countries": {k: top[k] for k in list(top)[:12]},
        "slovakia": top.get("slovakia", 0),
        "source": "Open Food Facts (openfoodfacts.org), ODbL",
        "shards": [p for p, _ in pieces],
    }
    with open(os.path.join(tmp, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    shutil.rmtree(out_dir, ignore_errors=True)
    os.replace(tmp, out_dir)  # appears only once complete
    size = sum(os.path.getsize(os.path.join(out_dir, x)) for x in os.listdir(out_dir))
    print(f"Kept {len(recs):,} European products ({with_stores:,} with store names) "
          f"from {lines:,} lines in {len(pieces):,} shards, {size / 1e6:.1f} MB, {time.time() - t0:.0f}s")
    print("By country:", ", ".join(f"{k} {v:,}" for k, v in list(top.items())[:15]))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
