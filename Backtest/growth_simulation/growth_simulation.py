"""
段階的ロットアップ 目標残高到達期間シミュレーション
¥50,000スタート → ¥100,000 → ¥500,000 → ¥1,000,000
各残高到達時点でロットを段階的に引き上げる
"""

import pickle
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyArrowPatch

# 日本語フォント設定
font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
fp = fm.FontProperties(fname=font_path)
plt.rcParams['font.family'] = fp.get_name()
plt.rcParams['axes.unicode_minus'] = False

# ===== 設定 =====
INITIAL_BALANCE = 50_000
RUIN_LINE       = 15_000      # 破産ライン（初期の30%）
N_SIMULATIONS   = 10_000
MAX_MONTHS      = 120         # 最大10年
SCALE           = 10          # バックテスト損益の実際スケール

# ===== 段階的ロット設定 =====
# 残高がしきい値に達したらロットを切り替える
LOT_STAGES = [
    {'threshold': 0,         'lot': 0.01, 'label': '¥5万〜：0.01lot'},
    {'threshold': 100_000,   'lot': 0.05, 'label': '¥10万〜：0.05lot'},
    {'threshold': 500_000,   'lot': 0.20, 'label': '¥50万〜：0.20lot'},
    {'threshold': 1_000_000, 'lot': 0.66, 'label': '¥100万〜：0.66lot'},
]

TARGET_BALANCES = [100_000, 500_000, 1_000_000]
TARGET_LABELS   = ['¥10万', '¥50万', '¥100万']

# ===== バックテストデータ読み込み =====
with open('backtest_results_logic2.pkl', 'rb') as f:
    results = pickle.load(f)

trades_df = pd.DataFrame(results[10000]['trades'])
trades_df['pnl_real'] = trades_df['pnl_jpy'] * SCALE  # 0.01lot実際損益

pnl_array      = trades_df['pnl_real'].values
monthly_trades = len(trades_df) / 38.0  # 月平均トレード数

print(f"0.01lot 1トレード平均損益: ¥{pnl_array.mean():.1f}")
print(f"0.01lot 1トレード最大損失: ¥{pnl_array.min():.1f}")
print(f"月平均トレード数: {monthly_trades:.1f}回")

# ===== モンテカルロシミュレーション =====
np.random.seed(42)

# 各シミュレーションの月別残高と目標到達月を記録
all_curves          = []
target_reach_months = {t: [] for t in TARGET_BALANCES}  # 到達月リスト（破産除く）
ruin_count          = 0

for sim in range(N_SIMULATIONS):
    balance = INITIAL_BALANCE
    curve   = [balance]
    ruined  = False
    reached = {t: None for t in TARGET_BALANCES}

    for month in range(1, MAX_MONTHS + 1):
        # 現在の残高に応じたロット決定
        current_lot = LOT_STAGES[0]['lot']
        for stage in LOT_STAGES:
            if balance >= stage['threshold']:
                current_lot = stage['lot']

        # 月間トレード数（正規分布でばらつかせる）
        n_trades = int(np.random.normal(monthly_trades, monthly_trades * 0.3))
        n_trades = max(5, n_trades)

        # 損益サンプリング（実績分布から）
        sampled_pnl  = np.random.choice(pnl_array, size=n_trades, replace=True)
        lot_scale    = current_lot / 0.01  # 0.01lot基準のスケール
        monthly_pnl  = sampled_pnl.sum() * lot_scale

        balance += monthly_pnl
        curve.append(balance)

        # 目標到達チェック
        for target in TARGET_BALANCES:
            if reached[target] is None and balance >= target:
                reached[target] = month

        # 破産チェック
        if balance <= RUIN_LINE:
            ruined = True
            ruin_count += 1
            break

    # 結果記録
    all_curves.append(curve)
    if not ruined:
        for target in TARGET_BALANCES:
            if reached[target] is not None:
                target_reach_months[target].append(reached[target])

ruin_prob = ruin_count / N_SIMULATIONS * 100
print(f"\n破産確率（段階的ロット）: {ruin_prob:.1f}%")

# ===== 統計集計 =====
stats = {}
for target, label in zip(TARGET_BALANCES, TARGET_LABELS):
    months_list = target_reach_months[target]
    reach_rate  = len(months_list) / N_SIMULATIONS * 100

    if len(months_list) > 0:
        p25 = np.percentile(months_list, 25)
        p50 = np.percentile(months_list, 50)
        p75 = np.percentile(months_list, 75)
        p90 = np.percentile(months_list, 90)
        avg = np.mean(months_list)
    else:
        p25 = p50 = p75 = p90 = avg = None

    stats[target] = {
        'label':      label,
        'reach_rate': reach_rate,
        'p25':        p25,
        'p50':        p50,
        'p75':        p75,
        'p90':        p90,
        'avg':        avg,
        'months':     months_list,
    }
    print(f"\n{label} 到達統計:")
    print(f"  到達率: {reach_rate:.1f}%")
    if avg:
        print(f"  平均: {avg:.1f}ヶ月")
        print(f"  中央値(50%): {p50:.1f}ヶ月")
        print(f"  楽観(25%): {p25:.1f}ヶ月")
        print(f"  悲観(75%): {p75:.1f}ヶ月")
        print(f"  最悪(90%): {p90:.1f}ヶ月")

# ===== 可視化 =====
fig = plt.figure(figsize=(20, 16))
fig.patch.set_facecolor('#0d1117')
gs = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35)

fig.suptitle('段階的ロットアップ 目標残高到達シミュレーション\n¥50,000スタート → ¥10万 → ¥50万 → ¥100万',
             fontsize=15, color='white', fontweight='bold', y=0.99)

# --- 上段：エクイティカーブ（全体） ---
ax_main = fig.add_subplot(gs[0, :])
ax_main.set_facecolor('#161b22')

curves_arr = [np.array(c) for c in all_curves]
max_len    = max(len(c) for c in curves_arr)
padded     = np.array([np.pad(c, (0, max_len - len(c)), constant_values=c[-1]) for c in curves_arr])

months_x = np.arange(max_len)
p10 = np.percentile(padded, 10, axis=0)
p25 = np.percentile(padded, 25, axis=0)
p50 = np.percentile(padded, 50, axis=0)
p75 = np.percentile(padded, 75, axis=0)
p90 = np.percentile(padded, 90, axis=0)

ax_main.fill_between(months_x, p10, p90, alpha=0.12, color='#4fc3f7', label='10〜90%')
ax_main.fill_between(months_x, p25, p75, alpha=0.22, color='#4fc3f7', label='25〜75%')
ax_main.plot(months_x, p50, color='#4fc3f7', linewidth=2.5, label='中央値')

# 目標ラインと到達中央値
target_colors = ['#00ff88', '#ffdd00', '#ff6b6b']
for target, label, color in zip(TARGET_BALANCES, TARGET_LABELS, target_colors):
    ax_main.axhline(y=target, color=color, linestyle='--', alpha=0.7, linewidth=1.5)
    p50_month = stats[target]['p50']
    if p50_month:
        ax_main.axvline(x=p50_month, color=color, linestyle=':', alpha=0.5, linewidth=1)
        ax_main.text(p50_month + 0.5, target * 1.05,
                     f'{label}\n中央値{p50_month:.0f}ヶ月',
                     color=color, fontsize=8, fontweight='bold')

ax_main.axhline(y=RUIN_LINE, color='#ff3333', linestyle='-', alpha=0.5, linewidth=1, label='破産ライン')
ax_main.set_xlim(0, min(max_len, 60))
ax_main.set_ylim(-50_000, 1_500_000)
ax_main.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'¥{x/10000:.0f}万'))
ax_main.set_xlabel('月数', color='#aaa', fontsize=10)
ax_main.set_ylabel('口座残高', color='#aaa', fontsize=10)
ax_main.set_title(f'エクイティカーブ（10,000回シミュレーション） | 破産確率: {ruin_prob:.1f}%',
                  color='white', fontsize=11, pad=8)
ax_main.tick_params(colors='#aaa')
ax_main.spines['bottom'].set_color('#444')
ax_main.spines['left'].set_color('#444')
ax_main.spines['top'].set_visible(False)
ax_main.spines['right'].set_visible(False)
ax_main.legend(facecolor='#161b22', labelcolor='white', fontsize=9, loc='upper left')

# --- 中段：目標別ヒストグラム ---
for idx, (target, label, color) in enumerate(zip(TARGET_BALANCES, TARGET_LABELS, target_colors)):
    ax = fig.add_subplot(gs[1, idx])
    ax.set_facecolor('#161b22')

    months_list = stats[target]['months']
    reach_rate  = stats[target]['reach_rate']
    p50_val     = stats[target]['p50']
    p25_val     = stats[target]['p25']
    p75_val     = stats[target]['p75']

    if len(months_list) > 0:
        ax.hist(months_list, bins=40, color=color, alpha=0.7, edgecolor='none')
        ax.axvline(x=p25_val, color='white', linestyle='--', alpha=0.6, linewidth=1.5, label=f'楽観 {p25_val:.0f}ヶ月')
        ax.axvline(x=p50_val, color=color,   linestyle='-',  alpha=0.9, linewidth=2.5, label=f'中央値 {p50_val:.0f}ヶ月')
        ax.axvline(x=p75_val, color='#aaa',  linestyle='--', alpha=0.6, linewidth=1.5, label=f'悲観 {p75_val:.0f}ヶ月')

    ax.set_title(f'{label} 到達期間分布\n到達率: {reach_rate:.1f}%',
                 color=color, fontsize=10, fontweight='bold')
    ax.set_xlabel('到達月数', color='#aaa', fontsize=9)
    ax.set_ylabel('シミュレーション数', color='#aaa', fontsize=9)
    ax.tick_params(colors='#aaa', labelsize=8)
    ax.spines['bottom'].set_color('#444')
    ax.spines['left'].set_color('#444')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.legend(facecolor='#161b22', labelcolor='white', fontsize=8)

# --- 下段：ロードマップ表 ---
ax_table = fig.add_subplot(gs[2, :])
ax_table.set_facecolor('#0d1117')
ax_table.axis('off')

table_data = [
    ['フェーズ', '口座残高', 'ロット', '月収益目標', '到達率', '楽観(25%)', '中央値(50%)', '悲観(75%)'],
    ['テスト', '¥5万〜', '0.01lot', '¥7,500', '—', '—', '—', '—'],
]

for target, label, color in zip(TARGET_BALANCES, TARGET_LABELS, target_colors):
    s = stats[target]
    monthly_income = pnl_array.mean() * (target / 0.01 / 0.01) / 100  # 概算
    lot_map = {100_000: '0.05lot', 500_000: '0.20lot', 1_000_000: '0.66lot'}
    income_map = {100_000: '¥37,500', 500_000: '¥150,000', 1_000_000: '¥500,000'}
    phase_map = {100_000: '拡張①', 500_000: '拡張②', 1_000_000: '目標'}

    p25_str = f'{s["p25"]:.0f}ヶ月' if s['p25'] else '—'
    p50_str = f'{s["p50"]:.0f}ヶ月' if s['p50'] else '—'
    p75_str = f'{s["p75"]:.0f}ヶ月' if s['p75'] else '—'

    table_data.append([
        phase_map[target], label, lot_map[target], income_map[target],
        f'{s["reach_rate"]:.1f}%', p25_str, p50_str, p75_str
    ])

table = ax_table.table(
    cellText=table_data[1:],
    colLabels=table_data[0],
    loc='center',
    cellLoc='center',
)
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1.2, 2.2)

# テーブルスタイリング
header_color = '#1f2937'
row_colors   = ['#161b22', '#1a2030']
phase_colors = {'テスト': '#2d4a3e', '拡張①': '#2d3a4a', '拡張②': '#3a2d4a', '目標': '#4a2d2d'}

for (row, col), cell in table.get_celld().items():
    cell.set_edgecolor('#444')
    if row == 0:
        cell.set_facecolor(header_color)
        cell.set_text_props(color='white', fontweight='bold')
    else:
        phase = table_data[row][0]
        cell.set_facecolor(phase_colors.get(phase, row_colors[row % 2]))
        cell.set_text_props(color='white')

ax_table.set_title('段階的ロットアップ ロードマップ', color='white', fontsize=12, fontweight='bold', pad=10)

plt.savefig('chart_growth_simulation.png', dpi=150, bbox_inches='tight',
            facecolor='#0d1117', edgecolor='none')
print("\nチャート保存: chart_growth_simulation.png")

# ===== Markdownレポート =====
md_lines = [
    "# 段階的ロットアップ 目標残高到達シミュレーション\n",
    "## 前提条件\n",
    "| 項目 | 設定値 |",
    "|------|--------|",
    "| 初期残高 | ¥50,000 |",
    "| 破産ライン | ¥15,000（初期の30%） |",
    "| シミュレーション回数 | 10,000回（モンテカルロ法） |",
    "| 最大シミュレーション期間 | 120ヶ月（10年） |",
    "| 使用データ | XM GOLD 実績トレード 1,281件（2023年1月〜2026年2月） |",
    "",
    "## ロット段階設定\n",
    "| フェーズ | 残高条件 | ロット | 月収益目標（期待値） |",
    "|---------|---------|:-----:|:-----------------:|",
    "| テスト | ¥5万〜 | 0.01lot | ¥7,500 |",
    "| 拡張① | ¥10万達成後 | 0.05lot | ¥37,500 |",
    "| 拡張② | ¥50万達成後 | 0.20lot | ¥150,000 |",
    "| 目標 | ¥100万達成後 | 0.66lot | ¥500,000 |",
    "",
    f"## シミュレーション結果（破産確率: {ruin_prob:.1f}%）\n",
    "| 目標残高 | 到達率 | 楽観（25%） | 中央値（50%） | 悲観（75%） | 最悪（90%） |",
    "|---------|:-----:|:---------:|:-----------:|:---------:|:---------:|",
]

for target, label in zip(TARGET_BALANCES, TARGET_LABELS):
    s = stats[target]
    p25_str = f'{s["p25"]:.0f}ヶ月' if s['p25'] else '—'
    p50_str = f'{s["p50"]:.0f}ヶ月' if s['p50'] else '—'
    p75_str = f'{s["p75"]:.0f}ヶ月' if s['p75'] else '—'
    p90_str = f'{s["p90"]:.0f}ヶ月' if s['p90'] else '—'
    md_lines.append(f"| {label} | {s['reach_rate']:.1f}% | {p25_str} | {p50_str} | {p75_str} | {p90_str} |")

md_lines += [
    "",
    "## 解説\n",
    "- **楽観（25%）**: シミュレーションの上位25%が到達する月数（運が良い場合）",
    "- **中央値（50%）**: 最も現実的な到達月数",
    "- **悲観（75%）**: シミュレーションの75%が到達する月数（運が悪い場合）",
    "- **最悪（90%）**: シミュレーションの90%が到達する月数",
    "",
    "## 注意事項\n",
    "- バックテストはスプレッド固定・スリッページ未考慮のため、実際の結果は異なる場合があります",
    "- 現在のGOLD相場は1日$100以上動くことがあり、最大損失が大きくなる可能性があります",
    "- 段階的ロットアップは「残高が目標に達した時点で即座にロットを上げる」設計です",
    "- 実運用では数ヶ月の安定稼働を確認してからロットアップすることを推奨します",
]

with open('report_growth_simulation.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(md_lines))
print("レポート保存: report_growth_simulation.md")
