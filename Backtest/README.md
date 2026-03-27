# Backtest - Stochastics EA バックテスト検証

GOLDmicro（XM micro口座）の実データを使用したStochastics EAのバックテスト検証コードとレポートです。

## データ概要

- **銘柄**: GOLD/XAUUSD（XM micro口座）
- **時間軸**: 1分足
- **期間**: 2023年1月3日〜2026年2月27日（約3年2ヶ月）
- **本数**: 1,067,628本

---

## ディレクトリ構成

```
Backtest/
└── stoch_logic2/
    ├── backtest_logic2.py          # ロジック②バックテストエンジン（最新版）
    ├── backtest_logic1_original.py # 旧ロジック（4H/15M/1M足）バックテストエンジン
    ├── report_logic2.py            # ロジック②レポート生成スクリプト
    ├── report_logic2.md            # ロジック②検証レポート
    ├── chart_logic2.png            # ロジック②ダッシュボードチャート
    ├── compare_report.md           # 条件⑤変更前後比較レポート
    └── chart_compare.png           # 比較チャート
```

---

## ロジック比較

| 項目 | 旧ロジック | ロジック②（最新） |
|------|-----------|-----------------|
| 上位足 | 4H足 Stoch(60,3,3) | 4H足 Stoch(9,3,3) |
| 中位足 | 15M足 Stoch(9,3,3) | 1H足 Stoch(9,3,3) |
| エントリー足 | 1M足 GC/DC | 5M足 GC/DC |
| エグジット | 15M足 80/20到達 | 5M足 DC/GC |
| 時間帯フィルター | あり | なし |

## ロジック②検証結果サマリー（¥10,000スタート）

| 指標 | 旧ロジック | ロジック② |
|------|:----------:|:---------:|
| 総トレード数 | 26回 | **1,281回** |
| 勝率 | 61.5% | **68.1%** |
| PF | 1.30 | **1.61** |
| 総収益率 | +5.6% | **+286.2%** |
| 最大DD | 10.7% | 14.5% |
| 月平均回数 | 0.78回 | **33.5回** |

---

## ロジック②仕様

### ロング戦略
1. 4H足 Stoch(9,3,3) が **0〜20圏内でGC** → ロング戦略開始
2. 4H足 Stoch が **80〜100に到達してDC** が出るまでロング戦略継続
3. **4H足 %K > %D（上昇中）** かつ **1H足 %K > %D（上昇中）** の間、④⑤を繰り返す
4. 5M足 Stoch が **0〜20圏内でGC** → ロングエントリー
5. 5M足 Stoch が **80〜100圏内でDC** → イグジット
6. 日次+20%達成でトレード終了

### ショート戦略
1. 4H足 Stoch(9,3,3) が **80〜100圏内でDC** → ショート戦略開始
2. 4H足 Stoch が **0〜20に到達してGC** が出るまでショート戦略継続
3. **4H足 %K < %D（下降中）** かつ **1H足 %K < %D（下降中）** の間、④⑤を繰り返す
4. 5M足 Stoch が **80〜100圏内でDC** → ショートエントリー
5. 5M足 Stoch が **0〜20圏内でGC** → イグジット
6. 日次+20%達成でトレード終了

---

## データの配置（ZIP / 環境変数）

1分足 CSV（`date,time,open,high,low,close,volume` 形式）を **再帰的に** 読み込みます。

- **既定パス**: `Backtest/stoch_logic2/csv_data/`（`GOLD_XEM_mcr_20xx_all.zip` を解凍し、中の `.csv` をこのフォルダ以下に置く）
- **上書き**: 環境変数 `STOCH_CSV_DIR` にルートフォルダを指定
- **出力**: 既定は `Backtest/stoch_logic2/output/`。`STOCH_OUTPUT_DIR` で変更可

`backtest_logic2.py` は初期残高 **10万円** でロット **A=0.01 / B=0.1 / C=0.05** の比較を実行し、`output/compare_ABC_summary.md`（および `.csv`）、各シナリオの月次 `monthly_*.md` / `.csv` を生成します。

---

## 実行方法

```bash
cd Backtest/stoch_logic2

# 依存パッケージ
pip install pandas numpy matplotlib

# バックテスト（csv_data に CSV が必要）
python backtest_logic2.py

# レポート生成（別スクリプト）
python report_logic2.py
```

> **注意**: CSVデータ（XM micro口座の1分足）は容量の関係でリポジトリに含まれていません。
