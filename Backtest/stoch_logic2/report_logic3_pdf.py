"""
ロジック③ 検証結果を PDF / Markdown にまとめる。
実行: python report_logic3_pdf.py
  環境変数 STOCH_CSV_DIR / STOCH_OUTPUT_DIR は backtest_logic2 と同じ
"""

import os
import sys

import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from backtest_logic2 import (
    OUTPUT_DIR,
    SCENARIOS,
    ensure_output_dir,
    load_data,
    analyze,
    run_backtest,
    write_monthly_md,
)
from backtest_logic3 import run_backtest_logic3, analyze_logic2_trade_frequency

# 日本語フォント（Windows）
mpl.rcParams["font.family"] = ["MS Gothic", "Yu Gothic", "Meiryo", "sans-serif"]
mpl.rcParams["axes.unicode_minus"] = False


def _table_page(pdf, title, rows, fontsize=8):
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.suptitle(title, fontsize=14, fontweight="bold", y=0.97)
    ax = fig.add_axes([0.04, 0.06, 0.92, 0.86])
    ax.axis("off")
    if not rows or len(rows) < 2:
        ax.text(0.5, 0.5, "データなし", ha="center", va="center", fontsize=12)
        pdf.savefig(fig)
        plt.close(fig)
        return
    tbl = ax.table(
        cellText=rows[1:],
        colLabels=rows[0],
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(fontsize)
    tbl.scale(1.0, 1.65)
    pdf.savefig(fig)
    plt.close(fig)


def _text_page(pdf, title, lines, fontsize=9):
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.suptitle(title, fontsize=14, fontweight="bold", y=0.97)
    ax = fig.add_axes([0.06, 0.06, 0.88, 0.86])
    ax.axis("off")
    y = 0.98
    line_h = 0.028
    for line in lines:
        ax.text(0.02, y, line, transform=ax.transAxes, fontsize=fontsize, va="top")
        y -= line_h
        if y < 0.05:
            pdf.savefig(fig)
            plt.close(fig)
            fig = plt.figure(figsize=(11.69, 8.27))
            fig.suptitle(title + "（続き）", fontsize=14, fontweight="bold", y=0.97)
            ax = fig.add_axes([0.06, 0.06, 0.88, 0.86])
            ax.axis("off")
            y = 0.98
    pdf.savefig(fig)
    plt.close(fig)


def _chunked_table_pages(pdf, title, rows, chunk_rows=28, fontsize=7):
    """行数が多い表を複数ページに分割。"""
    if not rows or len(rows) < 2:
        _table_page(pdf, title, rows, fontsize=fontsize)
        return
    header = rows[0]
    body = rows[1:]
    for start in range(0, len(body), chunk_rows):
        chunk = [header] + body[start : start + chunk_rows]
        subt = f"{title} ({start + 1}–{start + len(chunk) - 1} / {len(body)})"
        _table_page(pdf, subt, chunk, fontsize=fontsize)


def _write_verification_md(
    path,
    df_info,
    rows_compare,
    s3_a,
    freq,
    recommendations_lines,
):
    lines = [
        "# MT5-TRADING-SYSTEM　ロジック③検証（XM 実データ）",
        "",
        "**生成**: `report_logic3_pdf.py` 実行時",
        "",
        "## データ概要",
        "",
        "| 項目 | 値 |",
        "|:--|:--|",
        f"| 銘柄 | {df_info['symbol']} |",
        f"| 1分足本数 | {df_info['bars']:,} |",
        f"| 期間 | {df_info['start']} ～ {df_info['end']} |",
        "| エンジン | `backtest_logic3.py`（5M リサンプル後） |",
        "",
        "---",
        "",
        "## ロジック② vs ロジック③（初期残高 10 万円・ロット別）",
        "",
        "ロジック②: 1H/4H は %K と %D の向きのみ。5M ゾーンは 0～20 / 80～100（±5）。⑥ は日次 +20% 達成で当日停止。",
        "ロジック③: 1H/4H は **20～80 内** かつ上昇/下降（%K と %D の位置）。5M は **0～25 / 75～100**。⑥ は **SL 10pt**、**含み益で当日開始残高 +20%** で SL を建値に変更。",
        "",
        "| シナリオ | ロット | L2 総TR | L2 勝率 | L2 最終残高 | L2 収益率 | L3 総TR | L3 勝率 | L3 最終残高 | L3 収益率 | L3 最大DD |",
        "|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for r in rows_compare:
        lines.append(
            f"| {r['scenario']} | {r['lot']} | {r['l2_tr']} | {r['l2_wr']}% | ¥{r['l2_bal']:,.0f} | {r['l2_ret']:+.1f}% | "
            f"{r['l3_tr']} | {r['l3_wr']}% | ¥{r['l3_bal']:,.0f} | {r['l3_ret']:+.1f}% | {r['l3_dd']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "---",
            "",
            "## ロジック③（シナリオ A）サマリー",
            "",
        ]
    )
    if s3_a:
        lines.extend(
            [
                f"- 総トレード: {s3_a['total_trades']}",
                f"- 勝率: {s3_a['win_rate']:.1f}%",
                f"- PF: {s3_a['profit_factor']:.2f}",
                f"- 最終残高: ¥{s3_a['final_balance']:,.0f}",
                f"- 総収益率: {s3_a['total_return_pct']:+.1f}%",
                f"- 最大DD: {s3_a['max_dd_pct']:.1f}%",
                f"- プラス月: {s3_a['positive_months']} / {len(s3_a['monthly'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## ロジック②のトレード頻度（参考）",
            "",
            f"- ロジック② 総トレード（0.01 ロット試算）: {freq['logic2_trades']}",
            f"- 約 {freq['trades_per_month']:.1f} 回/月",
            "",
            "---",
            "",
            "## 今後の組み合わせ（提案）",
            "",
        ]
    )
    for line in recommendations_lines:
        lines.append(line)
    lines.extend(
        [
            "",
            "---",
            "",
            "## 免責",
            "",
            "過去のバックテストは将来を保証しません。スプレッド・スリッページ・スワップはモデルと実運用で異なります。",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    ensure_output_dir()
    csv_dir = os.environ.get(
        "STOCH_CSV_DIR", os.path.join(os.path.dirname(__file__), "csv_data", "xm_mcr")
    )
    os.environ["STOCH_CSV_DIR"] = csv_dir

    print(f"CSV: {csv_dir}")
    df1m = load_data()

    df_info = {
        "symbol": "GOLD（XM micro / MCR 系）",
        "bars": len(df1m),
        "start": str(df1m["dt"].iloc[0]),
        "end": str(df1m["dt"].iloc[-1]),
    }

    print("ロジック②・③ 全シナリオ実行中...")
    rows_compare = []
    results_l3 = {}
    results_l2 = {}

    for scenario_name, init, lot in SCENARIOS:
        t2, _ = run_backtest(df1m, init, lot, verbose=False)
        s2 = analyze(t2, init)
        t3, _ = run_backtest_logic3(df1m, init, lot, verbose=False)
        s3 = analyze(t3, init)
        results_l2[scenario_name] = (t2, s2)
        results_l3[scenario_name] = (t3, s3)

        def fmt(s, key, default="-"):
            if not s:
                return default
            if key == "pf" and s.get("profit_factor") == float("inf"):
                return "∞"
            return s[key]

        rows_compare.append(
            {
                "scenario": scenario_name,
                "lot": lot,
                "l2_tr": int(fmt(s2, "total_trades", "0")),
                "l2_wr": f"{s2['win_rate']:.1f}" if s2 else "-",
                "l2_bal": s2["final_balance"] if s2 else 0,
                "l2_ret": s2["total_return_pct"] if s2 else 0,
                "l3_tr": int(fmt(s3, "total_trades", "0")),
                "l3_wr": f"{s3['win_rate']:.1f}" if s3 else "-",
                "l3_bal": s3["final_balance"] if s3 else 0,
                "l3_ret": s3["total_return_pct"] if s3 else 0,
                "l3_dd": s3["max_dd_pct"] if s3 else 0,
            }
        )

    print("ロジック② 頻度分析...")
    freq = analyze_logic2_trade_frequency(df1m)

    _, s3_a = results_l3.get("A_100k_0.01", (None, None))
    t3_a, _ = results_l3.get("A_100k_0.01", (None, None))

    out_pdf = os.path.join(OUTPUT_DIR, "logic3_verification_report.pdf")
    out_md = os.path.join(OUTPUT_DIR, "verification_report_logic3_XM_mcr_2023_2026.md")
    out_csv = os.path.join(OUTPUT_DIR, "logic3_vs_logic2_scenarios.csv")

    pd.DataFrame(rows_compare).to_csv(out_csv, index=False, encoding="utf-8-sig")

    recommendations_lines = [
        "1. **反転の定義**: ロジック③はすでに 1H/4H で「中立帯内の方向」を要求。さらに絞るなら **5M と同様に 1H でも GC/DC を必須**にするとエントリーは減るがノイズ除去になる可能性がある（別途バックテストで検証）。",
        "2. **SL/TP**: ③ は **10pt SL + 建値移動**をモデル化済み。EA（`StochLogic2.mq5`）は現状ロジック②系で SL 固定なし。 **Python と EA を一致**させるなら、EA に同じ SL/トレールを実装するか、検証をロジック②ベースに揃える。",
        "3. **収益額を大きくする**: 同一ロジックでは **ロットと許容DD**が収益スケールの主因。②のレポート同様、**0.05～0.1** はバランス、**0.5～1.0** は DD と証拠金リスクが急増する点に注意。",
        "4. **月次トレード数**: ③ は 1H/4H の **20～80 フィルタ**で②より厳しく、トレード数は **おおむね減る**傾向。回数重視ならゾーン幅やフィルタを緩めるか②をベースに検討。",
    ]

    _write_verification_md(
        out_md,
        df_info,
        rows_compare,
        s3_a,
        freq,
        recommendations_lines,
    )

    compare_pdf_rows = [
        [
            "シナリオ",
            "ロット",
            "L2 TR",
            "L2 勝率",
            "L2 残高",
            "L2 収益%",
            "L3 TR",
            "L3 勝率",
            "L3 残高",
            "L3 収益%",
            "L3 DD%",
        ]
    ]
    for r in rows_compare:
        compare_pdf_rows.append(
            [
                r["scenario"],
                str(r["lot"]),
                str(r["l2_tr"]),
                str(r["l2_wr"]),
                f"¥{r['l2_bal']:,.0f}",
                f"{r['l2_ret']:+.1f}",
                str(r["l3_tr"]),
                str(r["l3_wr"]),
                f"¥{r['l3_bal']:,.0f}",
                f"{r['l3_ret']:+.1f}",
                f"{r['l3_dd']:.1f}",
            ]
        )

    logic2_analysis_lines = [
        "【ロジック②で月次トレード回数が「少なく」感じる主な要因】",
        "",
        "1) 4時間足のモードは 4H の GC/DC が出た区間だけ。",
        "2) 条件③で 1H・4H の向きが揃い、さらに 5M でゾーン内の GC/DC が必要。",
        "3) ポジション保有中は新規不可。",
        "4) 日次リスク（-10%・連敗 5、②では +20% 停止も）で当日停止する日がある。",
        "",
        f"参考: ロジック② 総トレード {freq['logic2_trades']}、約 {freq['trades_per_month']:.1f} 回/月。",
    ]

    with PdfPages(out_pdf) as pdf:
        _text_page(
            pdf,
            "MT5-TRADING-SYSTEM　ロジック③検証",
            [
                "データ: XM GOLD 1分足（csv_data/xm_mcr 配下）",
                "",
                "ロジック③ 概要:",
                "・1H/4H: %K が 20～80 内 かつ 上昇(ロング)/下降(ショート) でのみエントリー検討",
                "・4H ロング: 0～20 で GC 開始 → 75～100 で DC までモード",
                "・4H ショート: 80～100 で DC 開始 → 0～20 で GC までモード",
                "・5M ロング: 0～25 で GC、75～100 で DC イグジット",
                "・5M ショート: 75～100 で DC、0～25 で GC イグジット",
                "・SL 10pt、含み益で当日開始残高 +20% 到達で SL を建値へ",
                "",
                "ロジック② との違い: ②は 1H/4H 向きのみ・5M は 0～20/80～100（±5）。②の⑥は日次 +20% で当日停止。",
                "",
                f"期間: {df_info['start']} ～ {df_info['end']}（{df_info['bars']:,} 本）",
            ],
            fontsize=9,
        )

        _table_page(pdf, "ロジック② vs ロジック③（全シナリオ）", compare_pdf_rows, fontsize=7)

        if s3_a and len(s3_a["monthly"]) > 0:
            m = s3_a["monthly"].reset_index()
            m["ym"] = m["ym"].astype(str)
            monthly_rows = [["月", "回数", "損益(円)", "勝率%", "ロング回", "ショート回", "月内DD%"]]
            for _, r in m.iterrows():
                dd_m = r.get("max_dd_pct_month", 0.0)
                if pd.isna(dd_m):
                    dd_m = 0.0
                monthly_rows.append(
                    [
                        str(r["ym"]),
                        str(int(r["count"])),
                        f"{r['pnl']:+,.0f}",
                        f"{r['win_rate']:.1f}",
                        str(int(r.get("long_count", 0))),
                        str(int(r.get("short_count", 0))),
                        f"{float(dd_m):.2f}",
                    ]
                )
            _chunked_table_pages(pdf, "ロジック③ 月次（シナリオ A・0.01ロット）", monthly_rows)

        if results_l2.get("A_100k_0.01"):
            s2a = results_l2["A_100k_0.01"][1]
            if s2a and len(s2a["monthly"]) > 0:
                m2 = s2a["monthly"].reset_index()
                m2["ym"] = m2["ym"].astype(str)
                mrows = [["月", "回数", "損益(円)", "勝率%"]]
                for _, r in m2.iterrows():
                    mrows.append(
                        [
                            str(r["ym"]),
                            str(int(r["count"])),
                            f"{r['pnl']:+,.0f}",
                            f"{r['win_rate']:.1f}",
                        ]
                    )
                _chunked_table_pages(pdf, "ロジック② 月次（シナリオ A・参考）", mrows)

        _text_page(pdf, "ロジック②のトレード頻度（参考）", logic2_analysis_lines, fontsize=9)

        _text_page(
            pdf,
            "今後の組み合わせ（提案）",
            recommendations_lines,
            fontsize=8,
        )

        _text_page(
            pdf,
            "免責",
            [
                "過去のバックテスト結果は将来の損益を保証しません。",
                "スプレッド・スリッページはモデルと実運用で異なります。",
            ],
            fontsize=10,
        )

    if t3_a is not None:
        t3_a.to_csv(
            os.path.join(OUTPUT_DIR, "logic3_trades_A_100k_0.01.csv"),
            index=False,
            encoding="utf-8-sig",
        )

    if s3_a and len(s3_a["monthly"]) > 0:
        write_monthly_md(
            "logic3_A_100k_0.01",
            s3_a["monthly_detail"],
            os.path.join(OUTPUT_DIR, "monthly_logic3_A_100k_0.01.md"),
        )
        s3_a["monthly_detail"].to_csv(
            os.path.join(OUTPUT_DIR, "monthly_logic3_A_100k_0.01.csv"),
            encoding="utf-8-sig",
        )

    print(f"\nPDF:  {out_pdf}")
    print(f"MD:   {out_md}")
    print(f"CSV:  {out_csv}")


if __name__ == "__main__":
    main()
