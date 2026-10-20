# -*- coding: utf-8 -*-
"""スキンダプサス定点観測: SB / Kamle / Mapl / Paradise の商品一覧を取得し、
前回スナップショット (watch/snapshots/*.json) との差分を報告する。
実行: python3 watch/watch_shops.py   （リポジトリのルートで実行）
出力: 差分レポートを標準出力へ。スナップショットは上書き保存（コミットは呼び出し側で行う）。
"""
import json, re, sys, time, urllib.request, os
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, 'snapshots')
os.makedirs(SNAP, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (zukan-watch; contact: hide124@gmail.com)'}
JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')

def get(url, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:
            last = e; time.sleep(5 * (i + 1))
    print(f'!! 取得失敗: {url} ({last})')
    return None

def is_scin(s):
    return 'scindapsus' in s.lower() or 'skindapsus' in s.lower()

# ---------- 各店 ----------
def fetch_sb():
    """Scindapsus Borneo (Shopify): products.json 全ページ"""
    items = {}
    page = 1
    while page <= 20:
        t = get(f'https://www.scindapsusborneo.com/products.json?limit=250&page={page}')
        if t is None:
            return None
        try:
            prods = json.loads(t)['products']
        except Exception:
            return None
        if not prods:
            break
        for p in prods:
            if is_scin(p.get('handle', '')) or is_scin(p.get('title', '')):
                items[p['handle']] = {'title': p['title'],
                                      'published': (p.get('published_at') or '')[:10],
                                      'available': any(v.get('available') for v in p.get('variants', []))}
        page += 1
    return items

def fetch_kamle():
    """Kamle Plants (WordPress): 検索ページを辿って /shop/<slug>/ を収集"""
    items = {}
    page = 1
    while page <= 30:
        url = ('https://kamleplants.com/?s=scindapsus&post_type=product' if page == 1
               else f'https://kamleplants.com/page/{page}/?s=scindapsus&post_type=product')
        t = get(url, retries=3 if page == 1 else 1)
        if t is None:
            return None if page == 1 else items  # 2ページ目以降の404はページ送りの終端
        found = set(re.findall(r'https://kamleplants\.com/shop/([a-z0-9-]+)/', t))
        found.discard('feed')
        new = found - set(items)
        for slug in found:
            m = re.search(r'/shop/' + re.escape(slug) + r'/"[^>]*>([^<]{3,100})<', t)
            items.setdefault(slug, {'title': (m.group(1).strip() if m else slug)})
        if not new:
            break
        page += 1
    return items

def fetch_mapl():
    """Mapl Plants (vercel): sitemap.xml から /products/<slug> と lastmod"""
    t = get('https://maplplants.vercel.app/sitemap.xml')
    if t is None:
        return None
    items = {}
    for loc, lastmod in re.findall(r'<url>\s*<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>', t):
        m = re.search(r'/products/([a-z0-9-]+)$', loc)
        if m and is_scin(m.group(1)):
            items[m.group(1)] = {'title': m.group(1).replace('-', ' '), 'lastmod': lastmod[:10]}
    return items

def fetch_paradise():
    """Paradise Plants (Wix): store-products-sitemap.xml"""
    t = get('https://www.paradiseplants.org/store-products-sitemap.xml')
    if t is None:
        return None
    items = {}
    for loc in re.findall(r'<loc>([^<]+)</loc>', t):
        m = re.search(r'/product-page/([a-z0-9-]+)$', loc)
        if m and is_scin(m.group(1)):
            items[m.group(1)] = {'title': m.group(1).replace('-', ' ')}
    return items

SHOPS = [('scindapsusborneo', 'Scindapsus Borneo', fetch_sb),
         ('kamleplants', 'Kamle Plants', fetch_kamle),
         ('maplplants', 'Mapl Plants', fetch_mapl),
         ('paradiseplants', 'Paradise Plants', fetch_paradise)]

def main():
    report = [f'# スキンダプサス定点観測レポート（{NOW}）', '']
    any_change = False
    for key, name, fn in SHOPS:
        path = os.path.join(SNAP, key + '.json')
        prev = {}
        first = not os.path.exists(path)
        if not first:
            prev = json.load(open(path)).get('items', {})
        cur = fn()
        if cur is None:
            report.append(f'## {name}: 取得失敗（サイト不達またはレート制限。スナップショットは前回のまま）')
            report.append('')
            continue
        added = sorted(set(cur) - set(prev))
        removed = sorted(set(prev) - set(cur))
        json.dump({'fetched_at': NOW, 'count': len(cur), 'items': cur},
                  open(path, 'w'), ensure_ascii=False, indent=1, sort_keys=True)
        if first:
            report.append(f'## {name}: 初回スナップショット（{len(cur)}件）を保存')
        elif not added and not removed:
            report.append(f'## {name}: 変化なし（{len(cur)}件）')
        else:
            any_change = True
            report.append(f'## {name}: {len(prev)}件 → {len(cur)}件')
            for s in added:
                report.append(f'  + 新規: {cur[s].get("title", s)}  ({s})')
            for s in removed:
                report.append(f'  - 消滅: {prev[s].get("title", s)}  ({s})')
        report.append('')
    report.append('変化あり' if any_change else 'すべて変化なし（初回を除く）')
    print('\n'.join(report))

if __name__ == '__main__':
    main()
