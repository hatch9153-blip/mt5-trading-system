# SMC Master EA 要件定義書

## 1. 概要
本EA（Expert Advisor）は、SMC（Smart Money Concepts）の各要素を統合的に監視し、優位性の高い局面で自動的にエントリーおよびエグジットを行うMT5用自動売買システムです。

## 2. 対象環境
- **プラットフォーム**: MetaTrader 5 (MT5)
- **ブローカー**: XMTrading
- **口座タイプ**: Micro口座（円建て）
  - 1ロット = 1,000通貨
- **対象通貨ペア・銘柄**:
  - GOLD (XAUUSD)
  - USDJPY, GBPJPY, EURJPY, GBPUSD, EURUSD, AUDJPY, AUDUSD, GBPAUD, EURAUD
- **対象時間足**: 1分足 (M1) ～ 4時間足 (H4)

## 3. ロジック・SMC要素
以下のSMC要素を監視し、複数の条件が合致した場合（コンフルエンス）にエントリーを実行します。

1. **Order Block (OB)**
   - 機関投資家の注文が集中している価格帯（大陽線/大陰線の起点）の検出。
2. **Fair Value Gap (FVG)**
   - 3本のローソク足間で生じる価格のギャップ（インバランス）の検出。
3. **Break of Structure (BOS) / Change of Character (CHoCH)**
   - トレンド継続（BOS）およびトレンド転換（CHoCH）のシグナル検出。
4. **Liquidity Sweep**
   - 直近高値・安値（流動性プール）を一時的に抜けた後の反転（ストップハント）の検出。
5. **Premium / Discount Zone**
   - スイングハイ・スイングローのフィボナッチリトレースメントに基づく、割高（Premium）および割安（Discount）ゾーンの判定。
6. **Time-based Concepts**
   - **Judas Swing**: ロンドン/NYオープン直後の騙しの動き（逆行）。
   - **Silver Bullet**: 特定の時間帯（例: NY 10:00-11:00 EST）における高勝率セットアップ。
   - **Weekly PO3 (Power of 3)**: 週間の値動きサイクル（Accumulation, Manipulation, Distribution）。
7. **SMT Divergence**
   - 相関性のある銘柄間（例: EURUSDとGBPUSD、またはUSDJPYとGOLDなど）での高値・安値のダイバージェンス（不一致）検出。

## 4. エントリー・エグジットルール
- **エントリー**: 上記SMC要素が複数重なるポイント（例：Discount Zone内のOB/FVGへの価格到達 + 下位足でのCHoCH発生など）で成行または指値エントリー。
- **Stop Loss (SL)**: 直近高安値から ±5ポイント（= 50 pips/500 ticks相当、要調整）に設定。
- **Take Profit (TP)**: 次の流動性ターゲット（直近高安値、未充填のFVG、反対側のOBなど）または固定リスクリワード比率（例: 1:2以上）。

## 5. 資金管理・リスク管理ルール
1. **ロットサイズ計算**
   - 基本ロット: 口座残高 1,000円 に対して 0.1ロット。
   - 最大ロット: 口座残高 10,000円 に対して 1.0ロット（上限）。
   - 計算式: `Lots = Floor(Balance / 1000) * 0.1` （最大1.0に制限）
2. **日次利益制限（Daily Profit Target）**
   - その日の開始時の口座残高に対して、**20% ～ 25%** の利益が出た時点で、その日の新規トレードを停止する。
   - すでに保有しているポジションはルールに従い決済（または全決済）。
3. **時間管理**
   - XMTradingのサーバー時間（夏時間 UTC+3 / 冬時間 UTC+2）を考慮し、日本時間（JST）やニューヨーク時間（EST）に合わせた時間枠フィルター（Silver Bullet等）を正確に機能させる。

## 6. その他要件
- **マルチタイムフレーム (MTF) 分析**: 上位足（H4/H1）で環境認識（Premium/Discount、OB/FVG）を行い、下位足（M15/M5/M1）でエントリートリガー（CHoCH、Liquidity Sweep）を探す。
- **SMT Divergenceの監視**: 複数銘柄のデータを同時に取得・比較する機能（`iHigh`, `iLow` などを他通貨ペアで呼び出す）。
