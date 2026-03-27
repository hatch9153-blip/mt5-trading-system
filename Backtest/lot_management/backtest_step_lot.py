"""
段階的ロット方式バックテスト
==============================
ロット計算ルール:
  - 初期ロット = 初期残高 / 10,000 × 0.01lot
  - 残高が「直近のロットアップ基準残高」の2倍に達したらロットを2倍に増やす
  - ロットは一度上げたら下げない（ステップアップ方式）

例（¥10,000スタート）:
  ¥10,000 → 0.01lot
  ¥20,000 → 0.02lot（2倍達成）
  ¥40,000 → 0.04lot（さらに2倍達成）
  ¥80,000 → 0.08lot
  ...

例（¥100,000スタート）:
  ¥100,000 → 0.10lot
  ¥200,000 → 0.20lot（2倍達成）
  ¥400,000 → 0.40lot
  ...
"""

import pandas as pd
import numpy as np
import glob, os, pickle, warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = "/home/ubuntu/stoch_backtest"
K_PERIOD = 9; D_PERIOD = 3; SLOWING = 3
OVERSOLD = 20.0; OVERBOUGHT = 80.0
DAILY_PROFIT_TARGET_PCT = 0.20
MAX_DAILY_LOSS_PCT      = 0.10
MAX_CONSECUTIVE_LOSSES  = 5

def calc_step_lot(balance, base_balance, base_lot):
    """残高が base_balance の2倍に達するたびにロットを2倍にする"""
    multiplier = 1
    threshold = base_balance * 2
    while balance >= threshold:
        multiplier *= 2
        threshold *= 2
    return round(base_lot * multiplier, 2)

def calc_stoch(df, k_period=9, slowing=3, d_period=3):
    low_min  = df['low'].rolling(k_period).min()
    high_max = df['high'].rolling(k_period).max()
    raw_k = 100.0 * (df['close'] - low_min) / (high_max - low_min + 1e-10)
    k = raw_k.rolling(slowing).mean()
    d = k.rolling(d_period).mean()
    return k.values, d.values

def load_data(csv_dir):
    dfs = []
    for f in sorted(glob.glob(os.path.join(csv_dir, "**/*.csv"), recursive=True)):
        try:
            df = pd.read_csv(f, header=None,
                             names=['date','time','open','high','low','close','volume'])
            df['dt'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%Y.%m.%d %H:%M')
            dfs.append(df[['dt','open','high','low','close','volume']])
        except: pass
    df1m = pd.concat(dfs).sort_values('dt').drop_duplicates('dt').reset_index(drop=True)
    return df1m

def resample(df1m, rule):
    return df1m.set_index('dt').resample(rule).agg(
        open=('open','first'), high=('high','max'),
        low=('low','min'), close=('close','last'), volume=('volume','sum')
    ).dropna().reset_index()

def run_backtest(df1m, initial_balance, symbol):
    is_gold = (symbol == 'GOLD')
    SPREAD  = 0.30 if is_gold else 0.03
    USD_JPY = 150.0
    base_lot = initial_balance / 10_000 * 0.01  # 初期ロット

    print(f"\n{'='*65}")
    print(f"バックテスト [段階的ロット / {symbol}]: 初期資金 ¥{initial_balance:,}")
    print(f"  初期ロット: {base_lot:.2f}lot  (2倍達成ごとにロットアップ)")
    print(f"{'='*65}")

    df5m = resample(df1m, '5min')
    df1h = resample(df1m, '1h')
    df4h = resample(df1m, '4h')

    k5m, d5m = calc_stoch(df5m)
    k1h, d1h = calc_stoch(df1h)
    k4h, d4h = calc_stoch(df4h)

    df5m = df5m.copy()
    df5m['k5m'] = k5m; df5m['d5m'] = d5m
    df1h_s = df1h[['dt']].copy(); df1h_s['k1h'] = k1h; df1h_s['d1h'] = d1h
    df4h_s = df4h[['dt']].copy(); df4h_s['k4h'] = k4h; df4h_s['d4h'] = d4h

    df5m = pd.merge_asof(df5m.sort_values('dt'), df1h_s.sort_values('dt'), on='dt', direction='backward')
    df5m = pd.merge_asof(df5m.sort_values('dt'), df4h_s.sort_values('dt'), on='dt', direction='backward')
    df5m = df5m.reset_index(drop=True)
    print(f"  マージ完了: {len(df5m):,}行（5M足）")

    balance = float(initial_balance)
    trades  = []
    in_position = False
    entry_price = 0.0; entry_time = None; position_side = None
    current_lot = base_lot

    # ロットアップ履歴
    lot_up_events = []

    strategy_mode = None
    prev_k4h = np.nan; prev_d4h = np.nan

    current_date = None
    day_start_balance = balance
    consecutive_losses = 0
    day_blocked = False

    n = len(df5m)
    print("シミュレーション実行中...")

    for i in range(50, n):
        row = df5m.iloc[i]
        dt  = row['dt']

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

        k4h_now = row['k4h']; d4h_now = row['d4h']

        if not pd.isna(prev_k4h) and not pd.isna(prev_d4h):
            gc_4h = (prev_k4h <= prev_d4h) and (k4h_now > d4h_now) and (k4h_now <= OVERSOLD + 5)
            dc_4h = (prev_k4h >= prev_d4h) and (k4h_now < d4h_now) and (k4h_now >= OVERBOUGHT - 5)
            if gc_4h: strategy_mode = 'long'
            elif dc_4h: strategy_mode = 'short'
            if strategy_mode == 'long' and dc_4h: strategy_mode = None
            if strategy_mode == 'short' and gc_4h: strategy_mode = None

        prev_k4h = k4h_now; prev_d4h = d4h_now

        # エグジット
        if in_position:
            k5m_now = row['k5m']; d5m_now = row['d5m']
            prev_row = df5m.iloc[i-1]
            pk5m = prev_row['k5m']; pd5m_val = prev_row['d5m']
            exit_signal = False; exit_reason = ''

            if position_side == 'long':
                dc_5m = (not pd.isna(pk5m) and not pd.isna(pd5m_val) and
                         pk5m >= pd5m_val and k5m_now < d5m_now and k5m_now >= OVERBOUGHT - 5)
                if dc_5m: exit_signal = True; exit_reason = '5M_DC'
            elif position_side == 'short':
                gc_5m = (not pd.isna(pk5m) and not pd.isna(pd5m_val) and
                         pk5m <= pd5m_val and k5m_now > d5m_now and k5m_now <= OVERSOLD + 5)
                if gc_5m: exit_signal = True; exit_reason = '5M_GC'

            if exit_signal:
                exit_price = row['close']
                if is_gold:
                    pnl_jpy = (exit_price - entry_price - SPREAD) * 10 * current_lot * USD_JPY \
                              if position_side == 'long' \
                              else (entry_price - exit_price - SPREAD) * 10 * current_lot * USD_JPY
                else:
                    pnl_jpy = (exit_price - entry_price - SPREAD) * 100_000 * current_lot \
                              if position_side == 'long' \
                              else (entry_price - exit_price - SPREAD) * 100_000 * current_lot

                balance += pnl_jpy

                # ロットアップ判定（エグジット後に残高確認）
                new_lot = calc_step_lot(balance, initial_balance, base_lot)
                if new_lot > current_lot:
                    lot_up_events.append({
                        'time': dt, 'balance': balance,
                        'old_lot': current_lot, 'new_lot': new_lot
                    })
                    print(f"  ★ロットアップ: {current_lot:.2f}→{new_lot:.2f}lot | 残高¥{balance:,.0f} | {dt.date()}")
                    current_lot = new_lot

                trades.append({
                    'entry_time': entry_time, 'exit_time': dt,
                    'side': position_side,
                    'entry_price': entry_price, 'exit_price': exit_price,
                    'lot': current_lot,
                    'pnl_jpy': round(pnl_jpy, 2),
                    'balance': round(balance, 2),
                    'duration_min': (dt - entry_time).total_seconds() / 60,
                    'exit_reason': exit_reason,
                })
                consecutive_losses = 0 if pnl_jpy > 0 else consecutive_losses + 1
                in_position = False

                if consecutive_losses >= MAX_CONSECUTIVE_LOSSES: day_blocked = True
                if balance >= day_start_balance * (1 + DAILY_PROFIT_TARGET_PCT): day_blocked = True
                if balance <= day_start_balance * (1 - MAX_DAILY_LOSS_PCT): day_blocked = True
                continue

        if in_position or day_blocked or strategy_mode is None:
            continue

        k5m_now = row['k5m']; d5m_now = row['d5m']
        k1h_now = row['k1h']; d1h_now = row['d1h']
        if i < 1: continue
        prev_row = df5m.iloc[i-1]
        pk5m = prev_row['k5m']; pd5m_val = prev_row['d5m']; pk1h = prev_row['k1h']
        if pd.isna(pk5m) or pd.isna(pd5m_val) or pd.isna(pk1h): continue

        k1h_rising  = k1h_now > d1h_now
        k1h_falling = k1h_now < d1h_now
        k4h_rising  = k4h_now > d4h_now
        k4h_falling = k4h_now < d4h_now

        if strategy_mode == 'long':
            if not (k4h_rising and k1h_rising): continue
            gc_5m_entry = (pk5m <= pd5m_val and k5m_now > d5m_now and k5m_now <= OVERSOLD + 5)
            if gc_5m_entry:
                entry_price = row['close'] + SPREAD
                in_position = True; entry_time = dt; position_side = 'long'
        elif strategy_mode == 'short':
            if not (k4h_falling and k1h_falling): continue
            dc_5m_entry = (pk5m >= pd5m_val and k5m_now < d5m_now and k5m_now >= OVERBOUGHT - 5)
            if dc_5m_entry:
                entry_price = row['close'] - SPREAD
                in_position = True; entry_time = dt; position_side = 'short'

        if i % 50000 == 0 and i > 0:
            print(f"  進捗: {i/n*100:.1f}% | トレード数: {len(trades)} | 残高: ¥{balance:,.0f} | lot: {current_lot:.2f}")

    # 未決済強制クローズ
    if in_position:
        last = df5m.iloc[-1]; ep = last['close']
        if is_gold:
            pnl_jpy = (ep - entry_price - SPREAD) * 10 * current_lot * USD_JPY \
                      if position_side == 'long' \
                      else (entry_price - ep - SPREAD) * 10 * current_lot * USD_JPY
        else:
            pnl_jpy = (ep - entry_price - SPREAD) * 100_000 * current_lot \
                      if position_side == 'long' \
                      else (entry_price - ep - SPREAD) * 100_000 * current_lot
        balance += pnl_jpy
        trades.append({'entry_time': entry_time, 'exit_time': last['dt'],
                       'side': position_side, 'entry_price': entry_price, 'exit_price': ep,
                       'lot': current_lot, 'pnl_jpy': round(pnl_jpy, 2),
                       'balance': round(balance, 2),
                       'duration_min': (last['dt']-entry_time).total_seconds()/60,
                       'exit_reason': 'force_close'})

    trades_df = pd.DataFrame(trades)
    print(f"\n  完了: {len(trades_df)}トレード | 最終残高: ¥{balance:,.0f}")
    print(f"  ロットアップ回数: {len(lot_up_events)}回 | 最終lot: {current_lot:.2f}lot")
    return trades_df, balance, lot_up_events

def analyze(trades_df, initial_balance):
    if len(trades_df) == 0: return None
    wins   = trades_df[trades_df['pnl_jpy'] > 0]
    losses = trades_df[trades_df['pnl_jpy'] <= 0]
    win_rate   = len(wins) / len(trades_df) * 100
    total_win  = wins['pnl_jpy'].sum()
    total_loss = abs(losses['pnl_jpy'].sum())
    pf = total_win / total_loss if total_loss > 0 else float('inf')

    bal_series = [initial_balance] + list(trades_df['balance'])
    peak = initial_balance; max_dd_pct = 0.0
    for b in bal_series:
        if b > peak: peak = b
        dd = (peak - b) / peak * 100
        if dd > max_dd_pct: max_dd_pct = dd

    signs = (trades_df['pnl_jpy'] > 0).tolist()
    max_cw = max_cl = cw = cl = 0
    for s in signs:
        if s: cw += 1; cl = 0
        else: cl += 1; cw = 0
        max_cw = max(max_cw, cw); max_cl = max(max_cl, cl)

    total_days = (trades_df['exit_time'].max() - trades_df['entry_time'].min()).days + 1
    final_balance = trades_df['balance'].iloc[-1]

    return {
        'total_trades':     len(trades_df),
        'win_rate':         win_rate,
        'avg_win':          wins['pnl_jpy'].mean() if len(wins) else 0,
        'avg_loss':         losses['pnl_jpy'].mean() if len(losses) else 0,
        'profit_factor':    pf,
        'max_dd_pct':       max_dd_pct,
        'max_consec_loss':  max_cl,
        'initial_balance':  initial_balance,
        'final_balance':    final_balance,
        'total_return_pct': (final_balance - initial_balance) / initial_balance * 100,
        'total_pnl':        final_balance - initial_balance,
        'trades_per_month': len(trades_df) / (total_days / 30),
        'avg_duration_min': trades_df['duration_min'].mean(),
        'avg_lot':          trades_df['lot'].mean(),
        'max_lot':          trades_df['lot'].max(),
    }

if __name__ == '__main__':
    results = {}

    for symbol, csv_dir in [('GOLD',   '/home/ubuntu/stoch_backtest/csv_data'),
                             ('USDJPY', '/home/ubuntu/stoch_backtest/csv_usdjpy')]:
        print(f"\n{'#'*65}")
        print(f"# {symbol} 段階的ロット バックテスト")
        print(f"{'#'*65}")
        df1m = load_data(csv_dir)
        print(f"  1M: {len(df1m):,}本 ({df1m['dt'].iloc[0]} 〜 {df1m['dt'].iloc[-1]})")

        results[symbol] = {}
        for init_bal in [10_000, 100_000]:
            trades_df, final_bal, lot_ups = run_backtest(df1m, init_bal, symbol)
            stats = analyze(trades_df, init_bal)
            results[symbol][init_bal] = {
                'trades': trades_df, 'stats': stats, 'lot_up_events': lot_ups
            }

            if stats:
                s = stats
                print(f"\n--- {symbol} ¥{init_bal:,} スタート [段階的ロット] ---")
                print(f"総トレード数    : {s['total_trades']}")
                print(f"勝率            : {s['win_rate']:.1f}%")
                print(f"PF              : {s['profit_factor']:.2f}")
                print(f"最終残高        : ¥{s['final_balance']:,.0f}")
                print(f"総収益額        : ¥{s['total_pnl']:+,.0f}")
                print(f"総収益率        : {s['total_return_pct']:+.1f}%")
                print(f"最大DD          : {s['max_dd_pct']:.1f}%")
                print(f"最大連続負け    : {s['max_consec_loss']}回")
                print(f"平均lot         : {s['avg_lot']:.3f}lot")
                print(f"最大lot         : {s['max_lot']:.2f}lot")
                print(f"ロットアップ回数: {len(lot_ups)}回")
                print(f"月平均回数      : {s['trades_per_month']:.1f}回")

    with open(f'{OUTPUT_DIR}/backtest_results_step_lot.pkl', 'wb') as f:
        pickle.dump(results, f)
    print("\n\n結果を保存しました (backtest_results_step_lot.pkl)")
