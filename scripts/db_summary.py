#!/usr/bin/env python3
"""Report the built product database as GitHub annotations (readable via the API)."""
import json, os, sys
d = sys.argv[1]
i = json.load(open(os.path.join(d, "index.json")))
size = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d))
largest = max(os.path.getsize(os.path.join(d, p + ".json")) for p in i["shards"])
print(f"::notice title=Product database::{i['count']:,} products: {i.get('with_figures', 0):,} with label figures, "
      f"{i.get('estimated', 0):,} estimated from their category, {i.get('name_only', 0):,} name only; "
      f"{i['with_stores']:,} with store names; {len(i['shards']):,} shards, {size/1e6:.1f} MB, largest "
      f"{largest/1e3:.0f} kB; built {i['built']}")
loc = ", ".join(f"{k} {v:,}" for k, v in i.get("local", {}).items())
rej = ", ".join(f"{k} {v:,}" for k, v in i.get("rejected", {}).items())
print(f"::notice title=Product database detail::{i.get('lines', 0):,} lines read. Slovakia/Czechia (tagged or made there): {loc}. Rejected: {rej}")
