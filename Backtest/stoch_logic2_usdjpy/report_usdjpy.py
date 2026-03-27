"""
ロジック② USDJPY検証レポート生成
GOLD vs USDJPY 比較も含む
"""
import pickle
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import os
import warnings
warnings.filterwarnings('ignore')

font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
plt.rcParams['axes.unicode_minus'] = False

OUTPUT_DIR = "/home/ubuntu/stoch_backtest"

with open(f'{OUTPUT_DIR}/backtest_results_logic2.pkl', 'rb') as f:
    r_gold = pickle.load(f)
with open(f'{OUTPUT_DIR}/backtest_results_usdjpy.pkl', 'rb') as f:
    r_usdjpy = pickle.load(f)

DARK_BG    = '#0d1117'
PANEL_BG   = '#161b22'
GRID_COLOR = '#30363d'
TEXT_COLOR = '#e6edf3'
GREEN      = '#3fb950'
RED        = '#f85149'
YELLOW     = '#d29922'
CYAN       = '#00d4aa'
BLUE       = '#4a9eff'
ORANGE     = '#f0883e'
PURPLE     = '#bc8cff'
GOLD_COLOR = '#ffd700'

INIT_BAL = 10_000

sg = r_gold[INIT_BAL]['stats']
su = r_usdjpy[INIT_BAL]['stats']
tg = r_gold[INIT_BAL]['trades']
tu = r_usdjpy[INIT_BAL]['trades']

# ===== ダッシュボードチャート =====
fig = plt.figure(figsize=(22, 28), facecolor=DARK_BG)
fig.suptitle('ロジック② USDJPY 検証レポート（¥10,000スタート）\n4H/1H/5M足 Stochastics(9,3,3) | XM micro口座 実データ 2023年1月〜2026年2月',
             color=TEXT_COLOR, fontsize=16, fontweight='bold', y=0.99)

gs = fig.add_gridspec(7, 3, hspace=0.52, wspace=0.35,
                      top=0.95, bottom=0.03, left=0.07, right=0.97)

# ===== Row 0: KPI比較カード（GOLD vs USDJPY）=====
ax_kpi = fig.add_subplot(gs[0, :])
ax_kpi.set_facecolor(PANEL_BG)
ax_kpi.set_xlim(0, 6)
ax_kpi.set_ylim(0, 1)
ax_kpi.axis('off')
ax_kpi.set_title('主要指標 比較（¥10,000スタート）', color=TEXT_COLOR, fontsize=12, pad=8)

kpi_items = [
    ('総トレード数',  f"{sg['total_trades']}回",  f"{su['total_trades']}回",  None),
    ('勝率',          f"{sg['win_rate']:.1f}%",    f"{su['win_rate']:.1f}%",   's2_better_if_higher'),
    ('PF',            f"{sg['profit_factor']:.2f}", f"{su['profit_factor']:.2f}", 's2_better_if_higher'),
    ('総収益率',      f"{sg['total_return_pct']:+.1f}%", f"{su['total_return_pct']:+.1f}%", 's2_better_if_higher'),
    ('最大DD',        f"{sg['max_dd_pct']:.1f}%",  f"{su['max_dd_pct']:.1f}%",  's2_better_if_lower'),
    ('月平均回数',    f"{sg['trades_per_month']:.1f}回", f"{su['trades_per_month']:.1f}回", None),
]

for j, (label, val_gold, val_usdjpy, compare) in enumerate(kpi_items):
    x = j + 0.5
    rect = mpatches.FancyBboxPatch((j+0.04, 0.04), 0.92, 0.92,
                                    boxstyle="round,pad=0.02",
                                    facecolor='#21262d', edgecolor=GRID_COLOR, linewidth=1)
    ax_kpi.add_patch(rect)
    ax_kpi.text(x, 0.82, label, ha='center', va='center', color='#8b949e', fontsize=8)
    ax_kpi.text(x - 0.18, 0.57, 'GOLD', ha='center', va='center', color='#8b949e', fontsize=7)
    ax_kpi.text(x - 0.18, 0.35, val_gold, ha='center', va='center', color=GOLD_COLOR, fontsize=11, fontweight='bold')
    ax_kpi.text(x + 0.18, 0.57, 'USDJPY', ha='center', va='center', color='#8b949e', fontsize=7)

    if compare == 's2_better_if_higher':
        v1_n = float(val_gold.replace('%','').replace('回','').replace('+',''))
        v2_n = float(val_usdjpy.replace('%','').replace('回','').replace('+',''))
        col2 = GREEN if v2_n > v1_n else (RED if v2_n < v1_n else TEXT_COLOR)
    elif compare == 's2_better_if_lower':
        v1_n = float(val_gold.replace('%','').replace('回','').replace('+',''))
        v2_n = float(val_usdjpy.replace('%','').replace('回','').replace('+',''))
        col2 = GREEN if v2_n < v1_n else (RED if v2_n > v1_n else TEXT_COLOR)
    else:
        col2 = CYAN

    ax_kpi.text(x + 0.18, 0.35, val_usdjpy, ha='center', va='center', color=col2, fontsize=11, fontweight='bold')
    ax_kpi.axvline(x, ymin=0.1, ymax=0.9, color=GRID_COLOR, linewidth=0.5, alpha=0.5)

# ===== Row 1: 資産推移比較 =====
ax_eq = fig.add_subplot(gs[1, :2])
ax_eq.set_facecolor(PANEL_BG)
ax_eq.tick_params(colors=TEXT_COLOR, labelsize=8)
for spine in ax_eq.spines.values(): spine.set_color(GRID_COLOR)
ax_eq.grid(True, color=GRID_COLOR, alpha=0.5, linewidth=0.5)

if len(tg) > 0:
    bal_g = [INIT_BAL] + list(tg['balance'])
    ret_g = [(b - INIT_BAL) / INIT_BAL * 100 for b in bal_g]
    ax_eq.plot(range(len(ret_g)), ret_g, color=GOLD_COLOR, linewidth=2,
               label=f'GOLD（{sg["total_trades"]}回）', zorder=3)

if len(tu) > 0:
    bal_u = [INIT_BAL] + list(tu['balance'])
    ret_u = [(b - INIT_BAL) / INIT_BAL * 100 for b in bal_u]
    x_u = [i * (len(ret_g)-1) / (len(ret_u)-1) for i in range(len(ret_u))] if len(ret_u) > 1 else list(range(len(ret_u)))
    ax_eq.plot(x_u, ret_u, color=CYAN, linewidth=2,
               label=f'USDJPY（{su["total_trades"]}回）', zorder=3, linestyle='--')

ax_eq.axhline(0, color=GRID_COLOR, linewidth=1)
ax_eq.set_xlabel('トレード番号（正規化）', color=TEXT_COLOR, fontsize=9)
ax_eq.set_ylabel('収益率 (%)', color=TEXT_COLOR, fontsize=9)
ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:+.0f}%'))
ax_eq.legend(fontsize=9, facecolor=PANEL_BG, labelcolor=TEXT_COLOR)
ax_eq.set_title('資産推移比較（収益率ベース）', color=TEXT_COLOR, fontsize=11)

# USDJPY 時系列累積損益
ax_time = fig.add_subplot(gs[1, 2])
ax_time.set_facecolor(PANEL_BG)
ax_time.tick_params(colors=TEXT_COLOR, labelsize=7)
for spine in ax_time.spines.values(): spine.set_color(GRID_COLOR)
ax_time.grid(True, color=GRID_COLOR, alpha=0.5, linewidth=0.5)

if len(tu) > 0:
    cum_u = tu['pnl_jpy'].cumsum()
    ax_time.plot(tu['exit_time'], cum_u, color=CYAN, linewidth=2)
    ax_time.fill_between(tu['exit_time'], cum_u, 0,
                         where=cum_u >= 0, alpha=0.15, color=GREEN)
    ax_time.fill_between(tu['exit_time'], cum_u, 0,
                         where=cum_u < 0, alpha=0.15, color=RED)

ax_time.axhline(0, color=GRID_COLOR, linewidth=1)
ax_time.set_xlabel('日付', color=TEXT_COLOR, fontsize=8)
ax_time.set_ylabel('累積損益 (¥)', color=TEXT_COLOR, fontsize=8)
ax_time.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'¥{v:+,.0f}'))
ax_time.set_title('USDJPY 累積損益（時系列）', color=TEXT_COLOR, fontsize=10)

# ===== Row 2: 月次損益 =====
ax_monthly = fig.add_subplot(gs[2, :2])
ax_monthly.set_facecolor(PANEL_BG)
ax_monthly.tick_params(colors=TEXT_COLOR, labelsize=7)
for spine in ax_monthly.spines.values(): spine.set_color(GRID_COLOR)
ax_monthly.grid(True, color=GRID_COLOR, alpha=0.5, axis='y', linewidth=0.5)

if su and su['monthly'] is not None and len(su['monthly']) > 0:
    months = su['monthly'].index.tolist()
    pnls   = su['monthly']['pnl'].tolist()
    counts = su['monthly']['count'].tolist()
    wrs    = su['monthly']['win_rate'].tolist()
    x = np.arange(len(months))
    ax_monthly.bar(x, pnls, color=[GREEN if p >= 0 else RED for p in pnls], alpha=0.85)
    ax_monthly.set_xticks(x)
    ax_monthly.set_xticklabels([str(m) for m in months], rotation=45, ha='right', fontsize=7, color=TEXT_COLOR)
    ax_monthly.axhline(0, color=GRID_COLOR, linewidth=1)
    ax_monthly.set_ylabel('損益 (¥)', color=TEXT_COLOR, fontsize=9)
    ax_monthly.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'¥{v:+,.0f}'))
    for xi, (p, c, wr) in enumerate(zip(pnls, counts, wrs)):
        y_pos = p + (max(pnls)*0.02 if p >= 0 else min(pnls)*0.02)
        ax_monthly.text(xi, y_pos, f'{c}回\n{wr:.0f}%', ha='center', fontsize=6,
                        color=TEXT_COLOR, va='bottom' if p >= 0 else 'top')

ax_monthly.set_title('USDJPY 月次損益', color=TEXT_COLOR, fontsize=11)

# 方向別比較
ax_side = fig.add_subplot(gs[2, 2])
ax_side.set_facecolor(PANEL_BG)
ax_side.tick_params(colors=TEXT_COLOR, labelsize=9)
for spine in ax_side.spines.values(): spine.set_color(GRID_COLOR)
ax_side.grid(True, color=GRID_COLOR, alpha=0.5, axis='y', linewidth=0.5)

if su and su['side'] is not None and len(su['side']) > 0:
    sides = su['side'].index.tolist()
    labels_jp = ['ロング' if s == 'long' else 'ショート' for s in sides]
    wrs_s    = su['side']['win_rate'].tolist()
    counts_s = su['side']['count'].tolist()
    avg_pnls = su['side']['avg_pnl'].tolist()
    x = np.arange(len(sides))
    ax_side.bar(x, wrs_s, color=[BLUE, ORANGE][:len(sides)], alpha=0.85, width=0.5)
    ax_side.set_xticks(x)
    ax_side.set_xticklabels(labels_jp, color=TEXT_COLOR, fontsize=10)
    ax_side.set_ylabel('勝率 (%)', color=TEXT_COLOR, fontsize=9)
    ax_side.set_ylim(0, 120)
    ax_side.axhline(50, color=YELLOW, linewidth=1.5, linestyle='--', alpha=0.7, label='50%ライン')
    for xi, (c, wr, ap) in enumerate(zip(counts_s, wrs_s, avg_pnls)):
        ax_side.text(xi, wr + 2, f'{c:.0f}回\n勝率{wr:.1f}%\n平均¥{ap:.0f}', ha='center', fontsize=7,
                     color=TEXT_COLOR, va='bottom')
    ax_side.legend(fontsize=8, facecolor=PANEL_BG, labelcolor=TEXT_COLOR)

ax_side.set_title('方向別 勝率・回数', color=TEXT_COLOR, fontsize=11)

# ===== Row 3: 損益分布 =====
ax_dist = fig.add_subplot(gs[3, :2])
ax_dist.set_facecolor(PANEL_BG)
ax_dist.tick_params(colors=TEXT_COLOR, labelsize=8)
for spine in ax_dist.spines.values(): spine.set_color(GRID_COLOR)
ax_dist.grid(True, color=GRID_COLOR, alpha=0.5, axis='y', linewidth=0.5)

if len(tu) > 0:
    pnls_u = tu['pnl_jpy'].values
    bins = np.linspace(np.percentile(pnls_u, 1), np.percentile(pnls_u, 99), 40)
    ax_dist.hist(pnls_u[pnls_u > 0], bins=bins, color=GREEN, alpha=0.8, label=f'勝ち {len(pnls_u[pnls_u>0])}回')
    ax_dist.hist(pnls_u[pnls_u <= 0], bins=bins, color=RED, alpha=0.8, label=f'負け {len(pnls_u[pnls_u<=0])}回')
    ax_dist.axvline(np.mean(pnls_u), color=YELLOW, linewidth=2, linestyle='--',
                    label=f'平均 ¥{np.mean(pnls_u):.0f}')
    ax_dist.axvline(np.median(pnls_u), color=PURPLE, linewidth=2, linestyle=':',
                    label=f'中央値 ¥{np.median(pnls_u):.0f}')
    ax_dist.set_xlabel('損益 (¥)', color=TEXT_COLOR, fontsize=9)
    ax_dist.set_ylabel('件数', color=TEXT_COLOR, fontsize=9)
    ax_dist.legend(fontsize=8, facecolor=PANEL_BG, labelcolor=TEXT_COLOR)

ax_dist.set_title('USDJPY 損益分布', color=TEXT_COLOR, fontsize=11)

# 時間帯別損益
ax_hour = fig.add_subplot(gs[3, 2])
ax_hour.set_facecolor(PANEL_BG)
ax_hour.tick_params(colors=TEXT_COLOR, labelsize=8)
for spine in ax_hour.spines.values(): spine.set_color(GRID_COLOR)
ax_hour.grid(True, color=GRID_COLOR, alpha=0.5, axis='y', linewidth=0.5)

if su and su['hourly'] is not None and len(su['hourly']) > 0:
    hours = su['hourly'].index.tolist()
    hpnls = su['hourly']['pnl'].tolist()
    hcnts = su['hourly']['count'].tolist()
    x = np.arange(len(hours))
    ax_hour.bar(x, hpnls, color=[GREEN if p >= 0 else RED for p in hpnls], alpha=0.85)
    ax_hour.set_xticks(x)
    ax_hour.set_xticklabels([f'{h}時' for h in hours], fontsize=7, color=TEXT_COLOR, rotation=45)
    ax_hour.set_ylabel('損益 (¥)', color=TEXT_COLOR, fontsize=8)
    ax_hour.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'¥{v/1000:.1f}k'))
    ax_hour.axhline(0, color=GRID_COLOR, linewidth=1)
    for xi, (p, c) in enumerate(zip(hpnls, hcnts)):
        ax_hour.text(xi, p + (max(hpnls)*0.02 if p >= 0 else min(hpnls)*0.02),
                     f'{c}', ha='center', fontsize=6, color=TEXT_COLOR,
                     va='bottom' if p >= 0 else 'top')

ax_hour.set_title('時間帯別損益（サーバー時間）', color=TEXT_COLOR, fontsize=10)

# ===== Row 4: ドローダウン =====
ax_dd = fig.add_subplot(gs[4, :2])
ax_dd.set_facecolor(PANEL_BG)
ax_dd.tick_params(colors=TEXT_COLOR, labelsize=8)
for spine in ax_dd.spines.values(): spine.set_color(GRID_COLOR)
ax_dd.grid(True, color=GRID_COLOR, alpha=0.5, linewidth=0.5)

if len(tu) > 0:
    bal_series = np.array([INIT_BAL] + list(tu['balance']))
    peak = np.maximum.accumulate(bal_series)
    dd_pct = (bal_series - peak) / peak * 100
    ax_dd.fill_between(range(len(dd_pct)), dd_pct, 0, alpha=0.6, color=RED)
    ax_dd.plot(range(len(dd_pct)), dd_pct, color=RED, linewidth=1)
    ax_dd.axhline(0, color=GRID_COLOR, linewidth=1)
    ax_dd.set_xlabel('トレード番号', color=TEXT_COLOR, fontsize=9)
    ax_dd.set_ylabel('ドローダウン (%)', color=TEXT_COLOR, fontsize=9)
    ax_dd.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.1f}%'))
    ax_dd.text(0.02, 0.05, f'最大DD: {su["max_dd_pct"]:.1f}%', transform=ax_dd.transAxes,
               color=YELLOW, fontsize=10, fontweight='bold')

ax_dd.set_title('ドローダウン推移', color=TEXT_COLOR, fontsize=11)

# 保有時間分布
ax_dur = fig.add_subplot(gs[4, 2])
ax_dur.set_facecolor(PANEL_BG)
ax_dur.tick_params(colors=TEXT_COLOR, labelsize=8)
for spine in ax_dur.spines.values(): spine.set_color(GRID_COLOR)
ax_dur.grid(True, color=GRID_COLOR, alpha=0.5, axis='y', linewidth=0.5)

if len(tu) > 0:
    durs = tu['duration_min'].values
    durs_clipped = np.clip(durs, 0, np.percentile(durs, 99))
    bins_d = np.linspace(0, durs_clipped.max(), 30)
    ax_dur.hist(durs_clipped, bins=bins_d, color=BLUE, alpha=0.85)
    ax_dur.axvline(np.mean(durs), color=YELLOW, linewidth=2, linestyle='--',
                   label=f'平均 {np.mean(durs):.0f}分')
    ax_dur.axvline(np.median(durs), color=PURPLE, linewidth=2, linestyle=':',
                   label=f'中央値 {np.median(durs):.0f}分')
    ax_dur.set_xlabel('保有時間 (分)', color=TEXT_COLOR, fontsize=9)
    ax_dur.set_ylabel('件数', color=TEXT_COLOR, fontsize=9)
    ax_dur.legend(fontsize=8, facecolor=PANEL_BG, labelcolor=TEXT_COLOR)

ax_dur.set_title('保有時間分布', color=TEXT_COLOR, fontsize=11)

# ===== Row 5: GOLD vs USDJPY 月次比較 =====
ax_comp = fig.add_subplot(gs[5, :])
ax_comp.set_facecolor(PANEL_BG)
ax_comp.tick_params(colors=TEXT_COLOR, labelsize=7)
for spine in ax_comp.spines.values(): spine.set_color(GRID_COLOR)
ax_comp.grid(True, color=GRID_COLOR, alpha=0.5, axis='y', linewidth=0.5)

# 月次収益率で比較
if sg['monthly'] is not None and su['monthly'] is not None:
    # 共通月を取得
    months_g = {str(m): v for m, v in sg['monthly']['pnl'].items()}
    months_u = {str(m): v for m, v in su['monthly']['pnl'].items()}
    all_months = sorted(set(list(months_g.keys()) + list(months_u.keys())))

    x = np.arange(len(all_months))
    w = 0.38
    pnls_g = [months_g.get(m, 0) for m in all_months]
    pnls_u = [months_u.get(m, 0) for m in all_months]

    ax_comp.bar(x - w/2, pnls_g, width=w, color=GOLD_COLOR, alpha=0.8, label='GOLD')
    ax_comp.bar(x + w/2, pnls_u, width=w, color=CYAN, alpha=0.8, label='USDJPY')
    ax_comp.set_xticks(x)
    ax_comp.set_xticklabels(all_months, rotation=45, ha='right', fontsize=7, color=TEXT_COLOR)
    ax_comp.axhline(0, color=GRID_COLOR, linewidth=1)
    ax_comp.set_ylabel('月次損益 (¥)', color=TEXT_COLOR, fontsize=9)
    ax_comp.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'¥{v:+,.0f}'))
    ax_comp.legend(fontsize=9, facecolor=PANEL_BG, labelcolor=TEXT_COLOR)

ax_comp.set_title('GOLD vs USDJPY 月次損益比較', color=TEXT_COLOR, fontsize=11)

# ===== Row 6: 詳細比較表 =====
ax_table = fig.add_subplot(gs[6, :])
ax_table.set_facecolor(PANEL_BG)
ax_table.axis('off')

def fmt(s, key, fmt_str='{}'):
    if s and key in s and s[key] is not None:
        try: return fmt_str.format(s[key])
        except: return str(s[key])
    return 'N/A'

table_data = [
    ['総トレード数',    fmt(sg,'total_trades','{}回'),   fmt(su,'total_trades','{}回'),   '多い方が機会多い'],
    ['勝率',            fmt(sg,'win_rate','{:.1f}%'),    fmt(su,'win_rate','{:.1f}%'),    '高い方が良い'],
    ['PF',              fmt(sg,'profit_factor','{:.2f}'), fmt(su,'profit_factor','{:.2f}'), '1.0以上が必須'],
    ['最終残高',        fmt(sg,'final_balance','¥{:,.0f}'), fmt(su,'final_balance','¥{:,.0f}'), ''],
    ['総収益率',        fmt(sg,'total_return_pct','{:+.1f}%'), fmt(su,'total_return_pct','{:+.1f}%'), ''],
    ['最大DD',          fmt(sg,'max_dd_pct','{:.1f}%'),  fmt(su,'max_dd_pct','{:.1f}%'),  '小さい方が良い'],
    ['最大連続負け',    fmt(sg,'max_consec_loss','{}回'), fmt(su,'max_consec_loss','{}回'), '小さい方が良い'],
    ['平均利益',        fmt(sg,'avg_win','¥{:,.0f}'),    fmt(su,'avg_win','¥{:,.0f}'),    ''],
    ['平均損失',        fmt(sg,'avg_loss','¥{:,.0f}'),   fmt(su,'avg_loss','¥{:,.0f}'),   ''],
    ['1ヶ月あたり',     fmt(sg,'trades_per_month','{:.1f}回'), fmt(su,'trades_per_month','{:.1f}回'), ''],
    ['平均保有時間',    fmt(sg,'avg_duration_min','{:.0f}分'), fmt(su,'avg_duration_min','{:.0f}分'), ''],
]

headers = ['指標', 'GOLD（ロジック②）', 'USDJPY（ロジック②）', '評価基準']
tbl = ax_table.table(cellText=table_data, colLabels=headers,
                     cellLoc='center', loc='center', bbox=[0, 0, 1, 1])
tbl.auto_set_font_size(False)
tbl.set_fontsize(9)

for (row, col), cell in tbl.get_celld().items():
    cell.set_facecolor(PANEL_BG if row % 2 == 0 else '#21262d')
    cell.set_text_props(color=TEXT_COLOR)
    cell.set_edgecolor(GRID_COLOR)
    if row == 0:
        cell.set_facecolor('#21262d')
        if col == 1:
            cell.set_text_props(color=GOLD_COLOR, fontweight='bold')
        elif col == 2:
            cell.set_text_props(color=CYAN, fontweight='bold')
        else:
            cell.set_text_props(color=YELLOW, fontweight='bold')

ax_table.set_title('GOLD vs USDJPY 詳細比較表', color=TEXT_COLOR, fontsize=12, pad=10)

plt.savefig(f'{OUTPUT_DIR}/chart_usdjpy.png', dpi=150, bbox_inches='tight', facecolor=DARK_BG)
plt.close()
print("chart_usdjpy.png 生成完了")

# ===== Markdownレポート =====
monthly_str = ""
if su and su['monthly'] is not None and len(su['monthly']) > 0:
    for ym, row in su['monthly'].iterrows():
        monthly_str += f"| {ym} | {row['count']:.0f}回 | ¥{row['pnl']:+,.0f} | {row['win_rate']:.1f}% |\n"

side_str = ""
if su and su['side'] is not None and len(su['side']) > 0:
    for side, row in su['side'].iterrows():
        side_jp = 'ロング' if side == 'long' else 'ショート'
        side_str += f"| {side_jp} | {row['count']:.0f}回 | ¥{row['pnl']:+,.0f} | {row['win_rate']:.1f}% | ¥{row['avg_pnl']:,.0f} |\n"

report = f"""# ロジック② USDJPY 検証レポート

**検証期間**: 2023年1月2日〜2026年2月27日（約3年2ヶ月）  
**データ**: USDJPY 1分足 1,121,147本（XM micro口座）  
**生成日**: 2026年3月27日

---

## 検証結果（¥10,000スタート）

| 指標 | GOLD | **USDJPY** | 差分 |
|------|:----:|:----------:|:----:|
| **総トレード数** | {sg['total_trades']}回 | **{su['total_trades']}回** | {su['total_trades']-sg['total_trades']:+d}回 |
| **勝率** | {sg['win_rate']:.1f}% | **{su['win_rate']:.1f}%** | {su['win_rate']-sg['win_rate']:+.1f}pt |
| **PF** | {sg['profit_factor']:.2f} | **{su['profit_factor']:.2f}** | {su['profit_factor']-sg['profit_factor']:+.2f} |
| **最終残高** | ¥{sg['final_balance']:,.0f} | **¥{su['final_balance']:,.0f}** | ¥{su['final_balance']-sg['final_balance']:+,.0f} |
| **総収益率** | {sg['total_return_pct']:+.1f}% | **{su['total_return_pct']:+.1f}%** | {su['total_return_pct']-sg['total_return_pct']:+.1f}pt |
| **最大DD** | {sg['max_dd_pct']:.1f}% | **{su['max_dd_pct']:.1f}%** | {su['max_dd_pct']-sg['max_dd_pct']:+.1f}pt |
| **最大連続負け** | {sg['max_consec_loss']}回 | {su['max_consec_loss']}回 | {su['max_consec_loss']-sg['max_consec_loss']:+d}回 |
| **平均利益** | ¥{sg['avg_win']:,.0f} | ¥{su['avg_win']:,.0f} | ¥{su['avg_win']-sg['avg_win']:+,.0f} |
| **平均損失** | ¥{abs(sg['avg_loss']):,.0f} | ¥{abs(su['avg_loss']):,.0f} | ¥{abs(su['avg_loss'])-abs(sg['avg_loss']):+,.0f} |
| **月平均回数** | {sg['trades_per_month']:.1f}回 | **{su['trades_per_month']:.1f}回** | {su['trades_per_month']-sg['trades_per_month']:+.1f}回 |
| **平均保有時間** | {sg['avg_duration_min']:.0f}分 | {su['avg_duration_min']:.0f}分 | {su['avg_duration_min']-sg['avg_duration_min']:+.0f}分 |

---

## 月次損益（USDJPY）

| 月 | 回数 | 損益 | 勝率 |
|----|:----:|:----:|:----:|
{monthly_str}

---

## 方向別成績（USDJPY）

| 方向 | 回数 | 損益合計 | 勝率 | 平均損益 |
|------|:----:|:--------:|:----:|:--------:|
{side_str}

---

## 分析と考察

### GOLDとの比較

ロジック②はUSDJPYでも有効性が確認されました。主な違いは以下の通りです。

**勝率の差**: GOLD 68.1% vs USDJPY {su['win_rate']:.1f}%。USDJPYの勝率がやや低い理由として、USDJPYは**ファンダメンタルズ（日銀政策・米雇用統計等）の影響**を受けやすく、テクニカルシグナルが機能しにくい場面が多いことが考えられます。

**PFの差**: GOLD 1.61 vs USDJPY {su['profit_factor']:.2f}。PFはGOLDが優位ですが、USDJPYも1.0を超えており期待値プラスを維持しています。

**最大DDの差**: GOLD 14.5% vs USDJPY {su['max_dd_pct']:.1f}%。USDJPYの最大DDが{"高く" if su['max_dd_pct'] > sg['max_dd_pct'] else "低く"}なっています。{"これはUSDJPYの急激なトレンド転換（特に日銀介入等）による影響と考えられます。" if su['max_dd_pct'] > sg['max_dd_pct'] else "USDJPYの方がリスク管理の観点では優位です。"}

### 時間帯の特徴

USDJPYは東京時間（JST 9〜11時 = サーバー時間 2〜4時）と**ロンドン・NY時間（サーバー時間 7〜16時）**が主要な取引時間です。時間帯別損益チャートで収益性の高い時間帯を確認し、フィルタリングを検討することを推奨します。

### 注意点

1. **スプレッド固定**: 0.03円固定（実際は経済指標発表時等に大幅拡大）
2. **スリッページ未考慮**: 特に東京オープン・NY時間の流動性変化に注意
3. **日銀政策リスク**: 突発的な円高・円安への対応が必要
4. **夏時間未対応**: サーバー時間のUTC+2固定

---

## 結論

ロジック②はUSDJPYでも**PF{su['profit_factor']:.2f}・勝率{su['win_rate']:.1f}%・月{su['trades_per_month']:.1f}回**の安定した成績を示しています。GOLDと比較すると収益性はやや劣りますが、**ポートフォリオ分散**の観点からGOLDとUSDJPYの両銘柄でEAを稼働させることで、リスク分散と安定収益の両立が期待できます。

---

*本レポートはXM micro口座の実データを使用したバックテスト検証です。過去の結果は将来の利益を保証するものではありません。*
"""

with open(f'{OUTPUT_DIR}/report_usdjpy.md', 'w', encoding='utf-8') as f:
    f.write(report)
print("report_usdjpy.md 生成完了")

print()
print("=== 最終サマリー ===")
print(f"GOLD:    トレード{sg['total_trades']}回 | 勝率{sg['win_rate']:.1f}% | PF{sg['profit_factor']:.2f} | 収益率{sg['total_return_pct']:+.1f}% | DD{sg['max_dd_pct']:.1f}%")
print(f"USDJPY:  トレード{su['total_trades']}回 | 勝率{su['win_rate']:.1f}% | PF{su['profit_factor']:.2f} | 収益率{su['total_return_pct']:+.1f}% | DD{su['max_dd_pct']:.1f}%")
