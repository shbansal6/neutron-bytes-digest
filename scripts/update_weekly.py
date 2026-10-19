"""Unattended, source-restricted Neutron Bytes weekly reporting.

Runs in GitHub Actions at Monday 7am America/Chicago, with a secret OPENAI_API_KEY.
Only Neutron Bytes articles and hyperlinks INSIDE those articles are fetched.
No verified news -> no manufactured story. One MD briefing and cumulative archive update per week.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse, urldefrag
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # Offline site build/tests can run without the API client.

from site_builder import ROOT, CATEGORIES, append_stories, build_weekly_pages, normalized_url

BASE='https://neutronbytes.com'
HEADERS={'User-Agent':'NeutronBytesWeeklyResearch/1.0 (public RSS and published articles only)'}
SESSION=requests.Session();SESSION.headers.update(HEADERS)
TIMEOUT=25
PERMALINK=re.compile(r'^https://(?:www\.)?neutronbytes\.com/(20\d{2})/(\d{2})/(\d{2})/([^/?#]+)/?$',re.I)


def post_date(url):
    m=PERMALINK.match(url)
    if not m:return None
    try:return date(int(m[1]),int(m[2]),int(m[3]))
    except ValueError:return None


def fetch(url):
    r=SESSION.get(url,timeout=TIMEOUT)
    r.raise_for_status()
    if not any(x in r.headers.get('content-type','').lower() for x in ('html','xml','rss','json','text')):
        raise ValueError('Unexpected response content type')
    return r.text


def discover_posts(start,end):
    """Union REST, RSS and monthly archive URL discovery, fail rather than guess.

    This is best-effort public discovery, not a guarantee the host lists every post.
    """
    urls=set(); channels=[]; errors=[]
    after=(start-timedelta(days=2)).isoformat()+'T00:00:00'
    before=(end+timedelta(days=2)).isoformat()+'T23:59:59'
    for page in range(1,8):
        url=f'{BASE}/wp-json/wp/v2/posts?per_page=100&page={page}&after={after}&before={before}&_fields=date,link'
        try:
            data=json.loads(fetch(url))
            if not isinstance(data,list): raise ValueError('Unexpected WP response')
            for item in data:
                link=item.get('link','').split('#')[0]
                if post_date(link) and start<=post_date(link)<=end:urls.add(link)
            channels.append('WP REST')
            if len(data)<100:break
        except Exception as ex:
            errors.append('WordPress REST: '+str(ex)[:135]);break
    try:
        xml=ET.fromstring(fetch(f'{BASE}/feed/'))
        for item in xml.findall('.//channel/item'):
            link=(item.findtext('link') or '').strip().split('#')[0]
            if post_date(link) and start<=post_date(link)<=end:urls.add(link)
        channels.append('RSS')
    except Exception as ex:errors.append('RSS: '+str(ex)[:135])
    cursor=date(start.year,start.month,1)
    final=date(end.year,end.month,1)
    while cursor<=final:
        try:
            page=BeautifulSoup(fetch(f'{BASE}/{cursor:%Y/%m}/'),'html.parser')
            found=0
            for a in page.find_all('a',href=True):
                href=a['href'].split('#')[0].split('?')[0]
                if href.startswith('/'):
                    href=BASE+href
                dt=post_date(href)
                if dt and start<=dt<=end:
                    urls.add(href);found+=1
            if found: channels.append('monthly archive')
        except Exception as ex:errors.append(f'Archive {cursor:%Y/%m}: '+str(ex)[:135])
        cursor=date(cursor.year+cursor.month//12,cursor.month%12+1,1)
    if not channels:
        raise RuntimeError('All Neutron Bytes article discovery methods failed; refusing to fabricate weekly coverage: '+str(errors))
    return sorted(urls,key=lambda x:(post_date(x),x),reverse=True), channels, errors


def clean_link(href):
    if not href:return None
    url=urldefrag(href.strip())[0]
    if url.startswith('//'):url='https:'+url
    p=urlparse(url)
    if p.scheme!='https' or not p.netloc:return None
    if p.netloc.lower().endswith('neutronbytes.com'):return None
    return url


def extract_post(url):
    html=BeautifulSoup(fetch(url),'html.parser')
    article=next((x for css in ('.entry-content','.post-content','.td-post-content','article .content','article')
                  for x in html.select(css) if len(x.get_text(' ',strip=True))>400), None)
    if article is None:raise ValueError('Article body unavailable at '+url)
    for junk in article.select('script,style,form,nav,.sharedaddy,.jp-relatedposts,.social-share'):
        junk.decompose()
    links=[];seen=set()
    for a in article.find_all('a',href=True):
        href=clean_link(a.get('href'))
        if href and href not in seen:
            seen.add(href)
            label=a.get_text(' ',strip=True)[:120] or urlparse(href).netloc
            links.append({'url':href,'label':label})
    # NB article, NOT external search snippets or unrelated content.
    text=article.get_text('\n',strip=True)
    if len(text)<250:raise ValueError('Article appears empty at '+url)
    title=html.find('h1')
    return {'url':url,'date':post_date(url).isoformat(),'title':title.get_text(' ',strip=True) if title else '',
            'text':text[:145000], 'links':links[:120]}


def source_excerpt(link):
    """Review the linked original source when accessible; never follow unrelated links."""
    url=link['url']
    try:
        p=urlparse(url)
        if p.netloc in ('linkedin.com','www.linkedin.com','x.com','twitter.com'):
            return ''
        body=BeautifulSoup(fetch(url),'html.parser')
        for junk in body.select('script,style,nav,footer,header'):junk.decompose()
        el=body.select_one('article,main') or body
        return el.get_text(' ',strip=True)[:1300]
    except Exception:
        return ''


def summarize_post(post,client):
    links=post['links']
    extracts=[]
    for lk in links[:25]:
        excerpt=source_excerpt(lk)
        if excerpt:extracts.append({'url':lk['url'],'excerpt':excerpt})
    system=("You write precise, non-promotional investment banking nuclear sector research. "
            "ONLY use the provided Neutron Bytes article and texts of ORIGINAL SOURCES explicitly linked within it. "
            "Break multi-story roundup posts into EACH distinct substantive development (including financial, licensing, fuel, policy, construction and analysis). "
            "Never convert a proposal into an FID, licence, signed PPA, funded construction contract, or operation. "
            "Use article publication date, not milestone date, in every story. Do not fabricate titles, facts, numbers or URLs. "
            "Avoid duplicate descriptions, ceremonial/promotional filler, and editorial speculation presented as fact. "
            "Return one JSON object with key 'stories' holding an array. Each story keys: title, category, teaser (1-2 clear sentences), detail (2-6 factual sentences with financial and technical figures as relevant), original_sources (array of objects with url and label). "
            "Categories allowed: "+', '.join(CATEGORIES)+". Include 0 stories only if article genuinely contains no substantive nuclear development. "
            "Choose original_sources ONLY from the provided 'allowed_links', in order of substantive relevance; NEVER invent or alter URLs. "
            "Where a link is only an unrelated corporate homepage or tangential, omit. No more than 4 source links per story. "
            "Return VALID JSON, with no markdown wrapper.")
    prompt={'neutronbytes_title':post['title'],'article_url':post['url'],'publication_date':post['date'],
            'article_text':post['text'],'allowed_links':links,'linked_original_source_excerpts':extracts}
    result=client.chat.completions.create(
        model=os.environ.get('OPENAI_MODEL','gpt-4.1-mini'),
        messages=[{'role':'system','content':system},{'role':'user','content':json.dumps(prompt,ensure_ascii=False)}],
        response_format={'type':'json_object'},temperature=0.1)
    response=json.loads(result.choices[0].message.content)
    found=response.get('stories',[])
    if not isinstance(found,list):raise ValueError('Model returned invalid stories list')
    allowed={lk['url']:lk for lk in links}
    validated=[]
    for item in found:
        if not isinstance(item,dict) or not all(item.get(k) for k in ('title','detail')):continue
        category=item.get('category','')
        if category not in CATEGORIES:category='Policy & international'
        sources=[];seen=set()
        for link in item.get('original_sources',[]):
            url=link.get('url','') if isinstance(link,dict) else ''
            if url in allowed and url not in seen:
                sources.append({'url':url,'label':(link.get('label') or allowed[url]['label'])[:90]})
                seen.add(url)
        validated.append({'published_date':post['date'],'neutronbytes_url':post['url'],
                          'title':item['title'].strip(),'category':category,
                          'teaser':(item.get('teaser') or item['detail']).strip(),
                          'detail':item['detail'].strip(),'original_sources':sources})
    return validated


def report_markdown(weekstart,weekend,stories,client):
    bullets=[{'title':s['title'],'cat':s['category'],'detail':s['detail'][:500]} for s in stories]
    text=''
    if bullets:
        out=client.chat.completions.create(
            model=os.environ.get('OPENAI_MODEL','gpt-4.1-mini'),
            messages=[{'role':'system','content':'Write a 90-140 word factual executive summary for an investment banking managing director. Use ONLY data provided in the news items, reference key figures, mention material uncertainty, no promotional tone, no invented material. Plain prose, no heading.'},
                      {'role':'user','content':json.dumps(bullets,ensure_ascii=False)}],temperature=0.1)
        text=out.choices[0].message.content.strip()
    out=[f'# Neutron Bytes | Weekly Nuclear News Digest',
         f'**Coverage:** Monday {weekstart:%B} {weekstart.day}–Sunday {weekend:%B} {weekend.day}, {weekend.year}',
         '', '## Executive summary',text or 'No substantive developments were identified in the accessible articles for the period.',
         '',f'**Substantive developments:** {len(stories)}', '']
    for cat in CATEGORIES:
        group=[s for s in stories if s['category']==cat]
        if not group:continue
        out.append('## '+cat);out.append('')
        for s in group:
            out.extend([f'### {s["title"]} — {datetime.strptime(s["published_date"],"%Y-%m-%d"):%b %d, %Y}',
                        s['detail'],''])
            links=[f'[Neutron Bytes]({s["neutronbytes_url"]})']
            for k, source in enumerate(s['original_sources']):
                label=source['label'].replace('[','').replace(']','')
                links.append(f'[Original: {label}]({source["url"]})')
            out.extend(['Sources: '+' · '.join(links),''])
    return '\n'.join(out).rstrip()+'\n'


def main():
    arg=argparse.ArgumentParser()
    arg.add_argument('--week',help='Week start as YYYY-MM-DD (Monday); defaults to preceding complete Mon-Sun week')
    arg.add_argument('--self-check',action='store_true',help='Offline safety test; do not fetch or modify content')
    args=arg.parse_args()
    if args.self_check:
        from bs4 import BeautifulSoup
        archive=BeautifulSoup((ROOT/'index.html').read_text(encoding='utf-8'),'html.parser')
        assert len(archive.select('.news-card'))>=137
        assert len(list((ROOT/'weekly').glob('20??-??-??.md')))>=1
        assert archive.select_one('.main-sections a[href="weekly/"]')
        build_weekly_pages()
        print('Self check passed: archive entries:',len(archive.select('.news-card')))
        return
    local_today=datetime.now(ZoneInfo('America/Chicago')).date()
    current_monday=local_today-timedelta(days=local_today.weekday())
    weekstart=date.fromisoformat(args.week) if args.week else current_monday-timedelta(days=7)
    if weekstart.weekday()!=0:raise ValueError('--week must be Monday')
    weekend=weekstart+timedelta(days=6)
    file=ROOT/'weekly'/f'{weekstart.isoformat()}.md'
    if file.exists():
        print(f'Week already published, leaving it unchanged: {weekstart}')
        build_weekly_pages();return
    if not os.getenv('OPENAI_API_KEY'):
        raise RuntimeError('Missing GitHub Actions repository secret OPENAI_API_KEY. No publish was attempted.')
    urls,channels,errors=discover_posts(weekstart,weekend)
    print(f'Discovered {len(urls)} Neutron Bytes posts using {channels}; discovery warnings: {errors}')
    if not urls:
        # No substantive posts confirmed: avoid a false "nothing happened" claim.
        raise RuntimeError('No Neutron Bytes posts confirmed this week. Please review the feed/monthly archive; no speculative blank newsletter published.')
    client=OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    stories=[];checked=[];failures=[]
    for url in urls:
        try:
            p=extract_post(url)
            items=summarize_post(p,client)
            stories+=items;checked.append(url)
        except Exception as ex:
            failures.append(f'{url}: {type(ex).__name__}: {str(ex)[:200]}')
    if failures:
        # Prevent incomplete weekly editions from being mistaken for full coverage.
        raise RuntimeError('Some posts could not be processed; NO publication. Review failures: '+str(failures))
    if not stories:
        raise RuntimeError('No substantive stories extracted; requires editorial review before publishing.')
    # deduplicate within weekly edition
    unique={}
    for story in stories:
        key=(story['published_date'],re.sub(r'\W+','',story['title'].lower()))
        if key not in unique:unique[key]=story
    stories=sorted(unique.values(),key=lambda x:(x['published_date'],x['title']),reverse=True)
    md=report_markdown(weekstart,weekend,stories,client)
    file.write_text(md,encoding='utf-8')
    jfile=ROOT/'data'/'weeks'/f'{weekstart.isoformat()}.json'
    jfile.write_text(json.dumps({'week_start':weekstart.isoformat(),'week_end':weekend.isoformat(),'posts_reviewed':checked,'discovery_channels':channels,'discovery_warnings':errors,'stories':stories},indent=2,ensure_ascii=False),encoding='utf-8')
    added=append_stories(stories)
    build_weekly_pages()
    print(f'Published {len(stories)} weekly stories; appended {added} net-new stories to cumulative archive.')

if __name__=='__main__':main()