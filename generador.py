#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote_plus
from xml.sax.saxutils import escape, quoteattr
import requests
from bs4 import BeautifulSoup

BASE='https://nextnovels.com'
CATEGORY=BASE+'/category/novela-ligera/'
OUT=Path('catalogo')
DATA=OUT/'catalogo.json'
UA='Mozilla/5.0 (compatible; NextNovels-OPDS/1.0)'
MIN_VALID=10
MAX_PAGES=80
S=requests.Session(); S.headers.update({'User-Agent':UA})

def clean(x): return re.sub(r'\\s+',' ',str(x or '')).strip()
def absu(x): return urljoin(BASE,x) if x else ''
def get(url):
    r=S.get(url,timeout=25); r.raise_for_status(); return BeautifulSoup(r.text,'html.parser')
def article_url(u):
    p=urlparse(u); path=p.path.rstrip('/')
    if p.netloc and 'nextnovels.com' not in p.netloc: return False
    bad=('/category/','/tag/','/author/','/page/','/genero/','/indice-','/wp-')
    return path not in ('','/') and not any(x in path+'/' for x in bad)

def discover():
    out=[]; seen=set()
    for n in range(1,MAX_PAGES+1):
        u=CATEGORY if n==1 else f'{CATEGORY}page/{n}/'
        try: s=get(u)
        except Exception: break
        found=[]
        for a in s.select('h2 a,h3 a,article a,.entry-title a,a[href]'):
            u2=absu(a.get('href'))
            if article_url(u2) and u2 not in seen: found.append(u2)
        new=0
        for u2 in found:
            if u2 not in seen: seen.add(u2); out.append(u2); new+=1
        if not new: break
        time.sleep(.2)
    return out

def label(s,label):
    m=re.search(rf'{re.escape(label)}\\s*:?\\s*([^\\n]+)',s.get_text('\\n',strip=True),re.I)
    return clean(m.group(1)) if m else ''

def parse(url):
    s=get(url); h=s.find('h1')
    title=clean(h.get_text(' ',strip=True)) if h else clean(s.title.get_text() if s.title else '')
    title=re.sub(r'\\s+-\\s+Next Novels\\s*$','',title,flags=re.I)
    main=s.select_one('article,.entry-content,.post-content,main') or s
    og=s.find('meta',property='og:image'); cover=absu(og.get('content')) if og and og.get('content') else ''
    if not cover:
        img=main.find('img'); cover=absu(img.get('src') or img.get('data-src')) if img else ''
    author=label(main,'Autor'); status=label(main,'Estado'); typ=label(main,'Tipo')
    genres=[]
    for a in main.select("a[href*='/genero/'],a[href*='/tag/']"):
        t=clean(a.get_text(' ',strip=True))
        if t and t.lower() not in [x.lower() for x in genres]: genres.append(t)
    summary=''
    for h2 in main.find_all(['h2','h3','h4']):
        if 'sinopsis' in clean(h2.get_text()).lower():
            p=[]
            for x in h2.find_all_next():
                if x.name in ['h2','h3','h4']: break
                if x.name=='p' and clean(x.get_text(' ',strip=True)): p.append(clean(x.get_text(' ',strip=True)))
            summary='\\n\\n'.join(p); break
    downloads=[]
    for a in main.select('a[href]'):
        u=absu(a.get('href')); low=u.lower()
        for ext,mime in [('.epub','application/epub+zip'),('.pdf','application/pdf'),('.mobi','application/x-mobipocket-ebook'),('.azw3','application/vnd.amazon.ebook'),('.cbz','application/vnd.comicbook+zip'),('.cbr','application/vnd.comicbook-rar')]:
            if ext in low:
                downloads.append({'url':u,'title':clean(a.get_text(' ',strip=True)) or 'Descarga','type':mime}); break
    return {'id':url,'url':url,'title':title,'cover':cover,'author':author,'status':status,'type':typ,'genres':genres,'summary':summary,'downloads':downloads,'updated':datetime.now(timezone.utc).isoformat()}

def ent(b):
    x=['<entry>','<title>'+escape(b['title'] or 'Sin título')+'</title>','<id>'+escape(b['id'])+'</id>',f'<link rel="alternate" href={quoteattr(b["url"])} type="text/html"/>']
    if b.get('cover'): x.append(f'<link rel="http://opds-spec.org/image" href={quoteattr(b["cover"])} />')
    if b.get('author'): x.append('<author><name>'+escape(b['author'])+'</name></author>')
    for g in b.get('genres',[]): x.append(f'<category term={quoteattr(g)} label={quoteattr(g)}/>')
    if b.get('summary'): x.append('<content type="text">'+escape(b['summary'][:5000])+'</content>')
    for d in b.get('downloads',[]): x.append(f'<link rel="http://opds-spec.org/acquisition" href={quoteattr(d["url"])} type={quoteattr(d["type"])} title={quoteattr(d["title"])} />')
    if not b.get('downloads'): x.append(f'<link rel="http://opds-spec.org/acquisition" href={quoteattr(b["url"])} type="text/html" title="Abrir en Next Novels" />')
    x.append('</entry>'); return '\n'.join(x)

def feed(title,fid,items,selfurl,nav=False):
    x=['<?xml version="1.0" encoding="utf-8"?>','<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">',f'<id>{escape(fid)}</id>',f'<title>{escape(title)}</title>',f'<updated>{datetime.now(timezone.utc).isoformat()}</updated>',f'<link rel="self" href={quoteattr(selfurl)} type="application/atom+xml;profile=opds-catalog"/>']
    x += [ent(b) for b in items]; x.append('</feed>'); return '\n'.join(x)

def main():
    OUT.mkdir(exist_ok=True)
    old=[]
    if DATA.exists():
        try: old=json.loads(DATA.read_text(encoding='utf-8'))
        except Exception: pass
    urls=discover(); books=[]
    for i,u in enumerate(urls,1):
        try:
            b=parse(u)
            if b['title']: books.append(b); print(f'[{i}/{len(urls)}] {b["title"]}')
        except Exception as e: print('[WARN]',u,e)
        time.sleep(.2)
    if len(books)<MIN_VALID:
        if len(old)>=MIN_VALID: books=old
        else: raise RuntimeError(f'NextNovels devolvió muy pocos resultados: {len(books)}')
    books=list({b['url']:b for b in books}.values()); books.sort(key=lambda b:b['title'].lower())
    DATA.write_text(json.dumps(books,ensure_ascii=False,indent=2),encoding='utf-8')
    base='https://raw.githubusercontent.com/Deiviz25/opds-nextnovels/main/catalogo'
    nav=[('Novedades','novedades.xml'),('Todas las novelas','todos.xml'),('Autores','autores.xml'),('Géneros','generos.xml'),('Títulos A-Z','titulos.xml')]
    x=['<?xml version="1.0" encoding="utf-8"?>','<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">','<id>nextnovels:root</id>','<title>Next Novels</title>',f'<updated>{datetime.now(timezone.utc).isoformat()}</updated>',f'<link rel="self" href={quoteattr(base+"/index.xml")} type="application/atom+xml;profile=opds-catalog;kind=navigation"/>']
    for title,file in nav: x += [f'<entry><title>{escape(title)}</title><id>nextnovels:{file}</id><link rel="subsection" href={quoteattr(base+"/"+file)} type="application/atom+xml;profile=opds-catalog;kind=acquisition"/></entry>']
    x.append('</feed>'); (OUT/'index.xml').write_text('\n'.join(x),encoding='utf-8')
    (OUT/'todos.xml').write_text(feed('Todas las novelas','nextnovels:all',books,base+'/todos.xml'),encoding='utf-8')
    (OUT/'titulos.xml').write_text(feed('Títulos A-Z','nextnovels:titles',books,base+'/titulos.xml'),encoding='utf-8')
    (OUT/'novedades.xml').write_text(feed('Novedades','nextnovels:new',sorted(books,key=lambda b:b.get('updated',''),reverse=True)[:200],base+'/novedades.xml'),encoding='utf-8')
    groups={'autores':{},'generos':{}}
    for b in books:
        if b.get('author'): groups['autores'].setdefault(b['author'],[]).append(b)
        for g in b.get('genres',[]): groups['generos'].setdefault(g,[]).append(b)
    for kind,gs in groups.items():
        x=['<?xml version="1.0" encoding="utf-8"?>','<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">',f'<id>nextnovels:{kind}</id>',f'<title>{kind.title()}</title>']
        for i,name in enumerate(sorted(gs,key=str.lower)):
            fn=f'{kind}-{i}.xml'; x.append(f'<entry><title>{escape(name)}</title><id>nextnovels:{fn}</id><link rel="subsection" href={quoteattr(base+"/"+fn)} type="application/atom+xml;profile=opds-catalog;kind=acquisition"/></entry>')
            (OUT/fn).write_text(feed(name,f'nextnovels:{kind}:{name}',gs[name],base+'/'+fn),encoding='utf-8')
        x.append('</feed>'); (OUT/(kind+'.xml')).write_text('\n'.join(x),encoding='utf-8')
    (OUT/'opensearch.xml').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>\n<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">\n<ShortName>Next Novels</ShortName>\n<Description>Buscar en Next Novels</Description>\n<InputEncoding>UTF-8</InputEncoding>\n<Url type="application/atom+xml" template="{base}/search.xml?q={{searchTerms}}"/>\n</OpenSearchDescription>\n''',encoding='utf-8')
    print('Catálogo generado:',len(books),'novelas')
if __name__=='__main__': main()
