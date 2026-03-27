"""
Stochastics EA バックテストエンジン（実データ版 v2）
XM micro GOLD 1分足CSVデータを使用
多時間足: 1M / 5M / 15M / 1H / 4H
"""

import pandas as pd
import numpy as np
import glob
import os
import pickle
import warnings
warnings.filterwarnings('ignore')

# ===== 設定 =====
CSV_DIR = "/home/ubuntu/stoch_backtest/csv_data"
OUTPUT_DIR = "/home/ubuntu/stoch_backtest"
INITIAL_BALANCES = [10_000, 100_000]

USD_JPY = 150.0
LOT_SIZE = 0.01        # GOLDmicro 最小ロット
CONTRACT_SIZE = 10     # oz per lot
SPREAD_USD = 0.30      # $0.30 スプレッド

# Stochastics パラメータ
K_PERIOD_SHORT = 9
D_PERIOD_SHORT = 3
SLOWING_SHORT  = 3
K_PERIOD_LONG  = 60
D_PERIOD_LONG  = 3
SLOWING_LONG   = 3

OVERSOLD   = 20.0
OVERBOUGHT = 80.0

# リスク管理
MAX_CONSECUTIVE_LOSSES = 3
DAILY_PROFIT_TARGET_PCT = 0.20
MAX_DAILY_LOSS_PCT = 0.05

# ===== Stochastics 計算 =====
def calc_stoch(df, k_period, slowing, d_period):
    low_min  = df['low'].rolling(k_period).min()
    high_max = df['high'].rolling(k_period).max()
    raw_k = 100.0 * (df['close'] - low_min) / (high_max - low_min + 1e-10)
    k = raw_k.rolling(slowing).mean()
    d = k.rolling(d_period).mean()
    return k.values, d.values

# ===== 時間帯フィルター（サーバー時間 UTC+2） =====
def is_allowed_time(hour, minute):
    # JST 08:00-09:00 = Server 01:00-02:00
    if hour in [1, 2]:
        return True
    # JST 10:00-10:30 = Server 03:00-03:30
    if hour == 3 and minute <= 30:
        return True
    # JST 11:00-15:00 = Server 04:00-08:00 → ブロック
    if 4 <= hour <= 7:
        return False
    # JST 15:00-16:00 = Server 08:00-09:00
    if hour in [8, 9]:
        return True
    # JST 21:30-翌0:00 = Server 14:30-17:00
    if hour == 14 and minute >= 30:
        return True
    if hour in [15, 16]:
        return True
    return False

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
    print(f"\n{'='*60}")
    print(f"バックテスト: 初期資金 ¥{initial_balance:,}")
    print(f"{'='*60}")

    # リサンプリング
    print("リサンプリング中...")
    df5m  = resample(df1m, '5min')
    df15m = resample(df1m, '15min')
    df1h  = resample(df1m, '1h')
    df4h  = resample(df1m, '4h')

    # Stochastics計算
    print("Stochastics計算中...")
    k1m,  d1m  = calc_stoch(df1m,  K_PERIOD_SHORT, SLOWING_SHORT, D_PERIOD_SHORT)
    k5m,  d5m  = calc_stoch(df5m,  K_PERIOD_SHORT, SLOWING_SHORT, D_PERIOD_SHORT)
    k15m, d15m = calc_stoch(df15m, K_PERIOD_SHORT, SLOWING_SHORT, D_PERIOD_SHORT)
    k1h,  d1h  = calc_stoch(df1h,  K_PERIOD_SHORT, SLOWING_SHORT, D_PERIOD_SHORT)
    k4h,  d4h  = calc_stoch(df4h,  K_PERIOD_LONG,  SLOWING_LONG,  D_PERIOD_LONG)

    # 1M DataFrameに各時間足のStochasticsをマージ（前方結合）
    df1m = df1m.copy()
    df1m['k1m'] = k1m
    df1m['d1m'] = d1m

    # 5M → 1M にマージ
    df5m_s = df5m[['dt']].copy()
    df5m_s['k5m'] = k5m
    df5m_s['d5m'] = d5m
    df1m = pd.merge_asof(df1m.sort_values('dt'), df5m_s.sort_values('dt'),
                         on='dt', direction='backward')

    # 15M → 1M にマージ
    df15m_s = df15m[['dt']].copy()
    df15m_s['k15m'] = k15m
    df15m_s['d15m'] = d15m
    df15m_s['dt15'] = df15m['dt'].values
    df1m = pd.merge_asof(df1m.sort_values('dt'), df15m_s.sort_values('dt'),
                         on='dt', direction='backward')

    # 1H → 1M にマージ
    df1h_s = df1h[['dt']].copy()
    df1h_s['k1h'] = k1h
    df1h_s['d1h'] = d1h
    df1m = pd.merge_asof(df1m.sort_values('dt'), df1h_s.sort_values('dt'),
                         on='dt', direction='backward')

    # 4H → 1M にマージ
    df4h_s = df4h[['dt']].copy()
    df4h_s['k4h'] = k4h
    df4h_s['d4h'] = d4h
    df1m = pd.merge_asof(df1m.sort_values('dt'), df4h_s.sort_values('dt'),
                         on='dt', direction='backward')

    df1m = df1m.reset_index(drop=True)
    print(f"  マージ完了: {len(df1m):,}行")

    # ===== シミュレーション =====
    balance = float(initial_balance)
    trades = []

    in_position = False
    entry_price = 0.0
    entry_time = None
    position_side = None

    strategy_long  = False
    strategy_short = False

    current_date = None
    day_start_balance = balance
    consecutive_losses = 0
    day_blocked = False

    # 前の足の4Hクロス状態
    prev_k4h_above_d4h = None

    n = len(df1m)
    print("シミュレーション実行中...")

    for i in range(200, n):  # 先頭はウォームアップ
        row = df1m.iloc[i]
        dt = row['dt']

        # NaN チェック
        if pd.isna(row['k4h']) or pd.isna(row['k15m']) or pd.isna(row['k1m']):
            continue

        # 日次リセット
        d = dt.date()
        if d != current_date:
            current_date = d
            day_start_balance = balance
            consecutive_losses = 0
            day_blocked = False
            strategy_long  = False
            strategy_short = False
            prev_k4h_above_d4h = None

        # 4H戦略判定（クロス検出）
        k4h_above = row['k4h'] > row['d4h']
        if prev_k4h_above_d4h is not None:
            # ゴールデンクロス（下から上）かつ oversold圏
            if not prev_k4h_above_d4h and k4h_above and row['k4h'] <= OVERSOLD + 10:
                strategy_long  = True
                strategy_short = False
            # デッドクロス（上から下）かつ overbought圏
            elif prev_k4h_above_d4h and not k4h_above and row['k4h'] >= OVERBOUGHT - 10:
                strategy_short = True
                strategy_long  = False
        # 4Hが80以上到達でロング戦略終了
        if row['k4h'] >= OVERBOUGHT and strategy_long:
            strategy_long = False
        # 4Hが20以下到達でショート戦略終了
        if row['k4h'] <= OVERSOLD and strategy_short:
            strategy_short = False
        prev_k4h_above_d4h = k4h_above

        # ===== エグジット =====
        if in_position:
            exit_signal = False
            if position_side == 'long'  and row['k15m'] >= OVERBOUGHT:
                exit_signal = True
            elif position_side == 'short' and row['k15m'] <= OVERSOLD:
                exit_signal = True

            if exit_signal:
                exit_price = row['close']
                if position_side == 'long':
                    pnl_usd = (exit_price - entry_price - SPREAD_USD) * CONTRACT_SIZE * LOT_SIZE
                else:
                    pnl_usd = (entry_price - exit_price - SPREAD_USD) * CONTRACT_SIZE * LOT_SIZE
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
                    'k4h_at_entry': row['k4h'],
                    'k15m_at_exit': row['k15m'],
                })

                consecutive_losses = 0 if pnl_jpy > 0 else consecutive_losses + 1
                in_position = False

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
        if not strategy_long and not strategy_short:
            continue
        if not is_allowed_time(dt.hour, dt.minute):
            continue

        # 前の足との比較でクロス検出
        if i < 1:
            continue
        prev = df1m.iloc[i-1]
        if pd.isna(prev['k15m']) or pd.isna(prev['k1m']) or pd.isna(prev['k5m']):
            continue

        # 15M クロス
        cross15_up   = (prev['k15m'] < prev['d15m']) and (row['k15m'] > row['d15m']) and row['k15m'] <= OVERSOLD + 5
        cross15_down = (prev['k15m'] > prev['d15m']) and (row['k15m'] < row['d15m']) and row['k15m'] >= OVERBOUGHT - 5

        # 1M クロス
        cross1m_up   = (prev['k1m'] < prev['d1m']) and (row['k1m'] > row['d1m']) and row['k1m'] <= OVERSOLD + 5
        cross1m_down = (prev['k1m'] > prev['d1m']) and (row['k1m'] < row['d1m']) and row['k1m'] >= OVERBOUGHT - 5

        # 5M クロス
        cross5m_up   = (prev['k5m'] < prev['d5m']) and (row['k5m'] > row['d5m']) and row['k5m'] <= OVERSOLD + 5
        cross5m_down = (prev['k5m'] > prev['d5m']) and (row['k5m'] < row['d5m']) and row['k5m'] >= OVERBOUGHT - 5

        if strategy_long and cross15_up and (cross1m_up or cross5m_up):
            entry_price = row['close'] + SPREAD_USD
            in_position = True
            entry_time = dt
            position_side = 'long'

        elif strategy_short and cross15_down and (cross1m_down or cross5m_down):
            entry_price = row['close'] - SPREAD_USD
            in_position = True
            entry_time = dt
            position_side = 'short'

        if i % 100000 == 0 and i > 0:
            print(f"  進捗: {i/n*100:.1f}% | トレード数: {len(trades)} | 残高: ¥{balance:,.0f}")

    # 未決済ポジション強制クローズ
    if in_position:
        last = df1m.iloc[-1]
        ep = last['close']
        pnl_usd = (ep - entry_price - SPREAD_USD) * CONTRACT_SIZE * LOT_SIZE if position_side == 'long' \
                  else (entry_price - ep - SPREAD_USD) * CONTRACT_SIZE * LOT_SIZE
        pnl_jpy = pnl_usd * USD_JPY
        balance += pnl_jpy
        trades.append({
            'entry_time': entry_time, 'exit_time': last['dt'],
            'side': position_side, 'entry_price': entry_price, 'exit_price': ep,
            'pnl_usd': round(pnl_usd,4), 'pnl_jpy': round(pnl_jpy,2),
            'balance': round(balance,2), 'duration_min': (last['dt']-entry_time).total_seconds()/60,
            'k4h_at_entry': np.nan, 'k15m_at_exit': np.nan,
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
    win_rate = len(wins) / len(trades_df) * 100
    total_win  = wins['pnl_jpy'].sum()
    total_loss = abs(losses['pnl_jpy'].sum())
    pf = total_win / total_loss if total_loss > 0 else float('inf')

    # 最大DD
    bal_series = [initial_balance] + list(trades_df['balance'])
    peak = initial_balance
    max_dd_pct = 0.0
    for b in bal_series:
        if b > peak: peak = b
        dd_pct = (peak - b) / peak * 100
        if dd_pct > max_dd_pct: max_dd_pct = dd_pct

    # 連続勝敗
    signs = (trades_df['pnl_jpy'] > 0).tolist()
    max_cw = max_cl = cw = cl = 0
    for s in signs:
        if s: cw += 1; cl = 0
        else: cl += 1; cw = 0
        max_cw = max(max_cw, cw); max_cl = max(max_cl, cl)

    total_days = (trades_df['exit_time'].max() - trades_df['entry_time'].min()).days + 1
    final_balance = trades_df['balance'].iloc[-1]

    # 月次
    trades_df = trades_df.copy()
    trades_df['ym'] = trades_df['entry_time'].dt.to_period('M')
    monthly = trades_df.groupby('ym').agg(
        count=('pnl_jpy','count'),
        pnl=('pnl_jpy','sum'),
        win_rate=('pnl_jpy', lambda x: (x>0).mean()*100)
    )

    # 時間帯別（サーバー時間）
    trades_df['hour'] = trades_df['entry_time'].dt.hour
    hourly = trades_df.groupby('hour').agg(
        count=('pnl_jpy','count'),
        pnl=('pnl_jpy','sum'),
        win_rate=('pnl_jpy', lambda x: (x>0).mean()*100)
    )

    # 方向別
    side = trades_df.groupby('side').agg(
        count=('pnl_jpy','count'),
        pnl=('pnl_jpy','sum'),
        win_rate=('pnl_jpy', lambda x: (x>0).mean()*100),
        avg_pnl=('pnl_jpy','mean')
    )

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
        'hourly': hourly,
        'side': side,
    }

# ===== メイン =====
if __name__ == '__main__':
    df1m = load_data()
    results = {}

    for init_bal in INITIAL_BALANCES:
        trades_df, final_bal = run_backtest(df1m, init_bal)
        stats = analyze(trades_df, init_bal)
        results[init_bal] = {'trades': trades_df, 'stats': stats}

        if stats:
            s = stats
            print(f"\n--- ¥{init_bal:,} スタート 結果サマリー ---")
            print(f"総トレード数    : {s['total_trades']}")
            print(f"勝率            : {s['win_rate']:.1f}%")
            print(f"PF              : {s['profit_factor']:.2f}")
            print(f"最終残高        : ¥{s['final_balance']:,.0f}")
            print(f"総収益率        : {s['total_return_pct']:+.1f}%")
            print(f"最大DD          : {s['max_dd_pct']:.1f}%")
            print(f"1日あたり       : {s['trades_per_day']:.2f}回")
            print(f"1週間あたり     : {s['trades_per_week']:.2f}回")
            print(f"1ヶ月あたり     : {s['trades_per_month']:.2f}回")
            print(f"平均保有時間    : {s['avg_duration_min']:.0f}分")
        else:
            print(f"¥{init_bal:,}: トレードなし")

        if len(trades_df) > 0:
            trades_df.to_csv(f'{OUTPUT_DIR}/trades_{init_bal}.csv', index=False, encoding='utf-8-sig')

    with open(f'{OUTPUT_DIR}/backtest_results.pkl', 'wb') as f:
        pickle.dump(results, f)
    print("\n結果を保存しました")
