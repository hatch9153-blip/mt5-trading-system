"""
KWM 口座向け ロジック③ 検証（XM GOLD 1分足・kwm エクスポート）

前提（環境変数で上書き可）:
- STOCH_SPREAD_USD: 往復スプレッド USD（micro 想定 0.30 より狭い値）
- STOCH_CONTRACT_SIZE: 損益スケール（1.0 lot = 100 oz 相当なら 100）

検証ロット: 0.01, 0.1（初期残高 10 万円）

実行: python verify_logic3_kwm.py
"""

from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- import より前に必ず設定 ---
os.environ["STOCH_CSV_DIR"] = os.environ.get(
    "STOCH_CSV_DIR", os.path.join(_SCRIPT_DIR, "csv_data", "xm_kwm")
)
os.environ["STOCH_OUTPUT_DIR"] = os.environ.get(
    "STOCH_OUTPUT_DIR", os.path.join(_SCRIPT_DIR, "output", "kwm_logic3")
)
# micro(0.30) より狭い口座想定。必要なら実行前に STOCH_SPREAD_USD を変更。
os.environ.setdefault("STOCH_SPREAD_USD", "0.10")
# 1 lot = 10 万通貨 / 100 oz クラスの標準ロット想定（MCR の 10 より大きい）
os.environ.setdefault("STOCH_CONTRACT_SIZE", "100")

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from backtest_logic2 import (  # noqa: E402
    OUTPUT_DIR,
    SPREAD_USD,
    CONTRACT_SIZE,
    load_data,
    analyze,
    ensure_output_dir,
)
from backtest_logic3 import run_backtest_logic3  # noqa: E402

import pandas as pd  # noqa: E402


def main():
    ensure_output_dir()
    print(f"CSV: {os.environ['STOCH_CSV_DIR']}")
    print(f"出力: {OUTPUT_DIR}")
    print(f"往復スプレッド: {SPREAD_USD} USD | CONTRACT_SIZE: {CONTRACT_SIZE}")

    df1m = load_data()
    init = 100_000
    lots = [0.01, 0.1]
    rows = []

    for lot in lots:
        print(f"\n--- ロジック③ KWM ロット {lot} ---")
        trades_df, final_bal = run_backtest_logic3(df1m, init, lot, verbose=True)
        stats = analyze(trades_df, init) if len(trades_df) else None

        tag = f"kwm_100k_{lot:.2f}".replace(".", "_")
        csv_path = os.path.join(OUTPUT_DIR, f"logic3_trades_{tag}.csv")
        trades_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"保存: {csv_path}")

        if stats:
            rows.append(
                {
                    "lot": lot,
                    "total_trades": stats["total_trades"],
                    "win_rate": round(stats["win_rate"], 2),
                    "profit_factor": round(stats["profit_factor"], 4)
                    if stats["profit_factor"] != float("inf")
                    else None,
                    "final_balance": round(stats["final_balance"], 2),
                    "total_return_pct": round(stats["total_return_pct"], 2),
                    "max_dd_pct": round(stats["max_dd_pct"], 2),
                    "positive_months": stats["positive_months"],
                    "months": len(stats["monthly"]),
                }
            )
            print(
                f"  総TR {stats['total_trades']} 勝率 {stats['win_rate']:.1f}% "
                f"PF {stats['profit_factor']:.2f} 最終 ¥{stats['final_balance']:,.0f} "
                f"収益率 {stats['total_return_pct']:+.1f}% 最大DD {stats['max_dd_pct']:.1f}%"
            )

    if rows:
        summ = pd.DataFrame(rows)
        summ_path = os.path.join(OUTPUT_DIR, "logic3_kwm_summary.csv")
        summ.to_csv(summ_path, index=False, encoding="utf-8-sig")
        print(f"\nサマリー: {summ_path}")

    md_lines = [
        "# ロジック③ 検証（KWM・狭スプレッド想定）",
        "",
        f"- データ: `csv_data/xm_kwm/`（KWM エクスポート 1 分足）",
        f"- 往復スプレッド: **{SPREAD_USD} USD**（`STOCH_SPREAD_USD`、micro 0.30 より狭い想定）",
        f"- `CONTRACT_SIZE`: **{CONTRACT_SIZE}**（`STOCH_CONTRACT_SIZE`、1 lot あたりの損益スケール）",
        f"- 初期残高: ¥{init:,}、ロット: **0.01** と **0.1**",
        "",
        "## サマリー",
        "",
        "| ロット | 総TR | 勝率% | PF | 最終残高 | 総収益率% | 最大DD% | プラス月 |",
        "|:--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        pf = r["profit_factor"]
        pf_s = f"{pf:.2f}" if pf is not None else "∞"
        md_lines.append(
            f"| {r['lot']} | {r['total_trades']} | {r['win_rate']:.1f} | {pf_s} | "
            f"¥{r['final_balance']:,.0f} | {r['total_return_pct']:+.1f}% | {r['max_dd_pct']:.1f}% | "
            f"{r['positive_months']}/{r['months']} |"
        )
    md_lines.extend(
        [
            "",
            "## 免責",
            "",
            "過去のシミュレーションは将来を保証しません。スプレッド・約定はモデルと実運用で異なります。",
        ]
    )
    md_path = os.path.join(OUTPUT_DIR, "verification_logic3_kwm.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"レポート: {md_path}")


if __name__ == "__main__":
    main()
