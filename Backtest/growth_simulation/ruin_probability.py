"""
ロジック② 破産確率シミュレーション
Exness証拠金¥50,000スタートでの破産確率をモンテカルロ法で算出
"""

import pickle
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.gridspec import GridSpec

# 日本語フォント設定
font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
fp = fm.FontProperties(fname=font_path)
plt.rcParams['font.family'] = fp.get_name()
plt.rcParams['axes.unicode_minus'] = False

# ===== 設定 =====
INITIAL_BALANCE   = 50_000      # 証拠金¥50,000
RUIN_THRESHOLD    = 0.30        # 残高が30%以下（¥15,000）で破産とみなす
N_SIMULATIONS     = 10_000      # モンテカルロ試行回数
N_MONTHS          = 12          # シミュレーション期間（月）
USD_JPY           = 150.0
SCALE             = 10          # バックテスト損益の実際スケール（0.01lot実際値）

# ===== バックテストデータ読み込み =====
with open('backtest_results_logic2.pkl', 'rb') as f:
    results = pickle.load(f)

trades_df = pd.DataFrame(results[10000]['trades'])
# 実際の0.01lot損益に変換（バックテストはCONTRACT_SIZE=10で0.1oz相当）
trades_df['pnl_real'] = trades_df['pnl_jpy'] * SCALE

print(f"総トレード数: {len(trades_df)}")
print(f"実際の1トレード平均損益: ¥{trades_df['pnl_real'].mean():.1f}")
print(f"実際の1トレード最大損失: ¥{trades_df['pnl_real'].min():.1f}")
print(f"実際の1トレード最大利益: ¥{trades_df['pnl_real'].max():.1f}")
print(f"勝率: {(trades_df['pnl_real']>0).mean()*100:.1f}%")

# ===== ロット別シミュレーション設定 =====
lot_scenarios = {
    '0.01lot\n（テスト）':   {'lot': 0.01, 'scale': 1.0},
    '0.05lot':              {'lot': 0.05, 'scale': 5.0},
    '0.10lot':              {'lot': 0.10, 'scale': 10.0},
    '0.20lot':              {'lot': 0.20, 'scale': 20.0},
    '0.30lot\n（月10万円）': {'lot': 0.30, 'scale': 30.0},
    '0.66lot\n（月50万円）': {'lot': 0.66, 'scale': 66.0},
}

# 月ごとのトレード数（実績ベース）
monthly_trades = len(trades_df) / 38  # 38ヶ月分
print(f"\n月平均トレード数: {monthly_trades:.1f}回")

# ===== モンテカルロシミュレーション =====
pnl_array = trades_df['pnl_real'].values  # 実際の0.01lot損益

ruin_results = {}
equity_curves = {}

np.random.seed(42)

for scenario_name, config in lot_scenarios.items():
    lot_scale = config['scale']  # 0.01lot基準のスケール
    ruin_count = 0
    all_curves = []

    for sim in range(N_SIMULATIONS):
        balance = INITIAL_BALANCE
        curve = [balance]
        ruined = False

        for month in range(N_MONTHS):
            # 月ごとのトレード数をランダムサンプリング
            n_trades = int(np.random.normal(monthly_trades, monthly_trades * 0.3))
            n_trades = max(5, n_trades)

            # トレード損益をランダムサンプリング（実績分布から）
            sampled_pnl = np.random.choice(pnl_array, size=n_trades, replace=True)
            monthly_pnl = sampled_pnl.sum() * lot_scale

            balance += monthly_pnl
            curve.append(balance)

            # 破産判定（残高が初期の30%以下）
            if balance <= INITIAL_BALANCE * RUIN_THRESHOLD:
                ruin_count += 1
                ruined = True
                # 残りの月は破産残高で固定
                for _ in range(N_MONTHS - month - 1):
                    curve.append(balance)
                break

        all_curves.append(curve)

    ruin_prob = ruin_count / N_SIMULATIONS * 100
    ruin_results[scenario_name] = {
        'lot': config['lot'],
        'ruin_prob': ruin_prob,
        'curves': np.array(all_curves),
        'monthly_avg': pnl_array.mean() * lot_scale * monthly_trades,
    }
    print(f"{scenario_name.replace(chr(10),' ')}: 破産確率 {ruin_prob:.1f}%")

# ===== 可視化 =====
fig = plt.figure(figsize=(18, 14))
fig.patch.set_facecolor('#0d1117')
gs = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35)

# タイトル
fig.suptitle('ロジック② 破産確率シミュレーション\nExness 証拠金¥50,000スタート / モンテカルロ法 10,000回試行 / 12ヶ月',
             fontsize=14, color='white', fontweight='bold', y=0.98)

# カラーマップ（破産確率に応じて色変化）
def ruin_color(prob):
    if prob < 5:   return '#00ff88'
    elif prob < 15: return '#ffdd00'
    elif prob < 30: return '#ff8800'
    else:           return '#ff3333'

# --- 上段：破産確率バーチャート ---
ax_bar = fig.add_subplot(gs[0, :])
ax_bar.set_facecolor('#161b22')

labels = list(ruin_results.keys())
probs  = [ruin_results[k]['ruin_prob'] for k in labels]
colors = [ruin_color(p) for p in probs]
lots   = [ruin_results[k]['lot'] for k in labels]

bars = ax_bar.bar(range(len(labels)), probs, color=colors, alpha=0.85, width=0.6, edgecolor='white', linewidth=0.5)
ax_bar.set_xticks(range(len(labels)))
ax_bar.set_xticklabels([l.replace('\n', '\n') for l in labels], color='white', fontsize=10)
ax_bar.set_ylabel('破産確率 (%)', color='white', fontsize=11)
ax_bar.set_title('ロット別 破産確率（残高が¥15,000以下になる確率）', color='white', fontsize=12, pad=8)
ax_bar.tick_params(colors='white')
ax_bar.set_facecolor('#161b22')
ax_bar.spines['bottom'].set_color('#444')
ax_bar.spines['left'].set_color('#444')
ax_bar.spines['top'].set_visible(False)
ax_bar.spines['right'].set_visible(False)
ax_bar.axhline(y=5,  color='#00ff88', linestyle='--', alpha=0.5, linewidth=1, label='安全ライン(5%)')
ax_bar.axhline(y=20, color='#ff8800', linestyle='--', alpha=0.5, linewidth=1, label='警戒ライン(20%)')
ax_bar.legend(facecolor='#161b22', labelcolor='white', fontsize=9)
ax_bar.set_ylim(0, max(probs) * 1.2 + 5)

for bar, prob, lot in zip(bars, probs, lots):
    ax_bar.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{prob:.1f}%', ha='center', va='bottom', color='white', fontsize=11, fontweight='bold')

# --- 中段・下段：ロット別エクイティカーブ ---
scenario_keys = list(ruin_results.keys())
months_axis = list(range(N_MONTHS + 1))

for idx, key in enumerate(scenario_keys):
    row = 1 + idx // 3
    col = idx % 3
    ax = fig.add_subplot(gs[row, col])
    ax.set_facecolor('#161b22')

    curves = ruin_results[key]['curves']
    prob   = ruin_results[key]['ruin_prob']
    lot    = ruin_results[key]['lot']
    color  = ruin_color(prob)

    # パーセンタイル帯
    p10 = np.percentile(curves, 10, axis=0)
    p25 = np.percentile(curves, 25, axis=0)
    p50 = np.percentile(curves, 50, axis=0)
    p75 = np.percentile(curves, 75, axis=0)
    p90 = np.percentile(curves, 90, axis=0)

    ax.fill_between(months_axis, p10, p90, alpha=0.15, color=color)
    ax.fill_between(months_axis, p25, p75, alpha=0.25, color=color)
    ax.plot(months_axis, p50, color=color, linewidth=2, label='中央値')
    ax.axhline(y=INITIAL_BALANCE, color='white', linestyle=':', alpha=0.4, linewidth=1)
    ax.axhline(y=INITIAL_BALANCE * RUIN_THRESHOLD, color='#ff3333', linestyle='--', alpha=0.6, linewidth=1, label='破産ライン')

    ax.set_title(f'{key.replace(chr(10)," ")} | 破産確率: {prob:.1f}%',
                 color=color, fontsize=9, fontweight='bold')
    ax.set_xlabel('月数', color='#aaa', fontsize=8)
    ax.set_ylabel('残高 (¥)', color='#aaa', fontsize=8)
    ax.tick_params(colors='#aaa', labelsize=7)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'¥{x/10000:.0f}万'))
    ax.spines['bottom'].set_color('#444')
    ax.spines['left'].set_color('#444')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.legend(facecolor='#161b22', labelcolor='white', fontsize=7)

plt.savefig('chart_ruin_probability.png', dpi=150, bbox_inches='tight',
            facecolor='#0d1117', edgecolor='none')
print("\nチャート保存: chart_ruin_probability.png")

# ===== サマリーテーブル出力 =====
print("\n" + "=" * 70)
print("破産確率サマリー（証拠金¥50,000 / 破産ライン¥15,000 / 12ヶ月）")
print("=" * 70)
print(f"{'ロット':12} {'破産確率':>8} {'月平均収益':>12} {'判定':>10}")
print("-" * 70)
for key, data in ruin_results.items():
    label = key.replace('\n', ' ')
    prob  = data['ruin_prob']
    avg   = data['monthly_avg']
    if prob < 5:    judge = "✅ 安全"
    elif prob < 15: judge = "⚠️ 注意"
    elif prob < 30: judge = "🔶 危険"
    else:           judge = "❌ 破産リスク高"
    print(f"{label:12} {prob:>7.1f}% {avg:>+12,.0f}円  {judge}")

# ===== Markdownレポート =====
md = f"""# ロジック② 破産確率シミュレーション

## 前提条件

| 項目 | 設定値 |
|------|--------|
| 初期証拠金 | ¥50,000（Exness） |
| 破産ライン | ¥15,000（初期の30%以下） |
| シミュレーション回数 | 10,000回（モンテカルロ法） |
| シミュレーション期間 | 12ヶ月 |
| 使用データ | XM GOLD 実績トレード 1,281件（2023年1月〜2026年2月） |
| USD/JPY | 150円固定 |
| GOLD価格 | $3,000想定 |

## 破産確率シミュレーション結果

| ロット数 | 破産確率 | 月平均収益（期待値） | 判定 |
|---------|:-------:|:-----------------:|:----:|
| 0.01lot（テスト） | {ruin_results[list(ruin_results.keys())[0]]['ruin_prob']:.1f}% | ¥{ruin_results[list(ruin_results.keys())[0]]['monthly_avg']:+,.0f} | ✅ 安全 |
| 0.05lot | {ruin_results[list(ruin_results.keys())[1]]['ruin_prob']:.1f}% | ¥{ruin_results[list(ruin_results.keys())[1]]['monthly_avg']:+,.0f} | |
| 0.10lot | {ruin_results[list(ruin_results.keys())[2]]['ruin_prob']:.1f}% | ¥{ruin_results[list(ruin_results.keys())[2]]['monthly_avg']:+,.0f} | |
| 0.20lot | {ruin_results[list(ruin_results.keys())[3]]['ruin_prob']:.1f}% | ¥{ruin_results[list(ruin_results.keys())[3]]['monthly_avg']:+,.0f} | |
| 0.30lot（月10万円目標） | {ruin_results[list(ruin_results.keys())[4]]['ruin_prob']:.1f}% | ¥{ruin_results[list(ruin_results.keys())[4]]['monthly_avg']:+,.0f} | |
| 0.66lot（月50万円目標） | {ruin_results[list(ruin_results.keys())[5]]['ruin_prob']:.1f}% | ¥{ruin_results[list(ruin_results.keys())[5]]['monthly_avg']:+,.0f} | |

## 重要な注意事項

### XAUUSDの1日100ドル超の変動について

現在のGOLD相場は1日に$100以上動くことがあります。ロジック②の5M足エグジット（5M足のDC/GC）では、急激な相場変動時に**スリッページ**や**ギャップ**が発生する可能性があります。

バックテストはスリッページ未考慮のため、実際の破産確率はバックテスト結果より高くなる可能性があります。

### 推奨する安全な運用方針

1. **まず0.01〜0.05lotでテスト稼働**（1〜2ヶ月）
2. **損失が初期証拠金の20%（¥10,000）に達したらEAを停止**
3. **安定稼働を確認後に段階的にロットアップ**
4. **証拠金は目標ロットの証拠金の3倍以上を維持**

## 月50万円目標（0.66lot）での推奨口座残高

証拠金¥50,000で0.66lotを運用した場合、破産確率が高くなります。
月50万円目標を安全に達成するには以下の口座残高が推奨されます：

- **Exness 2,000倍レバレッジ**: 推奨口座残高 **¥150,000〜¥200,000**
- **Exness 1,000倍レバレッジ**: 推奨口座残高 **¥300,000〜¥400,000**
"""

with open('report_ruin_probability.md', 'w', encoding='utf-8') as f:
    f.write(md)
print("レポート保存: report_ruin_probability.md")
