#!/usr/bin/env python3
"""Apply researched weekly editorial additions after the source collector; preserve all prior JSON and verified permalinks."""
import json,re,datetime
from pathlib import Path
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
P=DATA/"editorial_week_2026-10-19.json"
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def norm(x): return re.sub(r"[^a-z0-9]+"," ",str(x or "").lower()).strip()
def sourcekey(x): return (x["url"].rstrip("/"),norm(x.get("source_heading") or x["title"]))
def run():
 patch=load(P);ap=DATA/"articles.json";bp=DATA/"briefings.json";op=DATA/"editorial_overrides.json"
 A=load(ap);B=load(bp);O=load(op)
 old=A["articles"]; prior_count=len(old);assert prior_count>=2000
 hidden=set(O.get("hidden",[])); existing={sourcekey(a):a for a in old}
 for row in patch["articles"]:
  row=dict(row);group=row.pop("group"); key=sourcekey(row)
  if row["url"]+"::"+row["title"] in hidden:continue
  target=existing.get(key)
  if target is None:
   for a in old:
    if a["url"].rstrip("/")!=row["url"].rstrip("/"):continue
    if norm(a.get("source_heading") or a["title"])==key[1] or SequenceMatcher(None,norm(a["title"]),norm(row["title"])).ratio()>=.83:
     target=a;break
  if target is None:
   row["search_text"]=" ".join([row["title"],row["summary"],*row["entities"],*row["categories"]])
   old.append(row);existing[key]=row
  else:
   target["title"]=row["title"]
   target["links"]=row["links"]
   if not target.get("editorial"):
    target["summary"]=row["summary"];target["editorial"]=True
    target["categories"]=list(dict.fromkeys(target.get("categories",[])+row["categories"]))
    target["technologies"]=list(dict.fromkeys(target.get("technologies",[])+row["technologies"]))
    target["entities"]=list(dict.fromkeys(target.get("entities",[])+row["entities"]))
    target["links"]=target.get("links") or row["links"]
    target["importance_score"]=max(target.get("importance_score",0),row["importance_score"])
    target["search_text"]=" ".join([target["title"],target["summary"],*target["entities"],*target["categories"]])
 old.sort(key=lambda a:(a["date"],a.get("importance_score",0)),reverse=True)
 assert len(old)>=prior_count and len(old)>=2000
 unique=set()
 for a in old:
  assert a.get("date") and a.get("title") and a.get("url")
  datetime.date.fromisoformat(a["date"])
  k=(a["date"],norm(a["title"]),a["url"].rstrip("/"))
  assert k not in unique,"Duplicate "+str(k)
  unique.add(k)
 octurl="https://neutronbytes.com/2026/10/02/south-korea-u-s-ink-massive-nuclear-energy-plan/"
 amazon=next(a for a in old if a["url"].rstrip("/")==octurl.rstrip("/") and a["title"]=="Amazon and Constellation sign 20-year, 690 MW Calvert Cliffs PPA")
 assert "690 MW" in amazon["summary"] and "190 MW" in amazon["summary"]
 assert {"Offtakes & customers","Restarts & uprates","Capital & financing"}.issubset(set(amazon["categories"]))
 assert any("google" in a["title"].lower() and "constellation" in a["title"].lower() for a in old)
 # Briefing references canonical records; never create multiple items for one event.
 issues=[];used=set()
 for row in patch["articles"]:
  a=next((x for x in old if x["url"].rstrip("/")==row["url"].rstrip("/") and (norm(x.get("source_heading") or x["title"])==norm(row["source_heading"]) or norm(x["title"])==norm(row["title"]))),None)
  if not a or a["url"]+"::"+a["title"] in hidden:continue
  key=(a["url"],a["title"])
  if key in used:continue
  used.add(key);issues.append((row["group"],a))
 sections=[]
 for category,takeaway in patch["group_takeaways"].items():
  items=[a for group,a in issues if group==category]
  if items:sections.append({"category":category,"takeaway":takeaway,"items":items})
 assert len(issues)>=12,"Missing researched roundup stories"
 b={"week_start":patch["week_start"],"week_end":patch["week_end"],"title":"Neutron Bytes | Weekly Nuclear Intelligence — October 19–25, 2026","overview":patch["overview"],"article_count":len(issues),"generated_at":patch["generated_at"],"editorial":True,"sections":sections}
 B["briefings"]=sorted([b]+[x for x in B["briefings"] if x.get("week_start")!=b["week_start"]],key=lambda x:x["week_start"],reverse=True)[:7]
 assert B["briefings"][0]["editorial"] and len(B["briefings"])<=7
 A["updated_at"]=patch["generated_at"];B["generated_at"]=patch["generated_at"]
 ap.write_text(json.dumps(A,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 bp.write_text(json.dumps(B,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("Editorial merge complete",len(old),"archive entries;",len(issues),"week stories;",len(B["briefings"]),"briefings")
if __name__=="__main__":run()
