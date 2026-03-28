"""
ロジック③ KWM 検証の詳細を表形式で PDF 化する。

実行: python report_logic3_kwm_pdf.py

前提: verify_logic3_kwm.py と同じ環境変数（csv_data/xm_kwm、狭スプレッド等）。
既存の logic3_trades_kwm_*.csv があれば再バックテストせず読み込み（高速）。
"""

from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

os.environ.setdefault(
    "STOCH_CSV_DIR", os.path.join(_SCRIPT_DIR, "csv_data", "xm_kwm")
)
os.environ.setdefault(
    "STOCH_OUTPUT_DIR", os.path.join(_SCRIPT_DIR, "output", "kwm_logic3")
)
os.environ.setdefault("STOCH_SPREAD_USD", "0.10")
os.environ.setdefault("STOCH_CONTRACT_SIZE", "100")

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

mpl.rcParams["font.family"] = ["MS Gothic", "Yu Gothic", "Meiryo", "sans-serif"]
mpl.rcParams["axes.unicode_minus"] = False

from backtest_logic2 import (  # noqa: E402
    OUTPUT_DIR,
    SPREAD_USD,
    CONTRACT_SIZE,
    load_data,
    analyze,
    ensure_output_dir,
)
from backtest_logic3 import run_backtest_logic3  # noqa: E402

INITIAL = 100_000
LOTS = [0.01, 0.1]


def _table_page(pdf, title, rows, fontsize=7.5):
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.97)
    ax = fig.add_axes([0.03, 0.05, 0.94, 0.88])
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
    tbl.scale(1.0, 1.55)
    pdf.savefig(fig)
    plt.close(fig)


def _text_page(pdf, title, lines, fontsize=9):
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.97)
    ax = fig.add_axes([0.06, 0.06, 0.88, 0.86])
    ax.axis("off")
    y = 0.98
    line_h = 0.026
    for line in lines:
        ax.text(0.02, y, line, transform=ax.transAxes, fontsize=fontsize, va="top")
        y -= line_h
        if y < 0.06:
            pdf.savefig(fig)
            plt.close(fig)
            fig = plt.figure(figsize=(11.69, 8.27))
            fig.suptitle(title + "（続き）", fontsize=13, fontweight="bold", y=0.97)
            ax = fig.add_axes([0.06, 0.06, 0.88, 0.86])
            ax.axis("off")
            y = 0.98
    pdf.savefig(fig)
    plt.close(fig)


def _chunked_table_pages(pdf, title, rows, chunk_rows=26, fontsize=6.5):
    if not rows or len(rows) < 2:
        _table_page(pdf, title, rows, fontsize=fontsize + 0.5)
        return
    header = rows[0]
    body = rows[1:]
    for start in range(0, len(body), chunk_rows):
        chunk = [header] + body[start : start + chunk_rows]
        subt = f"{title} ({start + 1}–{start + len(chunk) - 1} / {len(body)})"
        _table_page(pdf, subt, chunk, fontsize=fontsize)


def _exit_reason_table(trades_df: pd.DataFrame) -> list[list[str]]:
    if len(trades_df) == 0 or "exit_reason" not in trades_df.columns:
        return [["理由", "回数", "損益(円)"]]
    g = trades_df.groupby("exit_reason", dropna=False).agg(
        n=("pnl_jpy", "count"), pnl=("pnl_jpy", "sum")
    )
    rows = [["イグジット理由", "回数", "損益(円)"]]
    for reason, r in g.iterrows():
        rows.append([str(reason), str(int(r["n"])), f"{r['pnl']:+,.0f}"])
    return rows


def _side_table(stats) -> list[list[str]]:
    if stats is None or stats.get("side") is None or len(stats["side"]) == 0:
        return [["方向", "回数", "損益(円)", "勝率%"]]
    rows = [["方向", "回数", "損益(円)", "勝率%"]]
    for side, r in stats["side"].iterrows():
        rows.append(
            [
                str(side),
                str(int(r["count"])),
                f"{r['pnl']:+,.0f}",
                f"{r['win_rate']:.1f}",
            ]
        )
    return rows


def _hourly_table(stats, max_rows: int = 24) -> list[list[str]]:
    if stats is None or stats.get("hourly") is None or len(stats["hourly"]) == 0:
        return [["時間(UTC)", "回数", "損益(円)", "勝率%"]]
    h = stats["hourly"].reset_index().head(max_rows)
    rows = [["時間(UTC)", "回数", "損益(円)", "勝率%"]]
    for _, r in h.iterrows():
        rows.append(
            [
                str(int(r["hour"])),
                str(int(r["count"])),
                f"{r['pnl']:+,.0f}",
                f"{r['win_rate']:.1f}",
            ]
        )
    return rows


def _monthly_detail_rows(stats) -> list[list[str]]:
    if stats is None or len(stats.get("monthly", [])) == 0:
        return [["月", "回数", "損益", "勝率%", "粗利", "粗損", "L回/損益", "S回/損益", "月DD%"]]
    m = stats["monthly"]
    rows = [
        [
            "月",
            "回数",
            "損益(円)",
            "勝率%",
            "粗利",
            "粗損",
            "L回",
            "L損益",
            "S回",
            "S損益",
            "月DD%",
        ]
    ]
    for ym, r in m.iterrows():
        dd_m = r.get("max_dd_pct_month", 0.0)
        if pd.isna(dd_m):
            dd_m = 0.0
        rows.append(
            [
                str(ym),
                str(int(r["count"])),
                f"{r['pnl']:+,.0f}",
                f"{r['win_rate']:.1f}",
                f"{r['gross_win']:+,.0f}",
                f"{r['gross_loss']:+,.0f}",
                str(int(r.get("long_count", 0))),
                f"{r.get('long_pnl', 0):+,.0f}",
                str(int(r.get("short_count", 0))),
                f"{r.get('short_pnl', 0):+,.0f}",
                f"{float(dd_m):.2f}",
            ]
        )
    return rows


def _summary_metrics_rows(stats) -> list[list[str]]:
    if not stats:
        return [["項目", "値"]]
    pf = stats["profit_factor"]
    pf_s = "∞" if pf == float("inf") else f"{pf:.2f}"
    items = [
        ("総トレード", str(stats["total_trades"])),
        ("勝ち / 負け", f"{stats['win_trades']} / {stats['loss_trades']}"),
        ("勝率", f"{stats['win_rate']:.2f}%"),
        ("プロフィットファクター", pf_s),
        ("平均利益(円)", f"{stats['avg_win']:,.1f}"),
        ("平均損失(円)", f"{stats['avg_loss']:,.1f}"),
        ("最大連勝", str(stats["max_consec_win"])),
        ("最大連敗", str(stats["max_consec_loss"])),
        ("最終残高", f"¥{stats['final_balance']:,.0f}"),
        ("総収益率", f"{stats['total_return_pct']:+.2f}%"),
        ("最大DD%", f"{stats['max_dd_pct']:.2f}%"),
        ("トレード/月(概算)", f"{stats['trades_per_month']:.2f}"),
        ("平均保有(分)", f"{stats['avg_duration_min']:.1f}"),
        ("プラス月数", f"{stats['positive_months']} / {len(stats['monthly'])}"),
    ]
    return [["項目", "値"]] + [[a, b] for a, b in items]


def _trades_csv_path(lot: float) -> str:
    tag = f"kwm_100k_{lot:.2f}".replace(".", "_")
    return os.path.join(OUTPUT_DIR, f"logic3_trades_{tag}.csv")


def main():
    ensure_output_dir()
    out_pdf = os.path.join(OUTPUT_DIR, "logic3_kwm_detailed_report.pdf")

    df_info = {"bars": 0, "start": "", "end": ""}
    all_stats = {}
    all_trades = {}

    have_both = all(os.path.isfile(_trades_csv_path(lot)) for lot in LOTS)

    if have_both:
        for lot in LOTS:
            path = _trades_csv_path(lot)
            trades_df = pd.read_csv(path)
            for c in ("entry_time", "exit_time"):
                trades_df[c] = pd.to_datetime(trades_df[c])
            print(f"読込: {path}")
            all_trades[lot] = trades_df
            all_stats[lot] = analyze(trades_df, INITIAL)
        t0 = min(all_trades[0.01]["entry_time"].min(), all_trades[0.1]["entry_time"].min())
        t1 = max(all_trades[0.01]["exit_time"].max(), all_trades[0.1]["exit_time"].max())
        df_info = {"bars": 0, "start": str(t0), "end": str(t1)}
        df_info["note"] = "（トレード CSV から期間表示。本数は verify_logic3_kwm 実行時の load_data と同じ）"
    else:
        df1m = load_data()
        df_info = {
            "bars": len(df1m),
            "start": str(df1m["dt"].iloc[0]),
            "end": str(df1m["dt"].iloc[-1]),
        }
        for lot in LOTS:
            print(f"バックテスト実行 ロット {lot} ...")
            trades_df, _ = run_backtest_logic3(df1m, INITIAL, lot, verbose=False)
            p = _trades_csv_path(lot)
            trades_df.to_csv(p, index=False, encoding="utf-8-sig")
            all_trades[lot] = trades_df
            all_stats[lot] = analyze(trades_df, INITIAL)

    with PdfPages(out_pdf) as pdf:
        bars_line = (
            f"データ: csv_data/xm_kwm（1分足 {df_info['bars']:,} 本）"
            if df_info.get("bars", 0)
            else "データ: csv_data/xm_kwm（トレード CSV から再集計）"
        )
        if df_info.get("note"):
            bars_line += f" {df_info['note']}"
        _text_page(
            pdf,
            "ロジック③ KWM 検証（詳細）",
            [
                "MT5-TRADING-SYSTEM / Stochastics(9,3,3) ロジック③",
                "",
                bars_line,
                f"期間: {df_info['start']} ～ {df_info['end']}",
                f"往復スプレッド: {SPREAD_USD} USD | CONTRACT_SIZE: {CONTRACT_SIZE}",
                f"初期残高: ¥{INITIAL:,} | ロット: 0.01 / 0.1",
                "",
                "※ 詳細は以下の表を参照（サマリー・月次・方向別・時間帯・イグジット理由）。",
            ],
        )

        cmp_rows = [
            [
                "ロット",
                "総TR",
                "勝率%",
                "PF",
                "最終残高",
                "収益率%",
                "最大DD%",
                "プラス月",
            ]
        ]
        for lot in LOTS:
            s = all_stats.get(lot)
            if not s:
                continue
            pf = s["profit_factor"]
            pf_s = "∞" if pf == float("inf") else f"{pf:.2f}"
            cmp_rows.append(
                [
                    str(lot),
                    str(s["total_trades"]),
                    f"{s['win_rate']:.2f}",
                    pf_s,
                    f"¥{s['final_balance']:,.0f}",
                    f"{s['total_return_pct']:+.2f}",
                    f"{s['max_dd_pct']:.2f}",
                    f"{s['positive_months']}/{len(s['monthly'])}",
                ]
            )
        _table_page(pdf, "ロット別サマリー比較", cmp_rows, fontsize=9)

        for lot in LOTS:
            s = all_stats.get(lot)
            t = all_trades.get(lot)
            if not s or t is None:
                continue
            label = f"ロット {lot}"

            _table_page(pdf, f"{label} — 主要指標", _summary_metrics_rows(s), fontsize=8.5)
            _table_page(pdf, f"{label} — ロング / ショート", _side_table(s), fontsize=9)
            _table_page(pdf, f"{label} — イグジット理由", _exit_reason_table(t), fontsize=9)
            _chunked_table_pages(
                pdf, f"{label} — エントリー時間帯別（UTC）", _hourly_table(s), chunk_rows=24
            )
            _chunked_table_pages(
                pdf, f"{label} — 月次詳細", _monthly_detail_rows(s), chunk_rows=22, fontsize=6
            )

        _text_page(
            pdf,
            "免責",
            [
                "過去のバックテスト・シミュレーションは将来の損益を保証しません。",
                "スプレッド・スリッページ・スワップはモデルと実運用で異なる場合があります。",
            ],
            fontsize=10,
        )

    print(f"PDF 保存: {out_pdf}")


if __name__ == "__main__":
    main()
