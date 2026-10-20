#!/usr/bin/env python3
"""Neutron Bytes public feed → source-linked archive and weekly briefing.
Uses no API key. It never copies an entire Neutron Bytes story.
"""
import datetime as dt
import email.utils
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from taxonomy import enrich_record

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
TODAY=dt.datetime.now(ZoneInfo('America/Chicago')).date()
FEEDS=[
 'https://neutronbytes.com/category/nuclear/feed/',
 'https://neutronbytes.com/feed/'
]
HEADERS={'User-Agent':'NeutronBytesResearchArchive/1.0 (public-source reading and attribution)'}
WEEK_START=dt.date(2026,9,7)
SOURCE='Neutron Bytes'

def get(url):
    try:
        r=requests.get(url,headers=HEADERS,timeout=30)
        return r.content if r.status_code==200 else b''
    except requests.RequestException:
        return b''

def slim(text,limit=490):
    s=re.sub(r'\s+',' ',text or '').strip()
    return s if len(s)<=limit else s[:limit].rsplit(' ',1)[0].rstrip(' ,;:')+'…'

def source_links(node, post_url):
    out=[];seen={post_url}
    for a in node.select('a[href]'):
        raw=a.get('href','').strip()
        if not raw.startswith('http'):continue
        if not raw.startswith(('http://','https://')):continue
        if raw in seen:continue
        if any(word in raw.lower() for word in ('twitter.com','facebook.com','share?','mailto:','neutronbytes.com/category/')):continue
        txt=a.get_text(' ',strip=True) or raw.split('/')[2]
        if len(txt)<3:continue
        seen.add(raw);out.append({'label':slim(txt,45),'url':raw})
        if len(out)>=3:break
    return out

def records_from_item(item):
    title=(item.findtext('title') or '').strip()
    link=(item.findtext('link') or '').strip()
    date_raw=item.findtext('pubDate')
    try: date=email.utils.parsedate_to_datetime(date_raw).date()
    except (ValueError,TypeError):return []
    if not (dt.date(2020,1,1)<=date<=TODAY):return []
    if not link.startswith('https://neutronbytes.com/') or not title:return []
    text=item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or item.findtext('description') or ''
    soup=BeautifulSoup(text,'html.parser')
    # Gather individual WNN-like headlines from a newsletter post, so one bundled
    # NB post can generate separate tagged developments with the correct post URL.
    body=soup.find('div',class_='entry-content') or soup
    for junk in body.select('script,style,iframe,form,figure,figcaption'):junk.decompose()
    headings=body.find_all(['h2','h3'])
    sections=[]
    if headings:
        # Reduce feed articles to substantive h2/h3 sections only, retaining one
        # entry per specific event and excluding generic sidebar/footnote headings.
        for h in headings:
            heading=slim(h.get_text(' ',strip=True),145)
            if not (9<=len(heading)<=145):continue
            if re.search(r'^(?:references|related|notes|contact|updated|sponsors|support|subscription|about the author|click here)\b',heading,re.I):continue
            chunks=[]; links=[]
            for node in h.next_elements:
                if getattr(node,'name',None) in ('h2','h3'):break
                if getattr(node,'name',None)=='p':
                    s=node.get_text(' ',strip=True)
                    if len(s)>=32:chunks.append(s)
                    if len(chunks)>=6:break
                if getattr(node,'name',None)=='a' and node.has_attr('href'):
                    links.append(node)
            desc=slim(' '.join(chunks),490)
            if len(desc)<65:continue
            # Only hyperlinks in the headline's own content block.
            wrapper=BeautifulSoup(''.join(str(x) for x in links[:25]),'html.parser')
            sections.append((heading,desc,source_links(wrapper,link),' '.join(chunks)))
            if len(sections)>=25:break
    if not sections:
        paras=[p.get_text(' ',strip=True) for p in body.find_all('p')]
        paras=[p for p in paras if len(p)>40]
        summary=slim(' '.join(paras[:3]),490)
        if len(summary)>65:
            sections=[(title,summary,source_links(body,link),' '.join(paras[:8]))]
    out=[];seen=set()
    for heading,description,links,bodytext in sections:
        key=heading.casefold()
        if key in seen:continue
        seen.add(key)
        rec={'date':date.isoformat(),'title':heading,'summary':description,
             'category':'Other nuclear','url':link,'source':SOURCE,'links':links}
        out.append(enrich_record(rec,bodytext))
    return out

def collect():
    found={}
    for feed in FEEDS:
        raw=get(feed)
        if not raw:continue
        try:root=ET.fromstring(raw)
        except ET.ParseError:continue
        for item in root.findall('.//item'):
            for a in records_from_item(item):
                k=(a['url'].rstrip('/'),a['title'].casefold())
                found[k]=a
    print('Feed items:',len(found),flush=True)
    return found

def mkweeks(articles, old):
    start=TODAY-dt.timedelta(days=TODAY.weekday()+7)
    preserved={x['week_start']:x for x in old if x.get('editorial') and x.get('week_start')}
    out=[]
    while start>=WEEK_START:
        end=start+dt.timedelta(days=6)
        key=start.isoformat()
        if key in preserved:
            out.append(preserved[key])
        else:
            items=[a for a in articles if key<=a['date']<=end.isoformat()]
            if items:
                by=defaultdict(list)
                for a in items:
                    by[(a.get('categories') or ['Other developments'])[0]].append(a)
                sections=[]
                for c,events in sorted(by.items(),key=lambda z:-len(z[1])):
                    sections.append({'category':c,'takeaway':f'{len(events)} Neutron Bytes developments, including '+ '; '.join(x['title'] for x in events[:2])+'.','items':events})
                out.append({'week_start':key,'week_end':end.isoformat(),'title':'Nuclear sector news — week of '+start.strftime('%B %d, %Y'),
                            'overview':f'{len(items)} source-linked nuclear developments covered in Neutron Bytes. Grouped by subject, with original reporting links. No independent verification implied.',
                            'article_count':len(items),'generated_at':TODAY.isoformat(),'sections':sections})
        start-=dt.timedelta(days=7)
    return out[:7]

def main():
    if os.getenv('GITHUB_EVENT_NAME')=='schedule' and dt.datetime.now(ZoneInfo('America/Chicago')).hour!=7:
        print('Different Central-time hour; skipping daylight-saving redundant run');return
    DATA.mkdir(exist_ok=True)
    path=DATA/'articles.json'
    info=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'articles':[]}
    records={}
    for a in info['articles']:
        if a.get('url') and a.get('title'):
            records[(a['url'].rstrip('/'),a['title'].casefold())]=a
    newer=collect()
    records.update(newer)
    articles=list(records.values())
    for a in articles:enrich_record(a)
    articles.sort(key=lambda a:(a['date'],a.get('importance_score',0)),reverse=True)
    path.write_text(json.dumps({'updated_at':TODAY.isoformat(),
      'methodology':'Independent source-linked digest, no caps; Neutron Bytes post URLs plus only cited links. Each article may have multiple tags. Source updates via public WordPress RSS feed.',
      'articles':articles},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    briefing_path=DATA/'briefings.json'
    try:old=json.loads(briefing_path.read_text(encoding='utf-8')).get('briefings',[])
    except (OSError,ValueError):old=[]
    weeks=mkweeks(articles,old)
    briefing_path.write_text(json.dumps({'generated_at':TODAY.isoformat(),'briefings':weeks},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('News:',len(articles),'weekly reports:',len(weeks),flush=True)

if __name__=='__main__':main()
