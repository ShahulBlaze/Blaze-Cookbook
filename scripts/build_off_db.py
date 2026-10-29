#!/usr/bin/env python3
"""Build the app's offline barcode database from the Open Food Facts export.

Streams openfoodfacts-products.jsonl.gz (about 7 GB compressed), keeps every
product sold in a European country that carries usable per-100g nutrition,
and writes compact JSON shards keyed by barcode prefix:

    OUT/index.json      {"built", "count", "countries", "shards": [prefixes], ...}
    OUT/<prefix>.json   {"<barcode>": [name, kcal, protein, carbs, fat, stores?, "category|n"?]}
                        (figures are null for products with neither data nor a usable category)

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


def flatten_nutrition(nut):
    """Open Food Facts' newer format keeps figures in nutrition.aggregated_set
    ({"per": "100g", "nutrients": {"proteins": {"value": 8.4, "unit": "g"}, ...}})
    and leaves the old flat `nutriments` empty. Turn it into the flat shape."""
    agg = nut.get("aggregated_set") if isinstance(nut, dict) else None
    if not isinstance(agg, dict) or str(agg.get("per") or "") not in ("100g", "100ml"):
        return None
    ns = agg.get("nutrients")
    if not isinstance(ns, dict):
        return None

    def val(name):
        e = ns.get(name)
        if not isinstance(e, dict):
            return None, ""
        v = num(e.get("value"))
        if v is None:
            v = num(e.get("value_computed"))
        return v, str(e.get("unit") or "").lower()

    def grams(name):
        v, u = val(name)
        if v is None:
            return None
        return v / 1000 if u == "mg" else v / 1e6 if u in ("\u00b5g", "ug", "mcg") else v

    kcal = None
    for name in ("energy-kcal", "energy-kj", "energy"):
        v, u = val(name)
        if v is None:
            continue
        kcal = v if (u == "kcal" or (name == "energy-kcal" and u != "kj")) else v / 4.184
        break
    out = {"energy-kcal_100g": kcal, "proteins_100g": grams("proteins"),
           "carbohydrates_100g": grams("carbohydrates"), "fat_100g": grams("fat")}
    return {k: v for k, v in out.items() if v is not None} or None


def clean(s, limit):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s[:limit].rstrip()


def product_name(p):
    name = ""
    for f in NAME_FIELDS:
        if p.get(f) and str(p.get(f)).strip():
            name = clean(p.get(f), 80)
            break
    if not name:  # any other language's name, main language first
        lc = p.get("lang") or p.get("lc")
        fields = (["product_name_" + lc] if lc else []) + sorted(k for k in p if k.startswith("product_name_"))
        for f in fields:
            v = p.get(f)
            if isinstance(v, str) and v.strip():
                name = clean(v, 80)
                break
    if not name and isinstance(p.get("generic_name"), str):
        name = clean(p["generic_name"], 80)
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


def category_label(tag):
    return re.sub(r"^[a-z]{2}:", "", tag).replace("-", " ")


def main(src, out_dir):
    t0 = time.time()
    recs = {}            # barcode -> [name, kcal, p, c, f, stores]          (figures from the label)
    pending = {}         # barcode -> (name, stores, categories)              (no figures on file)
    cat_sum = {}         # category -> [count, kcal, p, c, f]                 (to estimate the above)
    by_country, why, lines = Counter(), Counter(), 0
    local = Counter()    # Slovak/Czech-relevant outcomes, to report coverage honestly
    with open_source(src) as fh:
        for line in fh:
            lines += 1
            if lines % 500000 == 0:
                print(f"  {lines:,} lines read, {len(recs):,} with figures, {len(pending):,} without, "
                      f"{time.time() - t0:.0f}s", flush=True)
            try:
                p = loads(line)
            except Exception:
                try:
                    p = json.loads(line)   # orjson is stricter about odd escapes
                except Exception:
                    why["unparseable"] += 1
                    continue
            code = str(p.get("code") or "").strip()
            if not code.isdigit() or not 8 <= len(code) <= 14:
                why["bad barcode"] += 1
                continue
            m = macros(p.get("nutriments")) or macros(flatten_nutrition(p.get("nutrition")))
            name = product_name(p)
            if not name:
                # A barcode with label figures is still worth recognising.
                brand = clean(str(p.get("brands") or "").split(",")[0], 40)
                if not m:
                    why["no name, no figures"] += 1
                    continue
                name = (brand + " \u2014 unnamed product") if brand else "Unnamed product"
                why["kept without a name"] += 1
            tags = set(p.get("countries_tags") or [])
            sk = "en:slovakia" in tags or code.startswith("858")
            cz = "en:czech-republic" in tags or "en:czechia" in tags or code.startswith("859")
            st = stores_of(p)
            cats = [c for c in (p.get("categories_tags") or []) if isinstance(c, str)]
            if m:
                prev = recs.get(code)
                if prev is None or (st and len(prev) < 6):
                    recs[code] = [name] + m + ([st] if st else [])
                    pending.pop(code, None)
                    if prev is None:
                        for t in tags & EUROPE_TAGS:
                            by_country[t[3:]] += 1
                        if sk: local["sk with figures"] += 1
                        if cz: local["cz with figures"] += 1
                        for c in cats:
                            a = cat_sum.get(c)
                            if a is None:
                                cat_sum[c] = [1] + m
                            else:
                                a[0] += 1; a[1] += m[0]; a[2] += m[1]; a[3] += m[2]; a[4] += m[3]
            elif code not in recs:
                pending[code] = (name, st, cats)
                if sk: local["sk without figures"] += 1
                if cz: local["cz without figures"] += 1

    # Products with no figures: borrow the average of their most specific
    # category that has enough labelled products to be trustworthy.
    MIN_N, MAX_N = 20, 40000
    estimated = name_only = 0
    for code, (name, st, cats) in pending.items():
        best = None
        for c in cats:
            a = cat_sum.get(c)
            if a and MIN_N <= a[0] <= MAX_N and (best is None or a[0] <= best[1][0]):  # ties: later tags are more specific
                best = (c, a)
        if best:
            c, a = best
            n = a[0]
            est = [round(a[1] / n, 1), round(a[2] / n, 1), round(a[3] / n, 1), round(a[4] / n, 1)]
            recs[code] = [name] + est + [st, f"{category_label(c)}|{n}"]
            estimated += 1
        else:
            recs[code] = [name, None, None, None, None] + ([st] if st else [])
            name_only += 1
    with_figures = len(recs) - estimated - name_only
    with_stores = sum(1 for r in recs.values() if len(r) > 5 and r[5])
    if with_figures < 1000:
        sys.exit(f"Only {with_figures} products with figures from {lines:,} lines - refusing to publish a broken database.")
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
        "with_figures": with_figures,
        "estimated": estimated,
        "name_only": name_only,
        "with_stores": with_stores,
        "countries": {k: top[k] for k in list(top)[:12]},
        "slovakia": local["sk with figures"],
        "local": dict(local),
        "lines": lines,
        "rejected": dict(why.most_common()),
        "source": "Open Food Facts (openfoodfacts.org), ODbL",
        "shards": [p for p, _ in pieces],
    }
    with open(os.path.join(tmp, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    shutil.rmtree(out_dir, ignore_errors=True)
    os.replace(tmp, out_dir)  # appears only once complete
    size = sum(os.path.getsize(os.path.join(out_dir, x)) for x in os.listdir(out_dir))
    print(f"Kept {len(recs):,} products: {with_figures:,} with label figures, {estimated:,} estimated from "
          f"their category, {name_only:,} name only; {with_stores:,} with store names; {len(pieces):,} shards, "
          f"{size / 1e6:.1f} MB, {time.time() - t0:.0f}s")
    print("Slovak/Czech:", dict(local), "| rejected:", dict(why.most_common()))

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
