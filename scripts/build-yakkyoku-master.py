# -*- coding: utf-8 -*-
"""
九州厚生局「保険医療機関・保険薬局の指定一覧」(県別 Excel/ZIP) から、
分譲先登録用の 薬局マスター JSON を生成する。

出力: data/yakkyoku/<romaji>.json  {pref, asOf, rows:[[code, name, zip, addr, tel, kaisetsu], ...]}
      data/yakkyoku/index.json     {asOf, src, built, prefs:{県名:{file,count}}}

使い方:
  python scripts/build-yakkyoku-master.py           # 一覧ページから各県の最新ZIPを自動検出
  python scripts/build-yakkyoku-master.py --force   # 基準日が同じでも作り直す
GitHub Actions(.github/workflows/yakka-update.yml)が毎週自動実行する。
依存: openpyxl
"""
import os, io, re, sys, json, zipfile, datetime, unicodedata, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT  = os.path.join(ROOT, 'data', 'yakkyoku')
PAGE = 'https://kouseikyoku.mhlw.go.jp/kyushu/gyomu/gyomu/hoken_kikan/index_00006.html'
BASE = 'https://kouseikyoku.mhlw.go.jp'
UA   = {'User-Agent': 'Mozilla/5.0 (bunjo pharmacy master updater)'}
PREFS = {'fukuoka':'福岡', 'saga':'佐賀', 'nagasaki':'長崎', 'kumamoto':'熊本',
         'oita':'大分', 'miyazaki':'宮崎', 'kagoshima':'鹿児島', 'okinawa':'沖縄'}

def log(*a): print(*a, flush=True)

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()

def sp(s):
    # 全角スペース等を半角1つに
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(s or ''))).strip()

def parse(data):
    import openpyxl
    ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
    rows, as_of, cur = [], '', None
    for r in ws.iter_rows(values_only=True):
        r = list(r) + [''] * 12
        c0 = str(r[0] or '').strip()
        if not as_of:
            m = re.search(r'令和\s*(\d+)年\s*(\d+)月\s*(\d+)日現在', str(r[0] or ''))
            if m: as_of = '%d-%02d-%02d' % (2018 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if c0.isdigit():                      # 1件目の行(連番・コード・名称・住所・電話・開設者)
            addr = sp(r[3])
            m = re.match(r'^〒?\s*(\d{3})\s*[-−ー－]?\s*(\d{4})\s*(.*)$', addr)
            zipc, addr = (m.group(1) + '-' + m.group(2), m.group(3)) if m else ('', addr)
            addr = re.sub(r'(?<=\d)[ーｰ−‐－―](?=\d)', '-', addr)   # 110ー68 → 110-68
            cur = [sp(r[1]).replace(',', ''), sp(r[2]), zipc, addr, sp(r[4]), sp(r[5])]
            rows.append(cur)
        elif cur is not None and sp(r[9]) == '休止':   # 2行目の状態欄
            rows.pop(); cur = None
    return rows, as_of

def main():
    force = '--force' in sys.argv
    html = fetch(PAGE).decode('utf-8', 'replace')
    links = re.findall(r'href="(/kyushu/[^"]+\.zip)"', html)
    idx_path = os.path.join(OUT, 'index.json')
    old = {}
    if os.path.exists(idx_path):
        try: old = json.load(open(idx_path, encoding='utf-8'))
        except Exception: pass

    found = {}
    for href in links:                         # ページ上が新しい順 → 県ごとに最初に見つかったZIPが最新
        if len(found) == len(PREFS): break
        try:
            z = zipfile.ZipFile(io.BytesIO(fetch(BASE + href)))
        except Exception as e:
            log('  skip', href, e); continue
        for nm in z.namelist():
            low = nm.lower().replace('ooita', 'oita')     # 表記ゆれ: r8_10_ooita_yakkyoku / r8_10_yakkyoku_fukuoka
            if 'yakkyoku' not in low or not low.endswith('.xlsx'):
                continue
            ro = next((k for k in PREFS if k in low), None)
            if ro and ro not in found:
                found[ro] = (href, z.read(nm))
    if len(found) < len(PREFS):
        log('⚠ 見つからない県:', [PREFS[k] for k in PREFS if k not in found])
        if not found: raise SystemExit('薬局ファイルが1つも見つかりません(ページ構成変更?)')

    os.makedirs(OUT, exist_ok=True)
    index = {'asOf': '', 'src': PAGE, 'built': datetime.date.today().isoformat(), 'prefs': {}}
    parsed = {}
    for ro, (href, data) in found.items():
        rows, as_of = parse(data)
        parsed[ro] = (href, rows, as_of)
        index['asOf'] = max(index['asOf'], as_of)
    if not force and old.get('asOf') == index['asOf'] and set(old.get('prefs', {})) == {PREFS[k] for k in found}:
        log('最新 %s 取込済み → 変更なし' % index['asOf']); return

    total = 0
    for ro in PREFS:
        if ro not in parsed:
            if PREFS[ro] in old.get('prefs', {}): index['prefs'][PREFS[ro]] = old['prefs'][PREFS[ro]]   # 取れなかった県は前回分を維持
            continue
        href, rows, as_of = parsed[ro]
        with open(os.path.join(OUT, ro + '.json'), 'w', encoding='utf-8') as f:
            json.dump({'pref': PREFS[ro], 'asOf': as_of, 'src': BASE + href,
                       'cols': ['code', 'name', 'zip', 'addr', 'tel', 'kaisetsu'], 'rows': rows},
                      f, ensure_ascii=False, separators=(',', ':'))
        index['prefs'][PREFS[ro]] = {'file': ro + '.json', 'count': len(rows)}
        total += len(rows)
        log('  ✓ %s %d件 (%s)' % (PREFS[ro], len(rows), as_of))
    with open(idx_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    log('━━ 合計 %d件 / 基準日 %s ━━' % (total, index['asOf']))

if __name__ == '__main__':
    main()
