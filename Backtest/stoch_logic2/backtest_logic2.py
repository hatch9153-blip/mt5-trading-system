"""
Stochastics EA バックテストエンジン ロジック②
==============================================
全時間足: Stochastics(9,3,3)

【ロング戦略】
① 4H足 Stoch(9,3,3) が 0〜20 圏内でGC（反転上昇サイン）→ ロング戦略開始
② 4H足 Stoch が 80〜100 に到達してDC（反転下落サイン）が出るまでロング戦略継続
③ 4H足 %K が上昇中 かつ 1H足 %K が上昇中 の間、④⑤を繰り返す
④ 5M足 Stoch が 0〜20 圏内でGC → ロングエントリー
⑤ 5M足 Stoch が 80〜100 圏内でDC → イグジット
⑥ 日次+20%達成でトレード終了（複数回繰り返し可）

【ショート戦略】
① 4H足 Stoch が 80〜100 圏内でDC（反転下落サイン）→ ショート戦略開始
② 4H足 Stoch が 0〜20 に到達してGC（反転上昇サイン）が出るまでショート戦略継続
③ 4H足 %K が下降中 かつ 1H足 %K が下降中 の間、④⑤を繰り返す
④ 5M足 Stoch が 80〜100 圏内でDC → ショートエントリー
⑤ 5M足 Stoch が 0〜20 圏内でGC → イグジット
⑥ 日次+20%達成でトレード終了（複数回繰り返し可）
"""

import pandas as pd
import numpy as np
import glob
import os
import pickle
import warnings
warnings.filterwarnings('ignore')

# ===== 設定 =====
CSV_DIR    = "/home/ubuntu/stoch_backtest/csv_data"
OUTPUT_DIR = "/home/ubuntu/stoch_backtest"
INITIAL_BALANCES = [10_000, 100_000]

USD_JPY       = 150.0
LOT_SIZE      = 0.01
CONTRACT_SIZE = 10
SPREAD_USD    = 0.30

K_PERIOD = 9
D_PERIOD = 3
SLOWING  = 3

OVERSOLD   = 20.0
OVERBOUGHT = 80.0

DAILY_PROFIT_TARGET_PCT = 0.20   # +20%でトレード終了
MAX_DAILY_LOSS_PCT      = 0.10   # -10%で当日終了（リスク管理）
MAX_CONSECUTIVE_LOSSES  = 5      # 連続負け5回で当日終了

# ===== Stochastics 計算 =====
def calc_stoch(df, k_period=9, slowing=3, d_period=3):
    low_min  = df['low'].rolling(k_period).min()
    high_max = df['high'].rolling(k_period).max()
    raw_k = 100.0 * (df['close'] - low_min) / (high_max - low_min + 1e-10)
    k = raw_k.rolling(slowing).mean()
    d = k.rolling(d_period).mean()
    return k.values, d.values

# ===== データ読み込み =====
def load_data():
    print("CSVデータ読み込み中...")
    dfs = []
    for f in sorted(glob.glob(os.path.join(CSV_DIR, "**/*.csv"), recursive=True)):
        try:
            df = pd.read_csv(f, header=None,
                             names=['date','time','open','high','low','close','volume'])
            df['dt'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%Y.%m.%d %H:%M')
            dfs.append(df[['dt','open','high','low','close','volume']])
        except Exception as e:
            print(f"  スキップ: {f}: {e}")
    df1m = pd.concat(dfs).sort_values('dt').drop_duplicates('dt').reset_index(drop=True)
    print(f"  1M: {len(df1m):,}本 ({df1m['dt'].iloc[0]} 〜 {df1m['dt'].iloc[-1]})")
    return df1m

def resample(df1m, rule):
    df = df1m.set_index('dt').resample(rule).agg(
        open=('open','first'), high=('high','max'),
        low=('low','min'), close=('close','last'), volume=('volume','sum')
    ).dropna().reset_index()
    return df

# ===== バックテスト =====
def run_backtest(df1m, initial_balance):
    print(f"\n{'='*65}")
    print(f"バックテスト [ロジック②]: 初期資金 ¥{initial_balance:,}")
    print(f"{'='*65}")

    print("リサンプリング中...")
    df5m  = resample(df1m, '5min')
    df1h  = resample(df1m, '1h')
    df4h  = resample(df1m, '4h')

    print("Stochastics計算中...")
    k5m,  d5m  = calc_stoch(df5m)
    k1h,  d1h  = calc_stoch(df1h)
    k4h,  d4h  = calc_stoch(df4h)

    # 5M足にStochastics付与
    df5m = df5m.copy()
    df5m['k5m'] = k5m
    df5m['d5m'] = d5m

    # 1H足にStochastics付与
    df1h_s = df1h[['dt']].copy()
    df1h_s['k1h'] = k1h
    df1h_s['d1h'] = d1h

    # 4H足にStochastics付与
    df4h_s = df4h[['dt']].copy()
    df4h_s['k4h'] = k4h
    df4h_s['d4h'] = d4h

    # 5M足に1H・4H情報をmerge
    df5m = pd.merge_asof(df5m.sort_values('dt'), df1h_s.sort_values('dt'),
                         on='dt', direction='backward')
    df5m = pd.merge_asof(df5m.sort_values('dt'), df4h_s.sort_values('dt'),
                         on='dt', direction='backward')
    df5m = df5m.reset_index(drop=True)
    print(f"  マージ完了: {len(df5m):,}行（5M足）")

    # ===== シミュレーション =====
    balance = float(initial_balance)
    trades  = []

    in_position   = False
    entry_price   = 0.0
    entry_time    = None
    position_side = None

    # 戦略状態
    strategy_mode = None   # 'long' or 'short' or None
    # 4H足の前足値（クロス検出用）
    prev_k4h = np.nan
    prev_d4h = np.nan

    # 日次管理
    current_date       = None
    day_start_balance  = balance
    consecutive_losses = 0
    day_blocked        = False

    n = len(df5m)
    print("シミュレーション実行中...")

    for i in range(50, n):
        row = df5m.iloc[i]
        dt  = row['dt']

        if pd.isna(row['k4h']) or pd.isna(row['k1h']) or pd.isna(row['k5m']):
            prev_k4h = row['k4h'] if not pd.isna(row['k4h']) else prev_k4h
            prev_d4h = row['d4h'] if not pd.isna(row['d4h']) else prev_d4h
            continue

        # ===== 日次リセット =====
        d = dt.date()
        if d != current_date:
            current_date       = d
            day_start_balance  = balance
            consecutive_losses = 0
            day_blocked        = False

        # ===== 4H足のGC/DC検出（クロス判定）=====
        k4h_now = row['k4h']
        d4h_now = row['d4h']

        if not pd.isna(prev_k4h) and not pd.isna(prev_d4h):
            # 4H GC: 前足 k < d、今足 k > d、かつ 0〜20圏内
            gc_4h = (prev_k4h <= prev_d4h) and (k4h_now > d4h_now) and (k4h_now <= OVERSOLD + 5)
            # 4H DC: 前足 k > d、今足 k < d、かつ 80〜100圏内
            dc_4h = (prev_k4h >= prev_d4h) and (k4h_now < d4h_now) and (k4h_now >= OVERBOUGHT - 5)

            # 戦略モード切替
            if gc_4h:
                strategy_mode = 'long'
            elif dc_4h:
                strategy_mode = 'short'

            # 戦略終了条件
            # ロング戦略: 4H足が80〜100に到達してDCが出たら終了
            if strategy_mode == 'long' and dc_4h:
                strategy_mode = None
            # ショート戦略: 4H足が0〜20に到達してGCが出たら終了
            if strategy_mode == 'short' and gc_4h:
                strategy_mode = None

        prev_k4h = k4h_now
        prev_d4h = d4h_now

        # ===== エグジット =====
        if in_position:
            k5m_now = row['k5m']
            d5m_now = row['d5m']
            prev_row = df5m.iloc[i-1]
            pk5m = prev_row['k5m']
            pd5m_val = prev_row['d5m']

            exit_signal = False
            exit_reason = ''

            if position_side == 'long':
                # 5M足が80〜100圏内でDC（デッドクロス）
                dc_5m = (not pd.isna(pk5m) and not pd.isna(pd5m_val) and
                         pk5m >= pd5m_val and k5m_now < d5m_now and
                         k5m_now >= OVERBOUGHT - 5)
                if dc_5m:
                    exit_signal = True
                    exit_reason = '5M_DC'
            elif position_side == 'short':
                # 5M足が0〜20圏内でGC（ゴールデンクロス）
                gc_5m = (not pd.isna(pk5m) and not pd.isna(pd5m_val) and
                         pk5m <= pd5m_val and k5m_now > d5m_now and
                         k5m_now <= OVERSOLD + 5)
                if gc_5m:
                    exit_signal = True
                    exit_reason = '5M_GC'

            if exit_signal:
                exit_price = row['close']
                if position_side == 'long':
                    pnl_usd = (exit_price - entry_price - SPREAD_USD) * CONTRACT_SIZE * LOT_SIZE
                else:
                    pnl_usd = (entry_price - exit_price - SPREAD_USD) * CONTRACT_SIZE * LOT_SIZE
                pnl_jpy = pnl_usd * USD_JPY
                balance += pnl_jpy

                trades.append({
                    'entry_time':    entry_time,
                    'exit_time':     dt,
                    'side':          position_side,
                    'entry_price':   entry_price,
                    'exit_price':    exit_price,
                    'pnl_usd':       round(pnl_usd, 4),
                    'pnl_jpy':       round(pnl_jpy, 2),
                    'balance':       round(balance, 2),
                    'duration_min':  (dt - entry_time).total_seconds() / 60,
                    'exit_reason':   exit_reason,
                    'k4h_at_entry':  k4h_now,
                    'k1h_at_entry':  row['k1h'],
                    'k5m_at_entry':  k5m_now,
                })

                consecutive_losses = 0 if pnl_jpy > 0 else consecutive_losses + 1
                in_position = False

                # 日次管理
                if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                    day_blocked = True
                if balance >= day_start_balance * (1 + DAILY_PROFIT_TARGET_PCT):
                    day_blocked = True
                if balance <= day_start_balance * (1 - MAX_DAILY_LOSS_PCT):
                    day_blocked = True
                continue

        # ===== エントリー =====
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
        prev_row = df5m.iloc[i-1]
        pk5m = prev_row['k5m']
        pd5m_val = prev_row['d5m']
        pk1h = prev_row['k1h']

        if pd.isna(pk5m) or pd.isna(pd5m_val) or pd.isna(pk1h):
            continue

        # 1H足の方向判定: %K > %D なら上昇トレンド、%K < %D なら下降トレンド
        k1h_rising  = k1h_now > d1h_now   # 1H %K が %D より上 = 上昇トレンド
        k1h_falling = k1h_now < d1h_now   # 1H %K が %D より下 = 下降トレンド

        # 4H足の方向判定: %K > %D なら上昇トレンド、%K < %D なら下降トレンド
        k4h_rising  = k4h_now > d4h_now
        k4h_falling = k4h_now < d4h_now

        if strategy_mode == 'long':
            # 条件③: 4H上昇中 かつ 1H上昇中
            if not (k4h_rising and k1h_rising):
                continue
            # 条件④: 5M足が0〜20圏内でGC
            gc_5m_entry = (pk5m <= pd5m_val and k5m_now > d5m_now and
                           k5m_now <= OVERSOLD + 5)
            if gc_5m_entry:
                entry_price   = row['close'] + SPREAD_USD
                in_position   = True
                entry_time    = dt
                position_side = 'long'

        elif strategy_mode == 'short':
            # 条件③: 4H下降中 かつ 1H下降中
            if not (k4h_falling and k1h_falling):
                continue
            # 条件④: 5M足が80〜100圏内でDC
            dc_5m_entry = (pk5m >= pd5m_val and k5m_now < d5m_now and
                           k5m_now >= OVERBOUGHT - 5)
            if dc_5m_entry:
                entry_price   = row['close'] - SPREAD_USD
                in_position   = True
                entry_time    = dt
                position_side = 'short'

        if i % 50000 == 0 and i > 0:
            print(f"  進捗: {i/n*100:.1f}% | トレード数: {len(trades)} | 残高: ¥{balance:,.0f}")

    # 未決済ポジション強制クローズ
    if in_position:
        last = df5m.iloc[-1]
        ep = last['close']
        pnl_usd = (ep - entry_price - SPREAD_USD) * CONTRACT_SIZE * LOT_SIZE \
                  if position_side == 'long' \
                  else (entry_price - ep - SPREAD_USD) * CONTRACT_SIZE * LOT_SIZE
        pnl_jpy = pnl_usd * USD_JPY
        balance += pnl_jpy
        trades.append({
            'entry_time': entry_time, 'exit_time': last['dt'],
            'side': position_side, 'entry_price': entry_price, 'exit_price': ep,
            'pnl_usd': round(pnl_usd,4), 'pnl_jpy': round(pnl_jpy,2),
            'balance': round(balance,2),
            'duration_min': (last['dt']-entry_time).total_seconds()/60,
            'exit_reason': 'force_close',
            'k4h_at_entry': np.nan, 'k1h_at_entry': np.nan, 'k5m_at_entry': np.nan,
        })

    trades_df = pd.DataFrame(trades)
    print(f"\n  完了: {len(trades_df)}トレード | 最終残高: ¥{balance:,.0f}")
    return trades_df, balance

# ===== 統計分析 =====
def analyze(trades_df, initial_balance):
    if len(trades_df) == 0:
        return None

    wins   = trades_df[trades_df['pnl_jpy'] > 0]
    losses = trades_df[trades_df['pnl_jpy'] <= 0]
    win_rate   = len(wins) / len(trades_df) * 100
    total_win  = wins['pnl_jpy'].sum()
    total_loss = abs(losses['pnl_jpy'].sum())
    pf = total_win / total_loss if total_loss > 0 else float('inf')

    bal_series = [initial_balance] + list(trades_df['balance'])
    peak = initial_balance
    max_dd_pct = 0.0
    for b in bal_series:
        if b > peak: peak = b
        dd_pct = (peak - b) / peak * 100
        if dd_pct > max_dd_pct: max_dd_pct = dd_pct

    signs = (trades_df['pnl_jpy'] > 0).tolist()
    max_cw = max_cl = cw = cl = 0
    for s in signs:
        if s: cw += 1; cl = 0
        else: cl += 1; cw = 0
        max_cw = max(max_cw, cw); max_cl = max(max_cl, cl)

    total_days    = (trades_df['exit_time'].max() - trades_df['entry_time'].min()).days + 1
    final_balance = trades_df['balance'].iloc[-1]

    trades_df = trades_df.copy()
    trades_df['ym']   = trades_df['entry_time'].dt.to_period('M')
    trades_df['hour'] = trades_df['entry_time'].dt.hour

    monthly = trades_df.groupby('ym').agg(
        count=('pnl_jpy','count'),
        pnl=('pnl_jpy','sum'),
        win_rate=('pnl_jpy', lambda x: (x>0).mean()*100)
    )
    hourly = trades_df.groupby('hour').agg(
        count=('pnl_jpy','count'),
        pnl=('pnl_jpy','sum'),
        win_rate=('pnl_jpy', lambda x: (x>0).mean()*100)
    )
    side = trades_df.groupby('side').agg(
        count=('pnl_jpy','count'),
        pnl=('pnl_jpy','sum'),
        win_rate=('pnl_jpy', lambda x: (x>0).mean()*100),
        avg_pnl=('pnl_jpy','mean')
    )

    return {
        'total_trades':     len(trades_df),
        'win_trades':       len(wins),
        'loss_trades':      len(losses),
        'win_rate':         win_rate,
        'avg_win':          wins['pnl_jpy'].mean() if len(wins) else 0,
        'avg_loss':         losses['pnl_jpy'].mean() if len(losses) else 0,
        'total_win':        total_win,
        'total_loss':       -total_loss,
        'profit_factor':    pf,
        'max_dd_pct':       max_dd_pct,
        'max_consec_win':   max_cw,
        'max_consec_loss':  max_cl,
        'initial_balance':  initial_balance,
        'final_balance':    final_balance,
        'total_return_pct': (final_balance - initial_balance) / initial_balance * 100,
        'total_days':       total_days,
        'trades_per_day':   len(trades_df) / total_days,
        'trades_per_week':  len(trades_df) / (total_days / 7),
        'trades_per_month': len(trades_df) / (total_days / 30),
        'avg_duration_min': trades_df['duration_min'].mean(),
        'monthly':          monthly,
        'hourly':           hourly,
        'side':             side,
    }

# ===== メイン =====
if __name__ == '__main__':
    df1m = load_data()
    results_l2 = {}

    for init_bal in INITIAL_BALANCES:
        trades_df, final_bal = run_backtest(df1m, init_bal)
        stats = analyze(trades_df, init_bal)
        results_l2[init_bal] = {'trades': trades_df, 'stats': stats}

        if stats:
            s = stats
            print(f"\n--- ¥{init_bal:,} スタート 結果サマリー [ロジック②] ---")
            print(f"総トレード数    : {s['total_trades']}")
            print(f"勝率            : {s['win_rate']:.1f}%")
            print(f"PF              : {s['profit_factor']:.2f}")
            print(f"最終残高        : ¥{s['final_balance']:,.0f}")
            print(f"総収益率        : {s['total_return_pct']:+.1f}%")
            print(f"最大DD          : {s['max_dd_pct']:.1f}%")
            print(f"1日あたり       : {s['trades_per_day']:.3f}回")
            print(f"1週間あたり     : {s['trades_per_week']:.2f}回")
            print(f"1ヶ月あたり     : {s['trades_per_month']:.2f}回")
            print(f"平均保有時間    : {s['avg_duration_min']:.0f}分")
            if s['side'] is not None and len(s['side']) > 0:
                print(f"方向別:")
                print(s['side'].to_string())
        else:
            print(f"\n--- ¥{init_bal:,} スタート: トレードなし ---")

    with open(f'{OUTPUT_DIR}/backtest_results_logic2.pkl', 'wb') as f:
        pickle.dump(results_l2, f)
    print("\n結果を保存しました (backtest_results_logic2.pkl)")
