# 医薬品分譲伝票

調剤薬局向けの医薬品分譲ソフト(ブラウザで動く単一HTML)。

- 分譲納品書(兼領収書・控付き A4)/ 分譲依頼書(向精神薬等分譲確認書付き)/ 分譲履歴 / 初期設定
- 薬価: 社会保険診療報酬支払基金「医薬品マスター」を毎週自動取込(`.github/workflows/yakka-update.yml`)
- データ: 各薬局のブラウザ内(localStorage `bunjo_v1`)のみ。サーバーには送信しない

## 構成
```
index.html                     アプリ本体
data/yakka.json                薬価マスター(自動生成・手で編集しない)
scripts/build-yakka-master.py  薬価マスター生成(python scripts/build-yakka-master.py [--force])
```
