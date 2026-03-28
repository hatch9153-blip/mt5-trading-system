"""
Stochastics EA バックテストエンジン ロジック②
==============================================
全時間足: Stochastics(9,3,3)

データ配置: 環境変数 STOCH_CSV_DIR または 本スクリプト直下の csv_data/ に
GOLD の 1分足 CSV を再帰配置（ZIP 解凍先をここに合わせる）。
出力: 環境変数 STOCH_OUTPUT_DIR または 本スクリプト直下の output/

シナリオ: 初期残高 10万円でロット A=0.01, B=0.10, C=0.05, D=0.50, E=1.00 を比較。
"""

import pandas as pd
import numpy as np
import glob
import os
import pickle
import csv
import warnings
import sys
warnings.filterwarnings('ignore')

# Windows コンソール (cp932) で円記号などを print するため
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ===== パス（環境変数で上書き可）=====
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.environ.get('STOCH_CSV_DIR', os.path.join(_SCRIPT_DIR, 'csv_data'))
OUTPUT_DIR = os.environ.get('STOCH_OUTPUT_DIR', os.path.join(_SCRIPT_DIR, 'output'))

# 10万円スタート・ロット別
SCENARIOS = [
    ('A_100k_0.01', 100_000, 0.01),
    ('B_100k_0.10', 100_000, 0.10),
    ('C_100k_0.05', 100_000, 0.05),
    ('D_100k_0.50', 100_000, 0.50),
    ('E_100k_1.00', 100_000, 1.00),
]

USD_JPY       = 150.0
# 1ロットあたりの USD 損益スケール（ブローカー仕様に合わせ env で上書き可）
CONTRACT_SIZE = float(os.environ.get("STOCH_CONTRACT_SIZE", "10"))
# 往復相当のスプレッド（USD）。狭スプレッド口座は STOCH_SPREAD_USD で上書き。
SPREAD_USD    = float(os.environ.get("STOCH_SPREAD_USD", "0.30"))

K_PERIOD = 9
D_PERIOD = 3
SLOWING  = 3

OVERSOLD   = 20.0
OVERBOUGHT = 80.0

DAILY_PROFIT_TARGET_PCT = 0.20
MAX_DAILY_LOSS_PCT      = 0.10
MAX_CONSECUTIVE_LOSSES  = 5

# 日次 +20% 達成で当日トレード停止（⑥）。False で同条件のみこの制限を外す。
USE_DAILY_PROFIT_STOP = True


def calc_stoch(df, k_period=9, slowing=3, d_period=3):
    low_min  = df['low'].rolling(k_period).min()
    high_max = df['high'].rolling(k_period).max()
    raw_k = 100.0 * (df['close'] - low_min) / (high_max - low_min + 1e-10)
    k = raw_k.rolling(slowing).mean()
    d = k.rolling(d_period).mean()
    return k.values, d.values


def load_data(csv_dir=None):
    root = csv_dir or CSV_DIR
    print(f"CSVデータ読み込み中... ({root})")
    pattern = os.path.join(root, "**", "*.csv")
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        raise FileNotFoundError(
            f"CSV が見つかりません: {pattern}\n"
            "ZIP を解凍し、1分足 CSV をこのフォルダ配下に置くか、"
            "環境変数 STOCH_CSV_DIR を設定してください。"
        )
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, header=None,
                             names=['date', 'time', 'open', 'high', 'low', 'close', 'volume'])
            df['dt'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%Y.%m.%d %H:%M')
            dfs.append(df[['dt', 'open', 'high', 'low', 'close', 'volume']])
        except Exception as e:
            print(f"  スキップ: {f}: {e}")
    if not dfs:
        raise RuntimeError("読み込めた CSV がありません。")
    df1m = pd.concat(dfs).sort_values('dt').drop_duplicates('dt').reset_index(drop=True)
    print(f"  1M: {len(df1m):,}本 ({df1m['dt'].iloc[0]} 〜 {df1m['dt'].iloc[-1]})")
    return df1m


def resample(df1m, rule):
    df = df1m.set_index('dt').resample(rule).agg(
        open=('open', 'first'), high=('high', 'max'),
        low=('low', 'min'), close=('close', 'last'), volume=('volume', 'sum')
    ).dropna().reset_index()
    return df


def run_backtest(
    df1m,
    initial_balance,
    lot_size,
    use_daily_profit_stop=None,
    verbose=True,
):
    """
    use_daily_profit_stop: None のときはグローバル USE_DAILY_PROFIT_STOP を使用。
    False のときは「当日 +20%」による day_blocked を付けない（連敗・-10% は従来通り）。
    """
    if use_daily_profit_stop is None:
        use_daily_profit_stop = USE_DAILY_PROFIT_STOP

    if verbose:
        print(f"\n{'='*65}")
        print(
            f"バックテスト [ロジック②]: 初期資金 ¥{initial_balance:,} ロット {lot_size} "
            f"日次+20%停止={'ON' if use_daily_profit_stop else 'OFF'}"
        )
        print(f"{'='*65}")

        print("リサンプリング中...")
    df5m = resample(df1m, '5min')
    df1h = resample(df1m, '1h')
    df4h = resample(df1m, '4h')

    if verbose:
        print("Stochastics計算中...")
    k5m, d5m = calc_stoch(df5m)
    k1h, d1h = calc_stoch(df1h)
    k4h, d4h = calc_stoch(df4h)

    df5m = df5m.copy()
    df5m['k5m'] = k5m
    df5m['d5m'] = d5m

    df1h_s = df1h[['dt']].copy()
    df1h_s['k1h'] = k1h
    df1h_s['d1h'] = d1h

    df4h_s = df4h[['dt']].copy()
    df4h_s['k4h'] = k4h
    df4h_s['d4h'] = d4h

    df5m = pd.merge_asof(df5m.sort_values('dt'), df1h_s.sort_values('dt'),
                         on='dt', direction='backward')
    df5m = pd.merge_asof(df5m.sort_values('dt'), df4h_s.sort_values('dt'),
                         on='dt', direction='backward')
    df5m = df5m.reset_index(drop=True)
    if verbose:
        print(f"  マージ完了: {len(df5m):,}行（5M足）")

    balance = float(initial_balance)
    trades = []

    in_position = False
    entry_price = 0.0
    entry_time = None
    position_side = None

    strategy_mode = None
    prev_k4h = np.nan
    prev_d4h = np.nan

    current_date = None
    day_start_balance = balance
    consecutive_losses = 0
    day_blocked = False

    n = len(df5m)
    if verbose:
        print("シミュレーション実行中...")

    for i in range(50, n):
        row = df5m.iloc[i]
        dt = row['dt']

        if pd.isna(row['k4h']) or pd.isna(row['k1h']) or pd.isna(row['k5m']):
            prev_k4h = row['k4h'] if not pd.isna(row['k4h']) else prev_k4h
            prev_d4h = row['d4h'] if not pd.isna(row['d4h']) else prev_d4h
            continue

        d = dt.date()
        if d != current_date:
            current_date = d
            day_start_balance = balance
            consecutive_losses = 0
            day_blocked = False

        k4h_now = row['k4h']
        d4h_now = row['d4h']

        if not pd.isna(prev_k4h) and not pd.isna(prev_d4h):
            gc_4h = (prev_k4h <= prev_d4h) and (k4h_now > d4h_now) and (k4h_now <= OVERSOLD + 5)
            dc_4h = (prev_k4h >= prev_d4h) and (k4h_now < d4h_now) and (k4h_now >= OVERBOUGHT - 5)

            if gc_4h:
                strategy_mode = 'long'
            elif dc_4h:
                strategy_mode = 'short'

            if strategy_mode == 'long' and dc_4h:
                strategy_mode = None
            if strategy_mode == 'short' and gc_4h:
                strategy_mode = None

        prev_k4h = k4h_now
        prev_d4h = d4h_now

        if in_position:
            k5m_now = row['k5m']
            d5m_now = row['d5m']
            prev_row = df5m.iloc[i - 1]
            pk5m = prev_row['k5m']
            pd5m_val = prev_row['d5m']

            exit_signal = False
            exit_reason = ''

            if position_side == 'long':
                dc_5m = (not pd.isna(pk5m) and not pd.isna(pd5m_val) and
                         pk5m >= pd5m_val and k5m_now < d5m_now and
                         k5m_now >= OVERBOUGHT - 5)
                if dc_5m:
                    exit_signal = True
                    exit_reason = '5M_DC'
            elif position_side == 'short':
                gc_5m = (not pd.isna(pk5m) and not pd.isna(pd5m_val) and
                         pk5m <= pd5m_val and k5m_now > d5m_now and
                         k5m_now <= OVERSOLD + 5)
                if gc_5m:
                    exit_signal = True
                    exit_reason = '5M_GC'

            if exit_signal:
                exit_price = row['close']
                if position_side == 'long':
                    pnl_usd = (exit_price - entry_price - SPREAD_USD) * CONTRACT_SIZE * lot_size
                else:
                    pnl_usd = (entry_price - exit_price - SPREAD_USD) * CONTRACT_SIZE * lot_size
                pnl_jpy = pnl_usd * USD_JPY
                balance += pnl_jpy

                trades.append({
                    'entry_time': entry_time,
                    'exit_time': dt,
                    'side': position_side,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl_usd': round(pnl_usd, 4),
                    'pnl_jpy': round(pnl_jpy, 2),
                    'balance': round(balance, 2),
                    'duration_min': (dt - entry_time).total_seconds() / 60,
                    'exit_reason': exit_reason,
                    'k4h_at_entry': k4h_now,
                    'k1h_at_entry': row['k1h'],
                    'k5m_at_entry': k5m_now,
                })

                consecutive_losses = 0 if pnl_jpy > 0 else consecutive_losses + 1
                in_position = False

                if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                    day_blocked = True
                if use_daily_profit_stop and balance >= day_start_balance * (1 + DAILY_PROFIT_TARGET_PCT):
                    day_blocked = True
                if balance <= day_start_balance * (1 - MAX_DAILY_LOSS_PCT):
                    day_blocked = True
                continue

        if in_position or day_blocked:
            continue
        if strategy_mode is None:
            continue

        k5m_now = row['k5m']
        d5m_now = row['d5m']
        k1h_now = row['k1h']
        d1h_now = row['d1h']

        if i < 1:
            continue
        prev_row = df5m.iloc[i - 1]
        pk5m = prev_row['k5m']
        pd5m_val = prev_row['d5m']
        pk1h = prev_row['k1h']

        if pd.isna(pk5m) or pd.isna(pd5m_val) or pd.isna(pk1h):
            continue

        k1h_rising = k1h_now > d1h_now
        k1h_falling = k1h_now < d1h_now
        k4h_rising = k4h_now > d4h_now
        k4h_falling = k4h_now < d4h_now

        if strategy_mode == 'long':
            if not (k4h_rising and k1h_rising):
                continue
            gc_5m_entry = (pk5m <= pd5m_val and k5m_now > d5m_now and
                           k5m_now <= OVERSOLD + 5)
            if gc_5m_entry:
                entry_price = row['close'] + SPREAD_USD
                in_position = True
                entry_time = dt
                position_side = 'long'

        elif strategy_mode == 'short':
            if not (k4h_falling and k1h_falling):
                continue
            dc_5m_entry = (pk5m >= pd5m_val and k5m_now < d5m_now and
                           k5m_now >= OVERBOUGHT - 5)
            if dc_5m_entry:
                entry_price = row['close'] - SPREAD_USD
                in_position = True
                entry_time = dt
                position_side = 'short'

        if verbose and i % 50000 == 0 and i > 0:
            print(f"  進捗: {i/n*100:.1f}% | トレード数: {len(trades)} | 残高: ¥{balance:,.0f}")

    if in_position:
        last = df5m.iloc[-1]
        ep = last['close']
        pnl_usd = (ep - entry_price - SPREAD_USD) * CONTRACT_SIZE * lot_size \
                  if position_side == 'long' \
                  else (entry_price - ep - SPREAD_USD) * CONTRACT_SIZE * lot_size
        pnl_jpy = pnl_usd * USD_JPY
        balance += pnl_jpy
        trades.append({
            'entry_time': entry_time, 'exit_time': last['dt'],
            'side': position_side, 'entry_price': entry_price, 'exit_price': ep,
            'pnl_usd': round(pnl_usd, 4), 'pnl_jpy': round(pnl_jpy, 2),
            'balance': round(balance, 2),
            'duration_min': (last['dt'] - entry_time).total_seconds() / 60,
            'exit_reason': 'force_close',
            'k4h_at_entry': np.nan, 'k1h_at_entry': np.nan, 'k5m_at_entry': np.nan,
        })

    trades_df = pd.DataFrame(trades)
    if verbose:
        print(f"\n  完了: {len(trades_df)}トレード | 最終残高: ¥{balance:,.0f}")
    return trades_df, balance


def compare_daily_profit_stop(df1m, initial_balance=10_000, lot_size=0.01):
    """
    report_logic2.md と同じ ¥10,000 / 0.01 ロットで、
    ⑥ 日次+20% 停止の ON / OFF を比較する。
    """
    print("\n" + "=" * 65)
    print("比較: ⑥ 日次+20% 達成で当日トレード終了 — ON vs OFF")
    print("=" * 65)

    t_on, _ = run_backtest(
        df1m, initial_balance, lot_size, use_daily_profit_stop=True, verbose=False
    )
    s_on = analyze(t_on, initial_balance)

    t_off, _ = run_backtest(
        df1m, initial_balance, lot_size, use_daily_profit_stop=False, verbose=False
    )
    s_off = analyze(t_off, initial_balance)

    if not s_on or not s_off:
        print("トレードなしのため比較できません。")
        return None

    def row(label, s):
        return (
            f"| {label} | {s['total_trades']} | {s['win_rate']:.1f}% | {s['profit_factor']:.2f} | "
            f"¥{s['final_balance']:,.0f} | {s['total_return_pct']:+.1f}% | "
            f"{s['max_dd_pct']:.1f}% | {s['max_consec_loss']} |"
        )

    lines = [
        "",
        "| ⑥ | 総トレード | 勝率 | PF | 最終残高 | 総収益率 | 最大DD | 最大連敗 |",
        "|:--|----------:|-----:|---:|---------:|---------:|-------:|---------:|",
        row("ON（+20%で当日停止）", s_on),
        row("OFF（+20%停止なし）", s_off),
        "",
        f"*トレード数差: {s_off['total_trades'] - s_on['total_trades']:+d}（OFF より ON が少ない日は +20% で打ち切り）*",
        "",
    ]
    text = "\n".join(lines)
    print(text)

    out_path = os.path.join(OUTPUT_DIR, "compare_daily_profit_stop_10k.md")
    ensure_output_dir()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# ⑥ 日次+20% 停止 ON / OFF 比較（¥10,000・0.01ロット）\n\n")
        f.write(text)
    print(f"保存: {out_path}")
    return {"on": s_on, "off": s_off, "trades_on": t_on, "trades_off": t_off}


def _monthly_max_dd_by_exit(trades_df, initial_balance):
    """各暦月について、exit 順の残高曲線でのピーク比最大 DD（%）。"""
    if len(trades_df) == 0:
        return pd.Series(dtype=float)
    t = trades_df.sort_values('exit_time').reset_index(drop=True)
    t['ym'] = t['exit_time'].dt.to_period('M')
    out = {}
    prev_equity = initial_balance
    for ym in t['ym'].unique():
        grp = t[t['ym'] == ym]
        peak = prev_equity
        max_dd = 0.0
        for _, row in grp.iterrows():
            eq = row['balance']
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100 if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        prev_equity = grp['balance'].iloc[-1]
        out[ym] = max_dd
    return pd.Series(out)


def analyze(trades_df, initial_balance):
    if len(trades_df) == 0:
        return None

    wins = trades_df[trades_df['pnl_jpy'] > 0]
    losses = trades_df[trades_df['pnl_jpy'] <= 0]
    win_rate = len(wins) / len(trades_df) * 100
    total_win = wins['pnl_jpy'].sum()
    total_loss = abs(losses['pnl_jpy'].sum())
    pf = total_win / total_loss if total_loss > 0 else float('inf')

    bal_series = [initial_balance] + list(trades_df['balance'])
    peak = initial_balance
    max_dd_pct = 0.0
    for b in bal_series:
        if b > peak:
            peak = b
        dd_pct = (peak - b) / peak * 100
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    signs = (trades_df['pnl_jpy'] > 0).tolist()
    max_cw = max_cl = cw = cl = 0
    for s in signs:
        if s:
            cw += 1
            cl = 0
        else:
            cl += 1
            cw = 0
        max_cw = max(max_cw, cw)
        max_cl = max(max_cl, cl)

    total_days = (trades_df['exit_time'].max() - trades_df['entry_time'].min()).days + 1
    final_balance = trades_df['balance'].iloc[-1]

    trades_df = trades_df.copy()
    trades_df['ym'] = trades_df['entry_time'].dt.to_period('M')
    trades_df['hour'] = trades_df['entry_time'].dt.hour

    monthly = trades_df.groupby('ym').agg(
        count=('pnl_jpy', 'count'),
        pnl=('pnl_jpy', 'sum'),
        win_rate=('pnl_jpy', lambda x: (x > 0).mean() * 100),
        gross_win=('pnl_jpy', lambda x: x[x > 0].sum()),
        gross_loss=('pnl_jpy', lambda x: x[x <= 0].sum()),
    )

    dd_series = _monthly_max_dd_by_exit(trades_df, initial_balance)
    monthly['max_dd_pct_month'] = dd_series.reindex(monthly.index)

    long_m = trades_df[trades_df['side'] == 'long'].groupby('ym').agg(
        long_count=('pnl_jpy', 'count'),
        long_pnl=('pnl_jpy', 'sum'),
    )
    short_m = trades_df[trades_df['side'] == 'short'].groupby('ym').agg(
        short_count=('pnl_jpy', 'count'),
        short_pnl=('pnl_jpy', 'sum'),
    )
    monthly = monthly.join(long_m, how='left').join(short_m, how='left')
    for c in ('long_count', 'long_pnl', 'short_count', 'short_pnl'):
        if c not in monthly.columns:
            monthly[c] = 0.0
    monthly[['long_count', 'long_pnl', 'short_count', 'short_pnl']] = monthly[
        ['long_count', 'long_pnl', 'short_count', 'short_pnl']
    ].fillna(0)

    hourly = trades_df.groupby('hour').agg(
        count=('pnl_jpy', 'count'),
        pnl=('pnl_jpy', 'sum'),
        win_rate=('pnl_jpy', lambda x: (x > 0).mean() * 100)
    )
    side = trades_df.groupby('side').agg(
        count=('pnl_jpy', 'count'),
        pnl=('pnl_jpy', 'sum'),
        win_rate=('pnl_jpy', lambda x: (x > 0).mean() * 100),
        avg_pnl=('pnl_jpy', 'mean')
    )

    positive_months = (monthly['pnl'] > 0).sum()

    return {
        'total_trades': len(trades_df),
        'win_trades': len(wins),
        'loss_trades': len(losses),
        'win_rate': win_rate,
        'avg_win': wins['pnl_jpy'].mean() if len(wins) else 0,
        'avg_loss': losses['pnl_jpy'].mean() if len(losses) else 0,
        'total_win': total_win,
        'total_loss': -total_loss,
        'profit_factor': pf,
        'max_dd_pct': max_dd_pct,
        'max_consec_win': max_cw,
        'max_consec_loss': max_cl,
        'initial_balance': initial_balance,
        'final_balance': final_balance,
        'total_return_pct': (final_balance - initial_balance) / initial_balance * 100,
        'total_days': total_days,
        'trades_per_day': len(trades_df) / total_days,
        'trades_per_week': len(trades_df) / (total_days / 7),
        'trades_per_month': len(trades_df) / (total_days / 30),
        'avg_duration_min': trades_df['duration_min'].mean(),
        'monthly': monthly,
        'monthly_detail': monthly,
        'positive_months': int(positive_months),
        'hourly': hourly,
        'side': side,
    }


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def write_summary_csv(rows, path):
    if not rows:
        return
    keys = rows[0].keys()
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def write_summary_md(rows, path):
    lines = [
        '# ロジック② ロット別比較サマリー（初期残高 10万円）',
        '',
        '| シナリオ | ロット | 総トレード | 勝率 | PF | 最終残高 | 総収益率 | 最大DD | 最大連敗 | プラス月数 |',
        '|:---------|-------:|----------:|-----:|---:|---------:|---------:|-------:|---------:|-----------:|',
    ]
    for r in rows:
        lines.append(
            f"| {r['scenario']} | {r['lot']} | {r['total_trades']} | {r['win_rate']:.1f}% | "
            f"{r['profit_factor']:.2f} | ¥{r['final_balance']:,.0f} | {r['total_return_pct']:+.1f}% | "
            f"{r['max_dd_pct']:.1f}% | {r['max_consec_loss']} | {r['positive_months']} |"
        )
    lines.append('')
    lines.append('*スプレッド・パラメータは backtest_logic2.py 先頭定数を参照。*')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def write_monthly_csv(monthly_df, path):
    monthly_df.to_csv(path, encoding='utf-8')


def write_monthly_md(scenario_name, monthly_df, path):
    lines = [
        f'# ロジック② 月次詳細 — {scenario_name}',
        '',
        '| 月 | 回数 | 損益 | 勝率 | 粗利 | 粗損 | ロング回/損益 | ショート回/損益 | 月内最大DD |',
        '|:----|-----:|-----:|-----:|-----:|-----:|---------------|----------------|------------|',
    ]
    for ym, row in monthly_df.iterrows():
        lines.append(
            f"| {ym} | {int(row['count'])} | ¥{row['pnl']:+,.0f} | {row['win_rate']:.1f}% | "
            f"¥{row['gross_win']:+,.0f} | ¥{row['gross_loss']:+,.0f} | "
            f"{int(row['long_count'])}/¥{row['long_pnl']:+,.0f} | "
            f"{int(row['short_count'])}/¥{row['short_pnl']:+,.0f} | "
            f"{row['max_dd_pct_month']:.2f}% |"
        )
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


if __name__ == '__main__':
    import sys

    ensure_output_dir()
    df1m = load_data()

    # 例: python backtest_logic2.py --compare-daily-profit
    if '--compare-daily-profit' in sys.argv:
        compare_daily_profit_stop(df1m)
        sys.exit(0)

    results_l2 = {}
    summary_rows = []

    for scenario_name, init_bal, lot_sz in SCENARIOS:
        trades_df, final_bal = run_backtest(df1m, init_bal, lot_sz)
        stats = analyze(trades_df, init_bal)
        results_l2[scenario_name] = {
            'trades': trades_df,
            'stats': stats,
            'lot': lot_sz,
            'initial_balance': init_bal,
        }

        if stats:
            s = stats
            print(f"\n--- {scenario_name} 結果サマリー ---")
            print(f"総トレード数    : {s['total_trades']}")
            print(f"勝率            : {s['win_rate']:.1f}%")
            print(f"PF              : {s['profit_factor']:.2f}")
            print(f"最終残高        : ¥{s['final_balance']:,.0f}")
            print(f"総収益率        : {s['total_return_pct']:+.1f}%")
            print(f"最大DD          : {s['max_dd_pct']:.1f}%")
            print(f"プラス月数      : {s['positive_months']} / {len(s['monthly'])}")
            if s['side'] is not None and len(s['side']) > 0:
                print("方向別:")
                print(s['side'].to_string())

            summary_rows.append({
                'scenario': scenario_name,
                'lot': lot_sz,
                'total_trades': s['total_trades'],
                'win_rate': round(s['win_rate'], 2),
                'profit_factor': round(s['profit_factor'], 4) if s['profit_factor'] != float('inf') else 999999,
                'final_balance': round(s['final_balance'], 2),
                'total_return_pct': round(s['total_return_pct'], 2),
                'max_dd_pct': round(s['max_dd_pct'], 2),
                'max_consec_loss': s['max_consec_loss'],
                'positive_months': s['positive_months'],
            })

            md_path = os.path.join(OUTPUT_DIR, f'monthly_{scenario_name}.md')
            csv_path = os.path.join(OUTPUT_DIR, f'monthly_{scenario_name}.csv')
            write_monthly_md(scenario_name, s['monthly_detail'], md_path)
            write_monthly_csv(s['monthly_detail'], csv_path)
            print(f"  月次: {md_path}")
        else:
            print(f"\n--- {scenario_name}: トレードなし ---")

    if summary_rows:
        write_summary_csv(summary_rows, os.path.join(OUTPUT_DIR, 'compare_ABC_summary.csv'))
        write_summary_md(summary_rows, os.path.join(OUTPUT_DIR, 'compare_ABC_summary.md'))

    pkl_path = os.path.join(OUTPUT_DIR, 'backtest_results_logic2_scenarios.pkl')
    with open(pkl_path, 'wb') as f:
        pickle.dump(results_l2, f)
    print(f"\n結果を保存: {pkl_path}, {OUTPUT_DIR}/compare_ABC_summary.*")
