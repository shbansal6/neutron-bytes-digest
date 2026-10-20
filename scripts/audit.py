#!/usr/bin/env python3
"""Fail a Neutron Bytes refresh when known high-materiality records disappear."""
import datetime as dt
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/"data/articles.json").read_text(encoding="utf-8"))
items=data.get("articles",[])
assert items and len(items)>=150,f"Suspicious archive contraction: {len(items)}"
seen=set()
for a in items:
    assert a.get("date") and a.get("title") and a.get("url"),"Missing required record field"
    dt.date.fromisoformat(a["date"])
    key=(a["date"],a["title"].lower().strip(),a["url"].rstrip("/"))
    assert key not in seen,"Exact duplicate event: "+a["title"]
    seen.add(key)
oct02="https://neutronbytes.com/2026/10/02/south-korea-u-s-ink-massive-nuclear-energy-plan/"
expected=[
 "US–South Korea announces eight-reactor cooperation framework",
 "Amazon and Constellation sign 20-year, 690 MW Calvert Cliffs PPA",
 "Holtec submits PSAR for two Palisades SMR-300 units",
 "General Matter files Paducah uranium enrichment licence application",
 "Raven-Flint advances Idaho uranium conversion process and NRC filing",
 "Deployable Energy selected for DOME microreactor testing in 2027",
 "NANO Nuclear agrees to acquire licensed fuel-processing assets",
 "Bipartisan US fusion bill proposes $10 billion of funding"]
found=[a for a in items if a.get("url","").rstrip("/")==oct02.rstrip("/")]
for title in expected:
    assert any(a["title"]==title for a in found),"Missing October 2 roundup story: "+title
ppa=next(a for a in found if "Amazon and Constellation sign" in a["title"])
for tag in ("Offtakes & customers","Restarts & uprates","Capital & financing"):
    assert tag in ppa.get("categories",[]),"Missing Amazon–Constellation tag: "+tag
assert "690 MW" in ppa["summary"] and "190 MW" in ppa["summary"],"Amazon PPA contracted/uprate quantities missing"
assert ppa["importance_score"]>=75,"Material PPA inappropriately downranked"
assert len([a for a in items if a["date"].startswith("2026-10")])>=20,"Recent archive unexpectedly missing substantive October sections"
print("Neutron Bytes QA PASSED:",len(items),"records;",len(found),"Oct 2 roundup stories;",
      len([a for a in items if a["date"].startswith("2026-10")]),"October stories")
