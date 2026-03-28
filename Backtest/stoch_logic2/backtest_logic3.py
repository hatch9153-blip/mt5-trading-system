"""
ロジック③ バックテスト
====================
全時間足 Stochastics(9,3,3)

ロング: 1H・4H がともに %K∈[20,80] かつ %K>%D（上昇）のときのみロング検討
ショート: 1H・4H がともに %K∈[20,80] かつ %K<%D（下降）のときのみショート検討

4H ロング: ① 0～20 で GC → ② 75～100 で DC までロングモード
4H ショート: ① 80～100 で DC → ② 0～20 で GC までショートモード
③ 4H・1H 上昇/下降中に ④⑤ 繰り返し
④ 5M: ロング GC 0～25 / ショート DC 75～100 でエントリー
⑤ 5M: ロング DC 75～100 / ショート GC 0～25 でイグジット
⑥ SL 10pt、当日開始残高+20%到達で SL を建値に変更（含み益で判定）

※ 仕様の「80～1000」は 80～100 の誤記と解釈
"""

import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from backtest_logic2 import (
    OUTPUT_DIR,
    SPREAD_USD,
    USD_JPY,
    CONTRACT_SIZE,
    MAX_DAILY_LOSS_PCT,
    MAX_CONSECUTIVE_LOSSES,
    calc_stoch,
    load_data,
    resample,
    analyze,
    ensure_output_dir,
    run_backtest as run_backtest_logic2,
)

# --- ロジック③ 定数 ---
SL_POINTS_USD = 10.0
ZONE_4H_LONG_START = 20.0
ZONE_4H_LONG_END_LO = 75.0
ZONE_4H_LONG_END_HI = 100.0
ZONE_4H_SHORT_START_LO = 80.0
ZONE_4H_SHORT_START_HI = 100.0
ZONE_4H_SHORT_END = 20.0

ZONE_H_NEUTRAL_LO = 20.0
ZONE_H_NEUTRAL_HI = 80.0

ZONE_5M_LONG_ENTRY = 25.0
ZONE_5M_LONG_EXIT_LO = 75.0
# 仕様: ショートは 5M で 75～100 内の DC（「80～1000」は 75～100 の誤記と解釈）
ZONE_5M_SHORT_ENTRY_LO = 75.0
ZONE_5M_SHORT_ENTRY_HI = 100.0
ZONE_5M_SHORT_EXIT = 25.0


def _in_range(x, lo, hi):
    return lo <= x <= hi


def _h_filter_long(k, d):
    return _in_range(k, ZONE_H_NEUTRAL_LO, ZONE_H_NEUTRAL_HI) and k > d


def _h_filter_short(k, d):
    return _in_range(k, ZONE_H_NEUTRAL_LO, ZONE_H_NEUTRAL_HI) and k < d


def run_backtest_logic3(df1m, initial_balance, lot_size, verbose=True):
    if verbose:
        print(f"\n{'='*65}\nロジック③ 初期資金 ¥{initial_balance:,} ロット {lot_size}\n{'='*65}")

    df5m = resample(df1m, "5min")
    df1h = resample(df1m, "1h")
    df4h = resample(df1m, "4h")

    k5m, d5m = calc_stoch(df5m)
    k1h, d1h = calc_stoch(df1h)
    k4h, d4h = calc_stoch(df4h)

    df5m = df5m.copy()
    df5m["k5m"] = k5m
    df5m["d5m"] = d5m

    df1h_s = df1h[["dt"]].copy()
    df1h_s["k1h"] = k1h
    df1h_s["d1h"] = d1h

    df4h_s = df4h[["dt"]].copy()
    df4h_s["k4h"] = k4h
    df4h_s["d4h"] = d4h

    df5m = pd.merge_asof(
        df5m.sort_values("dt"), df1h_s.sort_values("dt"), on="dt", direction="backward"
    )
    df5m = pd.merge_asof(
        df5m.sort_values("dt"), df4h_s.sort_values("dt"), on="dt", direction="backward"
    )
    df5m = df5m.reset_index(drop=True)

    balance = float(initial_balance)
    trades = []

    in_position = False
    entry_price = 0.0
    entry_time = None
    position_side = None
    sl_price = 0.0

    strategy_mode = None
    prev_k4h = np.nan
    prev_d4h = np.nan

    current_date = None
    day_start_balance = balance
    consecutive_losses = 0
    day_blocked = False

    n = len(df5m)
    if verbose:
        print(f"  5M行数: {n:,} シミュレーション中...")

    for i in range(50, n):
        row = df5m.iloc[i]
        dt = row["dt"]

        if pd.isna(row["k4h"]) or pd.isna(row["k1h"]) or pd.isna(row["k5m"]):
            prev_k4h = row["k4h"] if not pd.isna(row["k4h"]) else prev_k4h
            prev_d4h = row["d4h"] if not pd.isna(row["d4h"]) else prev_d4h
            continue

        d = dt.date()
        if d != current_date:
            current_date = d
            day_start_balance = balance
            consecutive_losses = 0
            day_blocked = False

        k4h_now = row["k4h"]
        d4h_now = row["d4h"]

        if not pd.isna(prev_k4h) and not pd.isna(prev_d4h):
            gc_4h_long = (
                (prev_k4h <= prev_d4h)
                and (k4h_now > d4h_now)
                and (k4h_now <= ZONE_4H_LONG_START)
            )
            dc_4h_long_end = (
                (prev_k4h >= prev_d4h)
                and (k4h_now < d4h_now)
                and _in_range(k4h_now, ZONE_4H_LONG_END_LO, ZONE_4H_LONG_END_HI)
            )
            dc_4h_short = (
                (prev_k4h >= prev_d4h)
                and (k4h_now < d4h_now)
                and _in_range(k4h_now, ZONE_4H_SHORT_START_LO, ZONE_4H_SHORT_START_HI)
            )
            gc_4h_short_end = (
                (prev_k4h <= prev_d4h)
                and (k4h_now > d4h_now)
                and (k4h_now <= ZONE_4H_SHORT_END)
            )

            if gc_4h_long:
                strategy_mode = "long"
            elif dc_4h_short:
                strategy_mode = "short"

            if strategy_mode == "long" and dc_4h_long_end:
                strategy_mode = None
            if strategy_mode == "short" and gc_4h_short_end:
                strategy_mode = None

        prev_k4h = k4h_now
        prev_d4h = d4h_now

        if in_position:
            k5m_now = row["k5m"]
            d5m_now = row["d5m"]
            prev_row = df5m.iloc[i - 1]
            pk5m = prev_row["k5m"]
            pd5m_val = prev_row["d5m"]
            low = row["low"]
            high = row["high"]
            close = row["close"]

            exit_signal = False
            exit_reason = ""
            exit_price = close

            if position_side == "long":
                float_usd = (close - entry_price) * CONTRACT_SIZE * lot_size
                equity_jpy = balance + float_usd * USD_JPY
                if equity_jpy >= day_start_balance * 1.2:
                    sl_price = entry_price

                if low <= sl_price:
                    exit_signal = True
                    exit_reason = "SL_or_BE"
                    exit_price = min(sl_price, close)

                if not exit_signal:
                    dc_5m = (
                        not pd.isna(pk5m)
                        and not pd.isna(pd5m_val)
                        and (pk5m >= pd5m_val)
                        and (k5m_now < d5m_now)
                        and (k5m_now >= ZONE_5M_LONG_EXIT_LO)
                    )
                    if dc_5m:
                        exit_signal = True
                        exit_reason = "5M_DC"
                        exit_price = close

            else:
                float_usd = (entry_price - close) * CONTRACT_SIZE * lot_size
                equity_jpy = balance + float_usd * USD_JPY
                if equity_jpy >= day_start_balance * 1.2:
                    sl_price = entry_price

                if high >= sl_price:
                    exit_signal = True
                    exit_reason = "SL_or_BE"
                    exit_price = max(sl_price, close)

                if not exit_signal:
                    gc_5m = (
                        not pd.isna(pk5m)
                        and not pd.isna(pd5m_val)
                        and (pk5m <= pd5m_val)
                        and (k5m_now > d5m_now)
                        and (k5m_now <= ZONE_5M_SHORT_EXIT)
                    )
                    if gc_5m:
                        exit_signal = True
                        exit_reason = "5M_GC"
                        exit_price = close

            if exit_signal:
                if position_side == "long":
                    pnl_usd = (exit_price - entry_price - SPREAD_USD) * CONTRACT_SIZE * lot_size
                else:
                    pnl_usd = (entry_price - exit_price - SPREAD_USD) * CONTRACT_SIZE * lot_size
                pnl_jpy = pnl_usd * USD_JPY
                balance += pnl_jpy

                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": dt,
                        "side": position_side,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl_usd": round(pnl_usd, 4),
                        "pnl_jpy": round(pnl_jpy, 2),
                        "balance": round(balance, 2),
                        "duration_min": (dt - entry_time).total_seconds() / 60,
                        "exit_reason": exit_reason,
                        "k4h_at_entry": k4h_now,
                        "k1h_at_entry": row["k1h"],
                        "k5m_at_entry": k5m_now,
                    }
                )

                consecutive_losses = 0 if pnl_jpy > 0 else consecutive_losses + 1
                in_position = False

                if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                    day_blocked = True
                if balance <= day_start_balance * (1 - MAX_DAILY_LOSS_PCT):
                    day_blocked = True
                continue

        if in_position or day_blocked:
            continue
        if strategy_mode is None:
            continue

        k5m_now = row["k5m"]
        d5m_now = row["d5m"]
        k1h_now = row["k1h"]
        d1h_now = row["d1h"]

        prev_row = df5m.iloc[i - 1]
        pk5m = prev_row["k5m"]
        pd5m_val = prev_row["d5m"]

        if pd.isna(pk5m) or pd.isna(pd5m_val):
            continue

        k4h_now = row["k4h"]
        d4h_now = row["d4h"]

        if strategy_mode == "long":
            if not (
                _h_filter_long(k4h_now, d4h_now) and _h_filter_long(k1h_now, d1h_now)
            ):
                continue
            if not ((k4h_now > d4h_now) and (k1h_now > d1h_now)):
                continue

            gc_5m_entry = (
                (pk5m <= pd5m_val)
                and (k5m_now > d5m_now)
                and (k5m_now <= ZONE_5M_LONG_ENTRY)
            )
            if gc_5m_entry:
                entry_price = row["close"] + SPREAD_USD
                in_position = True
                entry_time = dt
                position_side = "long"
                sl_price = entry_price - SL_POINTS_USD

        elif strategy_mode == "short":
            if not (
                _h_filter_short(k4h_now, d4h_now) and _h_filter_short(k1h_now, d1h_now)
            ):
                continue
            if not ((k4h_now < d4h_now) and (k1h_now < d1h_now)):
                continue

            dc_5m_entry = (
                (pk5m >= pd5m_val)
                and (k5m_now < d5m_now)
                and _in_range(k5m_now, ZONE_5M_SHORT_ENTRY_LO, ZONE_5M_SHORT_ENTRY_HI)
            )
            if dc_5m_entry:
                entry_price = row["close"] - SPREAD_USD
                in_position = True
                entry_time = dt
                position_side = "short"
                sl_price = entry_price + SL_POINTS_USD

        if verbose and i % 50000 == 0 and i > 0:
            print(
                f"  進捗: {i/n*100:.1f}% | トレード数: {len(trades)} | 残高: ¥{balance:,.0f}"
            )

    if in_position:
        last = df5m.iloc[-1]
        ep = last["close"]
        pnl_usd = (
            (ep - entry_price - SPREAD_USD) * CONTRACT_SIZE * lot_size
            if position_side == "long"
            else (entry_price - ep - SPREAD_USD) * CONTRACT_SIZE * lot_size
        )
        pnl_jpy = pnl_usd * USD_JPY
        balance += pnl_jpy
        trades.append(
            {
                "entry_time": entry_time,
                "exit_time": last["dt"],
                "side": position_side,
                "entry_price": entry_price,
                "exit_price": ep,
                "pnl_usd": round(pnl_usd, 4),
                "pnl_jpy": round(pnl_jpy, 2),
                "balance": round(balance, 2),
                "duration_min": (last["dt"] - entry_time).total_seconds() / 60,
                "exit_reason": "force_close",
                "k4h_at_entry": np.nan,
                "k1h_at_entry": np.nan,
                "k5m_at_entry": np.nan,
            }
        )

    trades_df = pd.DataFrame(trades)
    if verbose:
        print(f"\n  完了: {len(trades_df)}トレード | 最終残高: ¥{balance:,.0f}")
    return trades_df, balance


def analyze_logic2_trade_frequency(df1m):
    """
    ロジック②のトレード頻度の目安（同じデータ・100k/0.01）。
    """
    t2, _ = run_backtest_logic2(df1m, 100_000, 0.01, verbose=False)
    n_tr = len(t2)
    df5m = resample(df1m, "5min")
    n = len(df5m)
    total_days = (df5m["dt"].max() - df5m["dt"].min()).days + 1
    months = total_days / 30.0

    return {
        "logic2_trades": n_tr,
        "bars_5m": n,
        "trades_per_month": n_tr / max(months, 0.01),
        "avg_5m_bars_per_trade": n / max(n_tr, 1),
        "avg_minutes_between_trades": (n * 5) / max(n_tr, 1),
    }


if __name__ == "__main__":
    ensure_output_dir()
    df1m = load_data()
    init = 100_000
    lot = 0.01

    print("ロジック② トレード頻度の要因（概算）...")
    freq = analyze_logic2_trade_frequency(df1m)
    for k, v in freq.items():
        print(f"  {k}: {v}")

    trades_df, final_bal = run_backtest_logic3(df1m, init, lot, verbose=True)
    stats = analyze(trades_df, init)
    if stats:
        print("\n--- ロジック③ サマリー ---")
        print(f"総トレード: {stats['total_trades']}  勝率: {stats['win_rate']:.1f}%  PF: {stats['profit_factor']:.2f}")
        print(f"最終残高: ¥{stats['final_balance']:,.0f}  総収益率: {stats['total_return_pct']:+.1f}%  最大DD: {stats['max_dd_pct']:.1f}%")

    out_csv = os.path.join(OUTPUT_DIR, "logic3_trades.csv")
    trades_df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"\n保存: {out_csv}")
