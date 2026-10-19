"""Build the weekly briefing pages and append newly verified cards to the existing news archive.

This file never deletes or rewrites historical news content. The archive is updated only
with new, de-duplicated stories. Briefing pages are derived from saved weekly Markdown.
"""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import mistune
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
WEEKS = ROOT / 'weekly'
CATEGORIES = [
    'Restarts & uprates', 'Offtake & customers', 'Construction & licensing',
    'Fuel & supply chain', 'Capital & financing', 'Fusion & research',
    'Policy & international',
]
MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']


def safe_url(raw):
    u = (raw or '').strip()
    p = urlparse(u)
    return u if p.scheme == 'https' and p.netloc else ''


def normalized_url(u):
    p = urlparse(u)
    return f'{p.scheme}://{p.netloc.lower()}{p.path.rstrip("/")}/'


def build_weekly_pages():
    docs = sorted(WEEKS.glob('20??-??-??.md'), reverse=True)
    if not docs:
        return
    renderer = mistune.create_markdown(escape=True, plugins=['table', 'strikethrough'])
    for n, doc in enumerate(docs):
        week = doc.stem
        last = (datetime.strptime(week,'%Y-%m-%d').date())
        from datetime import timedelta
        end = last + timedelta(days=6)
        weeklabel = f'{last:%b %-d}–{end:%b %-d, %Y}'
        nav = ''.join(f'<a href="{d.stem}.html" class="{"active" if d==doc else ""}"><b>{datetime.strptime(d.stem,"%Y-%m-%d"):%b %-d, %Y}</b><span>Weekly briefing</span></a>' for d in docs)
        # all site paths relative to weekly/
        body = renderer(doc.read_text(encoding='utf-8'))
        page=f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Neutron Bytes | Weekly Briefing {html.escape(weeklabel)}</title>
<style>
:root{{--navy:#0c1f33;--ink:#17293b;--sub:#597086;--line:#dce5ec;--blue:#1362a5}}
*{{box-sizing:border-box}}body{{margin:0;background:#f0f4f7;color:var(--ink);font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;font-size:14px;line-height:1.65}}
a{{color:var(--blue)}}a:hover{{text-decoration:underline}}.shell{{max-width:1500px;display:grid;grid-template-columns:240px minmax(0,1fr);min-height:100vh;margin:auto}}
.side{{background:var(--navy);color:#f1f7fa;padding:28px 22px;position:sticky;top:0;align-self:start;height:100vh;display:flex;flex-direction:column;gap:22px;overflow:auto}}
.brand-small{{font-size:10px;letter-spacing:.22em;color:#8dbed9;font-weight:800}}.brand-name{{font-size:23px;font-weight:850;letter-spacing:-1px;line-height:1.05;margin-top:10px}}
.brand-slogan{{color:#a3bfd1;font-size:12px;line-height:1.4;margin-top:6px}}.main-sections{{border-top:1px solid #31506a;border-bottom:1px solid #31506a;padding:16px 0;display:grid;gap:6px}}
.main-sections a{{color:#dceef8;text-decoration:none;font-weight:700;padding:10px 12px;border-radius:7px}}.main-sections .active,.main-sections a:hover{{background:#1e425d;color:white}}
.week-jump-label{{font-size:10px;letter-spacing:.18em;font-weight:850;color:#91b3c6;margin-bottom:8px}}.week-links{{display:grid;gap:5px}}
.week-links a{{display:grid;text-decoration:none;color:#d6e5f1;padding:11px;border-radius:7px;line-height:1.3}}
.week-links a span{{font-size:10px;color:#88a7b8;margin-top:2px}}.week-links a.active,.week-links a:hover{{background:#1e425d;color:white}}
.content{{min-width:0;padding:38px 46px 70px}}.topline{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin:0 auto 20px;max-width:960px}}
.kicker{{font-size:11px;letter-spacing:.19em;text-transform:uppercase;font-weight:800;color:#356387}}.period{{font-size:12px;color:var(--sub)}}
.report{{background:white;border:1px solid var(--line);border-radius:13px;padding:32px 43px;max-width:960px;margin:auto;box-shadow:0 5px 20px #0e315008;overflow-wrap:anywhere}}
.report h1{{font-size:30px;line-height:1.16;letter-spacing:-.7px;margin:0 0 10px}}.report h2{{font-size:21px;letter-spacing:-.4px;line-height:1.25;color:#103550;margin:32px 0 12px;padding-bottom:9px;border-bottom:1px solid var(--line)}}
.report h3{{font-size:16px;line-height:1.4;margin:22px 0 8px;color:#0e2942}}.report p{{margin:8px 0 13px}}.report strong{{color:#17384f}}
.report h1+p{{color:#597086}}.report ul{{padding-left:22px}}.report li{{margin:8px 0}}.report a{{font-weight:650;text-decoration:underline;text-decoration-color:#a4c4d9;text-underline-offset:3px}}
.report h3+p{{margin-top:6px}}.report hr{{border:0;border-top:1px solid var(--line);margin:25px 0}}
.nav-end{{margin:26px auto;max-width:960px;display:flex;gap:12px;flex-wrap:wrap}}.nav-end a{{color:#165d90;font-weight:650;text-decoration:none}}
@media(max-width:900px){{.shell{{grid-template-columns:1fr}}.side{{position:relative;height:auto;padding:20px;gap:12px}}.side .week-links{{display:flex;overflow:auto;gap:10px}}.week-links a{{min-width:145px}}.content{{padding:22px 14px}}.report{{padding:24px 20px}}.report h1{{font-size:24px}}}}
</style></head><body><div class="shell">
<aside class="side"><div><div class="brand-small">ENERGY &amp; POWER RESEARCH</div><div class="brand-name">NEUTRON<br/>BYTES</div><div class="brand-slogan">Source-linked nuclear sector intelligence</div></div>
<div class="main-sections"><a href="../">News archive</a><a href="./" class="active">Weekly updates</a></div>
<div><div class="week-jump-label">WEEKLY BRIEFINGS · NEWEST FIRST</div><nav class="week-links">{nav}</nav></div></aside>
<main class="content"><div class="topline"><span class="kicker">Weekly nuclear intelligence</span><span class="period">{html.escape(weeklabel)}</span></div>
<article class="report">{body}</article><div class="nav-end"><a href="../">← News archive</a></div></main>
</div></body></html>'''
        (WEEKS / f'{week}.html').write_text(page, encoding='utf-8')
        if n == 0:
            (WEEKS / 'index.html').write_text(page, encoding='utf-8')


def append_stories(stories):
    """Input: individual validated stories; only appends non-duplicate stories to the correct period."""
    if not stories:
        return 0
    dst=ROOT/'index.html'
    soup=BeautifulSoup(dst.read_text(encoding='utf-8'), 'html.parser')
    entries=soup.select_one('#entries')
    if entries is None:
        raise RuntimeError('Expected existing archive #entries')
    old_keys=set()
    for node in soup.select('.news-card'):
        dt=node.select_one('.story-date').get_text(' ', strip=True) if node.select_one('.story-date') else ''
        ttl=node.select_one('h4').get_text(' ',strip=True) if node.select_one('h4') else ''
        old_keys.add((dt.lower(),ttl.lower()))
    existing_ids={node['id'] for node in soup.select('.news-card') if node.has_attr('id')}
    added=0
    for story in sorted(stories,key=lambda x:(x['published_date'],x['title']),reverse=True):
        date=datetime.strptime(story['published_date'], '%Y-%m-%d').date()
        stamp=f'{date:%b} {date.day}, {date:%Y}'
        title=story['title'].strip()
        if (stamp.lower(),title.lower()) in old_keys:
            continue
        cat=story['category'] if story['category'] in CATEGORIES else 'Policy & international'
        nb=safe_url(story.get('neutronbytes_url'))
        if not nb or urlparse(nb).netloc not in ('neutronbytes.com','www.neutronbytes.com'):
            raise ValueError(f'Invalid Neutron Bytes permalink for {title}')
        # Require a specific post permalink /YYYY/MM/DD/slug/ (never a generic monthly archive).
        if not re.search(r'/20\d{2}/\d{2}/\d{2}/[^/]+/?$',urlparse(nb).path):
            raise ValueError(f'Not a post permalink: {nb}')
        month_id=f'period-{date:%Y-%m}' if date.year>=2025 else f'period-{date:%Y}-q{(date.month-1)//3+1}'
        year_id=f'year-{date:%Y}'
        year=soup.find(id=year_id)
        if year is None:
            year=soup.new_tag('section',attrs={'class':'archive-year','data-yearblock':str(date.year),'id':year_id})
            header=soup.new_tag('div',attrs={'class':'year-header'})
            header.append(BeautifulSoup(f'<div class="year-number">{date.year}</div><div class="year-info"><div class="year-kicker">MONTHLY COVERAGE</div><h3>Nuclear sector developments</h3></div><div class="year-count">0<span> selected developments</span></div>','html.parser'))
            year.append(header)
            wrap=soup.new_tag('div',attrs={'class':'period-wrap'})
            year.append(wrap)
            other=[n for n in entries.select('.archive-year') if n.get('data-yearblock')]
            first_older=next((n for n in other if int(n['data-yearblock'])<date.year),None)
            if first_older: first_older.insert_before(year)
            else: entries.append(year)
            # new year filter
            ysel=soup.find(id='yrfilter')
            if ysel:
                opt=soup.new_tag('option', value=str(date.year)); opt.string=str(date.year)
                target=next((x for x in ysel.find_all('option') if x.get('value','').isdigit() and int(x['value'])<date.year),None)
                if target: target.insert_before(opt)
                else: ysel.append(opt)
        period=soup.find(id=month_id)
        if period is None:
            period=soup.new_tag('section',attrs={'class':'period','id':month_id})
            name=MONTHS[date.month-1] if date.year>=2025 else f'Q{(date.month-1)//3+1}'
            hd=BeautifulSoup(f'<div class="period-heading"><div class="period-tick"></div><div><div class="period-name">{name}</div><div class="period-sub">0 developments</div></div></div><div class="period-cards"></div>','html.parser')
            period.append(hd)
            wrap=year.select_one('.period-wrap')
            periods=wrap.select(':scope > .period')
            if date.year>=2025:
                newer_order=date.month
                older=next((x for x in periods if int(x['id'].split('-')[-1])<newer_order),None)
            else:
                older=None
            if older: older.insert_before(period)
            else: wrap.append(period)
        card=soup.new_tag('article',attrs={'class':'news-card','data-cat':cat,'data-year':str(date.year)})
        digest=hashlib.sha256((nb+'|'+title.lower()).encode()).hexdigest()[:14]
        identifier='news-'+digest
        if identifier in existing_ids: continue
        card['id']=identifier
        teaser=(story.get('teaser') or story.get('detail',''))[:320].strip()
        detail=story.get('detail') or teaser
        card['data-search']=(title+' '+teaser+' '+detail+' '+cat).lower()[:6000]
        top=soup.new_tag('div',attrs={'class':'story-top'})
        label=soup.new_tag('span',attrs={'class':'story-category'});label.string=cat
        dt=soup.new_tag('span',attrs={'class':'story-date'});dt.string=stamp
        top.extend([label,dt]);card.append(top)
        h=soup.new_tag('h4');h.string=title;card.append(h)
        teaser_node=soup.new_tag('div',attrs={'class':'story-teaser'});teaser_node.string=teaser;card.append(teaser_node)
        full=soup.new_tag('div',attrs={'class':'story-full'});full.string=detail;card.append(full)
        sources=soup.new_tag('div',attrs={'class':'sources'})
        anchor=soup.new_tag('a',href=nb,target='_blank',rel='noopener noreferrer'); anchor.string='Neutron Bytes ↗';sources.append(anchor)
        for i, item in enumerate(story.get('original_sources',[])):
            url=safe_url(item.get('url','')); label=(item.get('label') or urlparse(url).netloc)[:90]
            if not url or urlparse(url).netloc in ('neutronbytes.com','www.neutronbytes.com'):continue
            a=soup.new_tag('a',href=url,target='_blank',rel='noopener noreferrer');a.string=('Original · ' if i==0 else 'More · ')+label+' ↗';sources.append(a)
        card.append(sources)
        # Add to period sorted by post date, keeping previous stories intact.
        cards=period.select_one('.period-cards')
        existing_cards=cards.select(':scope > .news-card')
        older=next((node for node in existing_cards if parse_displayed_date(node)<date),None)
        if older: older.insert_before(card)
        else: cards.append(card)
        old_keys.add((stamp.lower(),title.lower()));existing_ids.add(identifier);added+=1
    if added:
        for period in soup.select('.period'):
            counter=period.select_one('.period-sub')
            if counter:counter.string=f'{len(period.select(".news-card"))} developments'
        for year in soup.select('.archive-year'):
            count=len(year.select('.news-card'))
            counter=year.select_one('.year-count')
            if counter: counter.clear();counter.append(str(count));counter.append(BeautifulSoup('<span> selected developments</span>', 'html.parser'))
        nav=soup.select_one('.sidebar .jump')
        if nav:
            for a in nav.find_all('a',href=True):
                y=a['href'].replace('#year-',''); group=soup.find(id='year-'+y)
                if group and a.find('span'):a.find('span').string=str(len(group.select('.news-card')))
        dst.write_text(str(soup),encoding='utf-8')
    return added


def parse_displayed_date(card):
    txt=card.select_one('.story-date').get_text(' ',strip=True)
    return datetime.strptime(txt,'%b %d, %Y').date()


if __name__=='__main__':
    build_weekly_pages()
    print('Generated',len(list(WEEKS.glob('20??-??-??.html'))),'briefing pages')