# SMC Master EA 設計書

## 1. システムアーキテクチャ

本EAは、以下の主要モジュールで構成される。

- **C_SMC_Engine**: 各SMC要素（OB, FVG, BOS/CHoCH, Liquidity Sweep等）を検出・判定するクラス。
- **C_RiskManager**: ロットサイズ計算、日次利益制限、最大ロット制限を管理するクラス。
- **C_TimeManager**: サーバー時間（UTC+2/UTC+3）とJST/EST（NY時間）を変換し、Silver BulletやJudas Swingなどの時間ベースのフィルターを管理するクラス。
- **C_TradeManager**: エントリー、エグジット、SL/TPの管理、複数銘柄のポジション管理を行うクラス。

## 2. 主要ロジックの詳細設計

### 2.1 SMC要素の検出ロジック

#### 2.1.1 Order Block (OB)
- **定義**: BOSを伴う強い値動き（インパルスムーブ）の直前にある、最後の反対方向のローソク足。
- **実装**:
  - スイングハイ/スイングローを特定する（`FindSwingHigh`/`FindSwingLow`）。
  - BOSが発生したかを確認。
  - BOSの起点となるスイングの直前の陰線（強気OB）または陽線（弱気OB）を特定。

#### 2.1.2 Fair Value Gap (FVG)
- **定義**: 3本のローソク足において、1本目の高値（安値）と3本目の安値（高値）の間に生じるギャップ。
- **実装**:
  - `High[i-2] < Low[i]` ならば強気FVG。
  - `Low[i-2] > High[i]` ならば弱気FVG。

#### 2.1.3 BOS / CHoCH
- **定義**:
  - **BOS (Break of Structure)**: トレンド方向への直近高値（安値）の更新。
  - **CHoCH (Change of Character)**: トレンド反転を示す直近安値（高値）のブレイク。
- **実装**:
  - スイングポイントを配列に保存し、現在価格が直近のスイングポイントを実体（終値）でブレイクしたかを判定。

#### 2.1.4 Liquidity Sweep
- **定義**: 直近高安値をヒゲで抜け、その後実体は高安値の内側で確定する動き。
- **実装**:
  - 高値（安値）を更新したが、終値は高値（安値）を下回る（上回る）ピンバー的な形状を検出。

#### 2.1.5 Premium / Discount Zone
- **定義**: スイングハイとスイングローのフィボナッチリトレースメントの50%ラインを基準とする。
- **実装**:
  - `50%以上` = Premium（売り目線）。
  - `50%以下` = Discount（買い目線）。

### 2.2 エントリー条件の統合（コンフルエンス）

買い（Long）の基本セットアップ例：
1. 上位足（H1/H4）が上昇トレンド（BOS）。
2. 価格が上位足のDiscount Zoneに到達。
3. 下位足（M5/M15）でLiquidity Sweepが発生。
4. 下位足で上方向へのCHoCHが発生。
5. CHoCHの起点に強気OBまたはFVGが存在。
6. 価格がOB/FVGにリトレースした時点でエントリー。

### 2.3 リスク管理とロット計算

#### 2.3.1 ロット計算
ユーザー要件に基づくロットサイズ計算ロジック。
```mql5
double CalculateLotSize(double balance) {
    double baseLot = 0.1;
    double maxLot = 1.0;
    double calculatedLot = MathFloor(balance / 1000.0) * baseLot;
    if (calculatedLot > maxLot) {
        calculatedLot = maxLot;
    }
    return calculatedLot;
}
```

#### 2.3.2 日次利益制限
1日の開始時の残高（`AccountInfoDouble(ACCOUNT_BALANCE)`）を保持し、現在の有効証拠金（`AccountInfoDouble(ACCOUNT_EQUITY)`）が開始残高の120%〜125%に達したか判定。
```mql5
bool CheckDailyProfitLimit(double startBalance, double targetPercentage) {
    double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    double targetEquity = startBalance * (1.0 + targetPercentage / 100.0);
    return currentEquity >= targetEquity;
}
```

#### 2.3.3 SL / TP
- **SL**: 直近高安値（スイングハイ/スイングロー）から ±5ポイント（= 50 pips/500 ticks相当。通貨ペアにより調整が必要）。
- **TP**: リスクリワード比率 1:2以上、または反対側の流動性（次のスイングポイントや未充填のFVG）。

## 3. マルチタイムフレーム・マルチカレンシー対応
- `iHigh`, `iLow`, `iClose` などの関数に明示的にシンボルと時間足を指定してデータを取得。
- SMT Divergenceの検出には、相関ペア（例: EURUSDとGBPUSD）の直近スイングポイントを同時に取得し、一方が高値を更新し、もう一方が更新していない状態を判定する。
