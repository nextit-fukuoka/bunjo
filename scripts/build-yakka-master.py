# -*- coding: utf-8 -*-
"""
社会保険診療報酬支払基金「医薬品マスター」(y_ALLyyyymmdd.zip) から、
分譲ソフト用の軽量 薬価JSON を生成する。

出力: data/yakka.json
  { "ver": "20261001", "src": "y_ALL20261001.zip", "built": "2026-10-09",
    "cols": [...], "rows": [[code, name, kana, unit, price, mdk, kohatsu, form, haishi, gname], ...] }
  mdk    : 麻薬・毒薬・覚醒剤原料・向精神薬区分 (0なし 1麻薬 2毒薬 3覚醒剤原料 5向精神薬)
  kohatsu: 後発品 (0/1)
  form   : 剤形 (1内用 3その他 4注射 6外用 8歯科用)
  haishi : 経過措置期限 (yyyymmdd・0=なし)

使い方:
  python scripts/build-yakka-master.py           # 公式ページから最新版を自動検出して取得
  python scripts/build-yakka-master.py --force   # 版が同じでも作り直す
GitHub Actions(.github/workflows/yakka-update.yml)が毎週自動実行する。
※ 静的JSONを作るだけ。アプリのデータ(各薬局の localStorage)には触れない。
"""
import os, io, re, csv, sys, json, zipfile, datetime, unicodedata, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT  = os.path.join(ROOT, 'data', 'yakka.json')
PAGE = 'https://www.ssk.or.jp/seikyushiharai/tensuhyo/kihonmasta/kihonmasta_04.html'
UA   = {'User-Agent': 'Mozilla/5.0 (bunjo yakka updater)'}

def log(*a): print(*a, flush=True)

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()

def nk(s):
    # 検索用正規化: 半角カナ→全角・全角英数→半角(NFKC)
    return unicodedata.normalize('NFKC', s or '').strip()

def main():
    force = '--force' in sys.argv
    html = fetch(PAGE).decode('utf-8', 'replace')
    # ページ先頭(=最新)の全件ファイル
    m = re.search(r'href="([^"]*y_ALL(\d{8})\.zip)"', html)
    if not m:
        raise SystemExit('y_ALL*.zip のリンクが見つかりません(ページ構成変更?)')
    href, ver = m.group(1), m.group(2)
    url = urllib.request.urljoin(PAGE, href)

    if not force and os.path.exists(OUT):
        try:
            cur = json.load(open(OUT, encoding='utf-8')).get('ver')
            if cur == ver:
                log(f'最新版 {ver} 取込済み → 変更なし'); return
        except Exception:
            pass

    log('取得:', url)
    z = zipfile.ZipFile(io.BytesIO(fetch(url)))
    name = [n for n in z.namelist() if n.lower().endswith('.csv')][0]
    text = z.read(name).decode('cp932', 'replace')

    today = int(datetime.date.today().strftime('%Y%m%d'))
    rows, skipped, excl = [], 0, {'請求用コード(点数・減点・評価療養等)': 0, '(類)OTC類似薬の給付対象額': 0, '(選)選定療養の給付対象額': 0}
    for c in csv.reader(io.StringIO(text)):
        if len(c) < 38 or c[1] != 'Y':
            continue
        # ⚠ 分譲に使うのは「薬価」そのもの。薬価でないレコードは除外する
        #   金額種別(c[10])≠1 … 歯科の点数・薬剤料減点などの請求用コード
        #   名称末尾「（類）」 … OTC類似薬の保険給付対象額(薬価×3/4)
        #   名称末尾「（選）」 … 長期収載品の選定療養における保険給付対象額
        #   (2026-10 厚労省 薬価基準収載品目リストと全件照合し、上記以外は全品目一致を確認)
        if c[10] != '1' or not c[31].strip():               # 薬価基準コードが無い=評価療養等の請求用コード
            excl['請求用コード(点数・減点・評価療養等)'] += 1; continue
        tail = nk(c[4]).rstrip()
        if tail.endswith('(類)'):
            excl['(類)OTC類似薬の給付対象額'] += 1; continue
        if tail.endswith('(選)'):
            excl['(選)選定療養の給付対象額'] += 1; continue
        haishi = int(c[30] or 0)                           # 廃止年月日
        if haishi and haishi != 99999999 and haishi < today:
            skipped += 1; continue
        keika = int(c[33] or 0) if c[33].isdigit() else 0  # 経過措置年月日(この日まで使用可)
        if keika and keika < today:                        # 経過措置期限切れは除外
            skipped += 1; continue
        haishi = keika
        try:
            price = float(c[11] or 0)
        except ValueError:
            price = 0
        gname = c[37].replace('【般】', '') if len(c) > 37 else ''
        rows.append([
            c[2],                      # 医薬品コード
            nk(c[4]),                  # 名称
            nk(c[6]),                  # カナ
            nk(c[9]),                  # 単位
            round(price, 2),           # 薬価
            int(c[13] or 0),           # 麻毒覚向
            int(c[16] or 0),           # 後発品
            int(c[27] or 0),           # 剤形
            haishi,                    # 経過措置期限
            nk(gname),                 # 一般名
        ])
    rows.sort(key=lambda r: r[2])
    out = {
        'ver': ver,
        'src': os.path.basename(href),
        'url': url,
        'built': datetime.date.today().isoformat(),
        'cols': ['code', 'name', 'kana', 'unit', 'price', 'mdk', 'kohatsu', 'form', 'haishi', 'gname'],
        'rows': rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    log(f'出力: {OUT}  版={ver} 件数={len(rows)} (期限切れ除外 {skipped} / 薬価でないレコード除外 {excl})  {os.path.getsize(OUT)//1024}KB')

if __name__ == '__main__':
    main()
