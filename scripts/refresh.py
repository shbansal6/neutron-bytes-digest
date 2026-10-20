#!/usr/bin/env python3
"""Neutron Bytes public-source reconciliation and editorial-preserving refresh.

Discovery sources:
- Dated entries from Neutron Bytes Nuclear category archive, including older pages
- The publicly available Neutron Bytes RSS feed as a fallback
- Existing indexed article source URLs and independently curated entries

One roundup post can yield MANY separate topical news records. Materiality scores
determine prominence, never inclusion. No third-party or paid APIs.
"""
import datetime as dt
import email.utils
import json
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup, NavigableString
from taxonomy import enrich_record

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TODAY = dt.datetime.now(ZoneInfo("America/Chicago")).date()
START = dt.date(2020, 1, 1)
END = min(TODAY, dt.date(2026, 12, 31))
SOURCE = "Neutron Bytes"
BASE = "https://neutronbytes.com"
POST_RE = re.compile(r"^https?://(?:www\.)?neutronbytes\.com/(20\d{2})/(\d{2})/(\d{2})/[^/?#]+/?$", re.I)
COMMON = requests.Session()
COMMON.headers.update({"User-Agent": "NuclearDigestSourceIndex/1.0 (source-linked short summaries; respect Neutron Bytes)", "Accept": "text/html, application/rss+xml, application/xml"})
LIMIT_PAGES = 200  # Safety bound on archive navigation, never an article-selection cap
ARTICLE_WORKERS = 3  # Polite site load
MAX_PER_RUN = 350  # Backfill checkpoint per GitHub Actions execution; continue next week
FIRST_WEEK = dt.date(2026, 9, 7)

def normal_url(url):
    if not url:return ""
    p = urlsplit(url)
    if p.scheme not in ("https","http") or p.hostname not in ("neutronbytes.com","www.neutronbytes.com"):return ""
    fixed=urlunsplit(("https","neutronbytes.com",p.path.rstrip("/")+"/","",""))
    return fixed if POST_RE.match(fixed) else ""

def date_url(url):
    m = POST_RE.match(normal_url(url))
    if not m:return None
    try:return dt.date(*(int(m.group(i)) for i in range(1,4)))
    except ValueError:return None

def get(url):
    try:
        r=COMMON.get(url,timeout=28)
        if r.status_code==200 and r.content:
            return r.content
    except requests.RequestException:
        pass
    return b""

def short(text,maxlen=500):
    s=re.sub(r"\s+"," ",text or "").strip()
    return s if len(s)<=maxlen else s[:maxlen].rsplit(" ",1)[0].rstrip(" ,;:")+"…"

def title_norm(s):
    return re.sub(r"[^a-z0-9 ]","",str(s).lower()).strip()

def indexed_key(a):
    return (normal_url(a.get("url","")),title_norm(a.get("source_heading") or a.get("title","")))

def source_links(nodes,original):
    """Record links found within the specific news section, not sidebars."""
    links=[];seen={original.rstrip("/")}
    for a in nodes:
        href=a.get("href","").strip()
        if not href.startswith(("https://","http://")):continue
        if any(block in href.lower() for block in ("facebook.com","twitter.com","mailto:","bsky.app","linkedin.com","buymeacoffee.com")):continue
        if href.rstrip("/") in seen:continue
        label=short(a.get_text(" ",strip=True),55)
        if len(label)<3:continue
        seen.add(href.rstrip("/"));links.append({"label":label,"url":href})
        if len(links)>=3:break
    return links

def sections_from_html(body, post_url, date, post_title):
    """Treat top-level h2s as separate news sections; retain subheading content."""
    headings=body.find_all("h2")
    results=[]
    for i,h in enumerate(headings):
        name=short(h.get_text(" ",strip=True),150)
        if not (10<=len(name)<=150):continue
        if re.search(r"^(analysis|about the author|references|footnotes|sources|support|subscribe|comment|read more|like this|related)\b",name,re.I):
            continue
        parts=[];links=[]
        for sibling in h.next_elements:
            if getattr(sibling,"name",None)=="h2":break
            if getattr(sibling,"name",None)=="p":
                # Only count each paragraph once
                ptext=sibling.get_text(" ",strip=True)
                if len(ptext)>40 and ptext not in parts:parts.append(ptext)
            if getattr(sibling,"name",None)=="a" and sibling.has_attr("href"):
                links.append(sibling)
            if len(parts)>=12:break
        if not parts:continue
        desc=short(" ".join(parts[:2]),490)
        if len(desc)<70:continue
        context=" ".join(parts[:8])
        entry={"date":date.isoformat(),"title":name,"source_heading":name,
               "summary":desc,"category":"Other nuclear",
               "url":post_url,"source":SOURCE,"links":source_links(links,post_url)}
        results.append(enrich_record(entry,context))
        if len(results)>=35:break
    if not results:
        # Unsectioned standalone article: still index its main headline.
        ps=[p.get_text(" ",strip=True) for p in body.find_all("p")]
        ps=[p for p in ps if len(p)>60]
        if ps:
            entry={"date":date.isoformat(),"title":post_title,"source_heading":post_title,
                   "summary":short(" ".join(ps[:2]),490),"category":"Other nuclear",
                   "url":post_url,"source":SOURCE,"links":source_links(body.select("a[href]"),post_url)}
            results=[enrich_record(entry," ".join(ps[:8]))]
    return results

def parse_post(url):
    raw=get(url)
    if not raw:return []
    html=BeautifulSoup(raw,"html.parser")
    article=html.find("article") or html
    title_tag=article.select_one("h1.entry-title") or article.find("h1")
    title=title_tag.get_text(" ",strip=True) if title_tag else url.rstrip("/").split("/")[-1].replace("-"," ")
    content=article.select_one(".entry-content") or article.select_one(".post-content") or article
    for x in content.select("script,style,form,footer,.sharedaddy,.jp-relatedposts,.comments-area"):
        x.decompose()
    d=date_url(url)
    if not d or not (START<=d<=END):return []
    return sections_from_html(content,url,d,title)

def discover_posts():
    """Crawl the publisher's dated public archive; do not assume 10 RSS items = all posts."""
    seen=set();found=[]
    for page in range(1,LIMIT_PAGES+1):
        path="/category/nuclear/" if page==1 else f"/category/nuclear/page/{page}/"
        raw=get(BASE+path)
        if not raw:
            print("Archive page inaccessible:",path,flush=True)
            break
        soup=BeautifulSoup(raw,"html.parser")
        urls=[]
        for a in soup.select("h1.entry-title a[href],h2.entry-title a[href],article h2 a[href]"):
            u=normal_url(a.get("href",""))
            if u:urls.append(u)
        if not urls:
            # Some WordPress themes omit the entry-title CSS selector
            for a in soup.select("article a[href]"):
                u=normal_url(a.get("href",""))
                if u:urls.append(u)
        urls=list(dict.fromkeys(urls))
        if not urls:
            print("No post links in",path,flush=True);break
        new=[u for u in urls if u not in seen]
        if not new:break
        found.extend(new);seen.update(new)
        dates=[date_url(u) for u in urls if date_url(u)]
        # WordPress category pages display newest first. Include full 2020–2026.
        if dates and max(dates)<START:break
        if page%10==0:print("Archive pages:",page,"posts discovered:",len(found),flush=True)
        time.sleep(.2)
    return found

def feed_posts():
    urls=[]
    for source in [BASE+"/category/nuclear/feed/",BASE+"/feed/"]:
        raw=get(source)
        if not raw:continue
        try:
            import xml.etree.ElementTree as ET
            root=ET.fromstring(raw)
            for item in root.findall(".//item"):
                u=normal_url(item.findtext("link"))
                if u:urls.append(u)
        except ET.ParseError:pass
    return list(dict.fromkeys(urls))

def load_json(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError,UnicodeError):return default

def merge_one(existing,story):
    key=indexed_key(story)
    if key in existing:
        old=existing[key]
        # Preserve richer manually researched summaries and source links.
        if len(old.get("summary",""))<len(story.get("summary","")) and not old.get("editorial"):
            old["summary"]=story["summary"]
        old["links"]=old.get("links") or story.get("links") or []
        old["entities"]=list(dict.fromkeys((old.get("entities") or [])+(story.get("entities") or [])))
        old["technologies"]=list(dict.fromkeys((old.get("technologies") or [])+(story.get("technologies") or [])))
        old["categories"]=list(dict.fromkeys((old.get("categories") or [])+(story.get("categories") or [])))
        enrich_record(old)
        return False
    # The same roundup may be indexed under a paraphrased editorial title.
    # Require both same dated post URL and strong headline similarity before merging.
    for old_key,old in existing.items():
        if old_key[0]!=key[0]:continue
        a=title_norm(old.get("title",""));b=title_norm(story.get("title",""))
        if SequenceMatcher(None,a,b).ratio()>=.78:
            old["source_heading"]=story.get("source_heading",story["title"])
            old["entities"]=list(dict.fromkeys((old.get("entities") or [])+(story.get("entities") or [])))
            old["categories"]=list(dict.fromkeys((old.get("categories") or [])+(story.get("categories") or [])))
            enrich_record(old)
            return False
    existing[key]=story
    return True

def build_briefings(records,previous):
    week=TODAY-dt.timedelta(days=TODAY.weekday()+7)
    researched={x["week_start"]:x for x in previous if x.get("editorial") and x.get("week_start")}
    issues=[]
    while week>=FIRST_WEEK:
        end=week+dt.timedelta(days=6)
        key=week.isoformat()
        if key in researched:
            issues.append(researched[key])
        else:
            stories=[a for a in records if key<=a["date"]<=end.isoformat()]
            if stories:
                groups=defaultdict(list)
                for a in stories:
                    for cat in (a.get("categories") or ["Other developments"]):
                        groups[cat].append(a)
                sections=[{"category":cat,"takeaway":f"{len(items)} source-linked development(s) in this theme. Refer to original Neutron Bytes reporting for the detail.","items":items}
                          for cat,items in sorted(groups.items(),key=lambda x:-len(x[1]))]
                issues.append({"week_start":key,"week_end":end.isoformat(),"title":"Neutron Bytes — week of "+week.strftime("%B %d, %Y"),
                  "overview":f"{len(stories)} distinct source-linked developments found in Neutron Bytes coverage. News may appear in multiple tagged sector sections.",
                  "article_count":len(stories),"generated_at":TODAY.isoformat(),"sections":sections})
        week-=dt.timedelta(days=7)
    return issues[:7]

def main():
    if os.getenv("GITHUB_EVENT_NAME")=="schedule" and dt.datetime.now(ZoneInfo("America/Chicago")).hour!=7:
        print("Skipping redundant non-7AM daylight-saving schedule");return
    DATA.mkdir(exist_ok=True)
    archive_path=DATA/"articles.json"
    old=load_json(archive_path,{"articles":[]}).get("articles",[])
    existing={indexed_key(a):a for a in old if a.get("url") and a.get("date") and a.get("title")}
    paths=discover_posts()
    for u in feed_posts():
        if u not in paths:paths.insert(0,u)
    # Keep prior URLs in the census; removes dependence on current RSS pagination.
    old_urls=set(a["url"] for a in old if a.get("url"))
    never_before=[u for u in paths if u not in old_urls and START<=date_url(u)<=END]
    # Reprocess a rolling window of recent posts to detect NEW sub-stories or edits.
    recent=[u for u in paths if date_url(u) and date_url(u)>=TODAY-dt.timedelta(days=75)]
    todo=list(dict.fromkeys(recent+never_before))[:MAX_PER_RUN]
    print("Publisher posts:",len(paths),"new post URLs:",len(never_before),"fetching:",len(todo),flush=True)
    n=0
    with ThreadPoolExecutor(max_workers=ARTICLE_WORKERS) as pool:
        for sub in pool.map(parse_post,todo):
            for story in sub:
                if merge_one(existing,story):n+=1
    rows=list(existing.values())
    for a in rows:enrich_record(a)
    rows.sort(key=lambda x:(x["date"],x.get("importance_score",0)),reverse=True)
    archive_path.write_text(json.dumps({"updated_at":TODAY.isoformat(),
      "methodology":"Neutron Bytes dated category archive plus RSS cross-check; individual h2 news sections extracted; no article score cutoff. Subsequent runs continue unfinished 2020–2026 reconciliation.",
      "publisher_posts_discovered":len(paths),"unindexed_source_posts":max(0,len(never_before)-len(todo)),
      "articles":rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    brief_path=DATA/"briefings.json"
    weekly=build_briefings(rows,load_json(brief_path,{"briefings":[]}).get("briefings",[]))
    brief_path.write_text(json.dumps({"generated_at":TODAY.isoformat(),"briefings":weekly},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("New story records:",n,"total:",len(rows),"weekly issues:",len(weekly),flush=True)

if __name__=="__main__":main()
