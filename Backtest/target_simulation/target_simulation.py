"""
月間収益目標達成シミュレーション
ロジック②の実績データから必要ロット・資金を逆算
"""
import pickle
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams
rcParams['font.family'] = 'Noto Sans CJK JP'

# データ読み込み
with open('backtest_results_logic2.pkl', 'rb') as f:
    results = pickle.load(f)

trades = results[10000]['trades']
df = pd.DataFrame(trades)
df['month'] = pd.to_datetime(df['exit_time']).dt.to_period('M')

monthly = df.groupby('month').agg(
    trades=('pnl_jpy', 'count'),
    win=('pnl_jpy', lambda x: (x > 0).sum()),
    pnl_sum=('pnl_jpy', 'sum'),
).reset_index()
monthly['winrate'] = monthly['win'] / monthly['trades'] * 100
monthly['month_str'] = monthly['month'].astype(str)

monthly_avg = monthly['pnl_sum'].mean()    # ¥753
monthly_median = monthly['pnl_sum'].median()  # ¥420

# 設定
GOLD_PRICE_USD = 3000
USD_JPY = 150
LOT_VALUE_JPY = GOLD_PRICE_USD * 100 * USD_JPY  # 1lot名目価値

# 目標ロット
lot_50m_avg = 500000 / (monthly_avg * 100)    # 6.6lot
lot_100m_avg = 1000000 / (monthly_avg * 100)  # 13.3lot

fig = plt.figure(figsize=(18, 20))
fig.patch.set_facecolor('#0d1117')

# タイトル
fig.suptitle('ロジック② 月間収益目標達成シミュレーション\nXAUUSD（GOLD） 2023年1月〜2026年2月',
             fontsize=16, color='white', fontweight='bold', y=0.98)

# ===== グラフ1: 月別損益（0.01lot基準）=====
ax1 = fig.add_axes([0.06, 0.78, 0.88, 0.16])
ax1.set_facecolor('#161b22')
colors = ['#2ea043' if v >= 0 else '#f85149' for v in monthly['pnl_sum']]
bars = ax1.bar(range(len(monthly)), monthly['pnl_sum'], color=colors, alpha=0.85, width=0.8)
ax1.axhline(y=monthly_avg, color='#f0c040', linewidth=1.5, linestyle='--', label=f'月平均 ¥{monthly_avg:.0f}')
ax1.axhline(y=monthly_median, color='#58a6ff', linewidth=1.5, linestyle=':', label=f'月中央値 ¥{monthly_median:.0f}')
ax1.axhline(y=0, color='white', linewidth=0.5, alpha=0.3)
ax1.set_xticks(range(0, len(monthly), 3))
ax1.set_xticklabels([monthly['month_str'].iloc[i] for i in range(0, len(monthly), 3)],
                     rotation=45, ha='right', fontsize=7, color='#8b949e')
ax1.set_ylabel('損益（円）\n0.01lot基準', color='#8b949e', fontsize=9)
ax1.tick_params(colors='#8b949e')
ax1.spines['bottom'].set_color('#30363d')
ax1.spines['left'].set_color('#30363d')
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
ax1.legend(fontsize=9, facecolor='#161b22', edgecolor='#30363d', labelcolor='white')
ax1.set_title('月別損益推移（0.01lot基準）', color='white', fontsize=11, pad=8)

# ===== グラフ2: 目標ロットでの月別損益シミュレーション =====
ax2 = fig.add_axes([0.06, 0.56, 0.88, 0.18])
ax2.set_facecolor('#161b22')

monthly_50m = monthly['pnl_sum'] * lot_50m_avg * 100
monthly_100m = monthly['pnl_sum'] * lot_100m_avg * 100

x = np.arange(len(monthly))
width = 0.4
bars1 = ax2.bar(x - width/2, monthly_50m / 10000, color='#2ea043', alpha=0.7, width=width, label=f'月50万円目標（{lot_50m_avg:.1f}lot）')
bars2 = ax2.bar(x + width/2, monthly_100m / 10000, color='#58a6ff', alpha=0.7, width=width, label=f'月100万円目標（{lot_100m_avg:.1f}lot）')
ax2.axhline(y=50, color='#2ea043', linewidth=1.5, linestyle='--', alpha=0.8)
ax2.axhline(y=100, color='#58a6ff', linewidth=1.5, linestyle='--', alpha=0.8)
ax2.axhline(y=0, color='white', linewidth=0.5, alpha=0.3)
ax2.set_xticks(range(0, len(monthly), 3))
ax2.set_xticklabels([monthly['month_str'].iloc[i] for i in range(0, len(monthly), 3)],
                     rotation=45, ha='right', fontsize=7, color='#8b949e')
ax2.set_ylabel('損益（万円）', color='#8b949e', fontsize=9)
ax2.tick_params(colors='#8b949e')
ax2.spines['bottom'].set_color('#30363d')
ax2.spines['left'].set_color('#30363d')
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.legend(fontsize=9, facecolor='#161b22', edgecolor='#30363d', labelcolor='white')
ax2.set_title('目標ロット運用時の月別損益シミュレーション', color='white', fontsize=11, pad=8)

# ===== グラフ3: 必要資金テーブル =====
ax3 = fig.add_axes([0.04, 0.30, 0.92, 0.22])
ax3.set_facecolor('#161b22')
ax3.axis('off')
ax3.set_title('必要資金・証拠金シミュレーション（GOLD価格$3,000 / USD/JPY 150円想定）',
              color='white', fontsize=11, pad=10)

# テーブルデータ
leverages = [2000, 1000, 500, 200]
col_labels = ['レバレッジ', '必要証拠金\n月50万円目標', '推奨口座残高\n月50万円目標', '必要証拠金\n月100万円目標', '推奨口座残高\n月100万円目標']
table_data = []
for lev in leverages:
    margin_per_lot = LOT_VALUE_JPY / lev
    m50_margin = margin_per_lot * lot_50m_avg
    m50_rec = m50_margin * 3
    m100_margin = margin_per_lot * lot_100m_avg
    m100_rec = m100_margin * 3
    table_data.append([
        f'{lev}倍',
        f'¥{m50_margin:,.0f}',
        f'¥{m50_rec:,.0f}',
        f'¥{m100_margin:,.0f}',
        f'¥{m100_rec:,.0f}',
    ])

table = ax3.table(
    cellText=table_data,
    colLabels=col_labels,
    cellLoc='center',
    loc='center',
    bbox=[0, 0, 1, 0.85]
)
table.auto_set_font_size(False)
table.set_fontsize(10)

for (row, col), cell in table.get_celld().items():
    cell.set_facecolor('#161b22')
    cell.set_edgecolor('#30363d')
    if row == 0:
        cell.set_facecolor('#21262d')
        cell.set_text_props(color='#f0c040', fontweight='bold', fontsize=9)
    else:
        if col == 0:
            cell.set_text_props(color='#58a6ff', fontweight='bold')
        elif col in [2, 4]:  # 推奨口座残高（強調）
            cell.set_text_props(color='#2ea043', fontweight='bold')
        else:
            cell.set_text_props(color='white')
        if row % 2 == 0:
            cell.set_facecolor('#1c2128')

# ===== グラフ4: リスク管理サマリー =====
ax4 = fig.add_axes([0.04, 0.04, 0.92, 0.22])
ax4.set_facecolor('#161b22')
ax4.axis('off')
ax4.set_title('リスク管理サマリー', color='white', fontsize=11, pad=10)

worst_month = monthly['pnl_sum'].min()
best_month = monthly['pnl_sum'].max()
profitable_months = (monthly['pnl_sum'] > 0).sum()

summary_data = [
    ['項目', '0.01lot基準', '月50万円目標\n（6.6lot）', '月100万円目標\n（13.3lot）'],
    ['月平均収益', f'¥{monthly_avg:.0f}', '¥500,000', '¥1,000,000'],
    ['月中央値収益', f'¥{monthly_median:.0f}', f'¥{monthly_median*lot_50m_avg*100:,.0f}', f'¥{monthly_median*lot_100m_avg*100:,.0f}'],
    ['月最大収益', f'¥{best_month:.0f}', f'¥{best_month*lot_50m_avg*100:,.0f}', f'¥{best_month*lot_100m_avg*100:,.0f}'],
    ['月最大損失', f'¥{worst_month:.0f}', f'¥{worst_month*lot_50m_avg*100:,.0f}', f'¥{worst_month*lot_100m_avg*100:,.0f}'],
    ['プラス月数', f'{profitable_months}/{len(monthly)}ヶ月（{profitable_months/len(monthly)*100:.0f}%）', '←同じ', '←同じ'],
    ['月平均トレード数', f'{monthly["trades"].mean():.0f}回', '←同じ', '←同じ'],
]

table2 = ax4.table(
    cellText=summary_data[1:],
    colLabels=summary_data[0],
    cellLoc='center',
    loc='center',
    bbox=[0, 0, 1, 0.85]
)
table2.auto_set_font_size(False)
table2.set_fontsize(10)

for (row, col), cell in table2.get_celld().items():
    cell.set_facecolor('#161b22')
    cell.set_edgecolor('#30363d')
    if row == 0:
        cell.set_facecolor('#21262d')
        cell.set_text_props(color='#f0c040', fontweight='bold', fontsize=9)
    else:
        if col == 0:
            cell.set_text_props(color='#8b949e')
        elif col == 1:
            cell.set_text_props(color='white')
        elif col == 2:
            cell.set_text_props(color='#2ea043', fontweight='bold')
        else:
            cell.set_text_props(color='#58a6ff', fontweight='bold')
        if row % 2 == 0:
            cell.set_facecolor('#1c2128')

plt.savefig('chart_target_simulation.png', dpi=150, bbox_inches='tight',
            facecolor='#0d1117', edgecolor='none')
print("chart_target_simulation.png を保存しました")

# PDFレポートも生成
report = f"""# ロジック② 月間収益目標達成シミュレーション

**検証期間**: 2023年1月〜2026年2月（38ヶ月）  
**銘柄**: XAUUSD（GOLD micro）  
**想定レート**: GOLD $3,000 / USD/JPY 150円

---

## 前提データ（0.01lot基準の実績）

| 指標 | 値 |
|------|:--:|
| 月平均収益 | ¥{monthly_avg:.0f} |
| 月中央値収益 | ¥{monthly_median:.0f} |
| 月最大収益 | ¥{best_month:.0f} |
| 月最大損失 | ¥{worst_month:.0f} |
| プラス月数 | {profitable_months}/{len(monthly)}ヶ月（{profitable_months/len(monthly)*100:.0f}%） |
| 月平均トレード数 | {monthly['trades'].mean():.0f}回 |
| 平均利益/トレード | ¥{df[df['pnl_jpy']>0]['pnl_jpy'].mean():.1f} |
| 平均損失/トレード | ¥{df[df['pnl_jpy']<0]['pnl_jpy'].mean():.1f} |

---

## 目標達成に必要なロット数

| 目標 | 必要ロット（月平均ベース） | 必要ロット（月中央値ベース） |
|------|:---------------------:|:----------------------:|
| **月50万円** | **{lot_50m_avg:.1f}lot** | {500000/(monthly_median*100):.1f}lot |
| **月100万円** | **{lot_100m_avg:.1f}lot** | {1000000/(monthly_median*100):.1f}lot |

> **月平均ベース**を基準に設計することを推奨します（中央値ベースは保守的すぎるため）

---

## 必要資金・証拠金シミュレーション

### 月50万円目標（{lot_50m_avg:.1f}lot）

| レバレッジ | 必要証拠金 | 推奨口座残高（証拠金×3） |
|-----------|:---------:|:--------------------:|
| 2,000倍 | ¥{LOT_VALUE_JPY/2000*lot_50m_avg:,.0f} | **¥{LOT_VALUE_JPY/2000*lot_50m_avg*3:,.0f}** |
| 1,000倍 | ¥{LOT_VALUE_JPY/1000*lot_50m_avg:,.0f} | **¥{LOT_VALUE_JPY/1000*lot_50m_avg*3:,.0f}** |
| 500倍 | ¥{LOT_VALUE_JPY/500*lot_50m_avg:,.0f} | **¥{LOT_VALUE_JPY/500*lot_50m_avg*3:,.0f}** |
| 200倍 | ¥{LOT_VALUE_JPY/200*lot_50m_avg:,.0f} | **¥{LOT_VALUE_JPY/200*lot_50m_avg*3:,.0f}** |

### 月100万円目標（{lot_100m_avg:.1f}lot）

| レバレッジ | 必要証拠金 | 推奨口座残高（証拠金×3） |
|-----------|:---------:|:--------------------:|
| 2,000倍 | ¥{LOT_VALUE_JPY/2000*lot_100m_avg:,.0f} | **¥{LOT_VALUE_JPY/2000*lot_100m_avg*3:,.0f}** |
| 1,000倍 | ¥{LOT_VALUE_JPY/1000*lot_100m_avg:,.0f} | **¥{LOT_VALUE_JPY/1000*lot_100m_avg*3:,.0f}** |
| 500倍 | ¥{LOT_VALUE_JPY/500*lot_100m_avg:,.0f} | **¥{LOT_VALUE_JPY/500*lot_100m_avg*3:,.0f}** |
| 200倍 | ¥{LOT_VALUE_JPY/200*lot_100m_avg:,.0f} | **¥{LOT_VALUE_JPY/200*lot_100m_avg*3:,.0f}** |

---

## リスク管理

### 最悪ケースシミュレーション

| 目標 | ロット | 最悪月の損失額 | 推奨口座残高に対する比率 |
|------|:------:|:------------:|:--------------------:|
| 月50万円 | {lot_50m_avg:.1f}lot | ¥{worst_month*lot_50m_avg*100:,.0f} | {abs(worst_month*lot_50m_avg*100)/(LOT_VALUE_JPY/2000*lot_50m_avg*3)*100:.1f}%（2000倍） |
| 月100万円 | {lot_100m_avg:.1f}lot | ¥{worst_month*lot_100m_avg*100:,.0f} | {abs(worst_month*lot_100m_avg*100)/(LOT_VALUE_JPY/2000*lot_100m_avg*3)*100:.1f}%（2000倍） |

### 推奨ブローカー別の最適設定

| ブローカー | レバレッジ | 月50万円目標の推奨口座残高 | 月100万円目標の推奨口座残高 |
|-----------|:--------:|:---------------------:|:----------------------:|
| **Exness** | 無制限〜2,000倍 | **¥{LOT_VALUE_JPY/2000*lot_50m_avg*3:,.0f}** | **¥{LOT_VALUE_JPY/2000*lot_100m_avg*3:,.0f}** |
| FXGT | 1,000倍 | ¥{LOT_VALUE_JPY/1000*lot_50m_avg*3:,.0f} | ¥{LOT_VALUE_JPY/1000*lot_100m_avg*3:,.0f} |
| Pepperstone | 200倍 | ¥{LOT_VALUE_JPY/200*lot_50m_avg*3:,.0f} | ¥{LOT_VALUE_JPY/200*lot_100m_avg*3:,.0f} |

---

## 重要な注意事項

1. **月平均収益は保証されません**: 実績38ヶ月中8ヶ月がマイナスです。月単位では損失月もあります。
2. **スプレッドの影響**: バックテストは固定$0.30スプレッドです。実際のスプレッドは変動し、特にNY市場オープン直後は広がります。
3. **スリッページ**: 高ロット運用では約定スリッページが発生する場合があります。
4. **証拠金維持率**: 推奨口座残高は証拠金の3倍を目安にしています。最低でも2倍以上を維持してください。
5. **段階的なロットアップ**: いきなり目標ロットで運用せず、0.1lot → 1lot → 目標ロットと段階的に増やすことを強く推奨します。
"""

with open('report_target_simulation.md', 'w', encoding='utf-8') as f:
    f.write(report)
print("report_target_simulation.md を保存しました")
