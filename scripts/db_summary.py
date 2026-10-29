#!/usr/bin/env python3
"""Report the built product database as a GitHub annotation (readable via the API)."""
import json, os, sys
d = sys.argv[1]
i = json.load(open(os.path.join(d, "index.json")))
size = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d))
largest = max(os.path.getsize(os.path.join(d, p + ".json")) for p in i["shards"])
top = ", ".join(f"{k} {v:,}" for k, v in list(i["countries"].items())[:10])
print(f"::notice title=Product database::{i['count']:,} European products ({i['slovakia']:,} sold in Slovakia, "
      f"{i['with_stores']:,} with store names) in {len(i['shards']):,} shards, {size/1e6:.1f} MB, largest shard "
      f"{largest/1e3:.0f} kB, built {i['built']}. Top countries: {top}")
if "lines" in i:
    rej = ", ".join(f"{k} {v:,}" for k, v in i.get("rejected", {}).items())
    seen = ", ".join(f"{k} {v:,}" for k, v in i.get("seen", {}).items())
    print(f"::notice title=Product database detail::{i['lines']:,} lines read. Rejected: {rej}. European products seen before quality filters: {seen}")
if i.get("probe"):
    pr = i["probe"]
    print("::notice title=Product database probe A::types " + json.dumps(pr["nutriments_type"]) + " | nutriment keys " + json.dumps(pr["nutri_keys"]) + " | top-level keys " + json.dumps(pr["top_keys"]))
    for n, smp in enumerate(pr["samples"]):
        print(f"::notice title=Product database probe S{n}::" + json.dumps(smp, ensure_ascii=False))
