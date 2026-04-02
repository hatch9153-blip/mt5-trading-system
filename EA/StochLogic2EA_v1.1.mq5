//+------------------------------------------------------------------+
//|                                          StochLogic2EA.mq5       |
//|  Exness XAUUSDm / USDJPY 向け ロジック② EA                       |
//|  4H/1H/5M Stochastics(9,3,3) マルチタイムフレーム戦略             |
//|  Version 1.1 - ビジュアル表示機能追加                             |
//+------------------------------------------------------------------+
#property copyright "hatch9153-blip"
#property link      "https://github.com/hatch9153-blip/mt5-trading-system"
#property version   "1.10"
#property description "ロジック②: 4H/1H/5M Stochastics(9,3,3) マルチタイムフレーム戦略"
#property description "Exness XAUUSDm / USDJPY 対応"
#property description "v1.1: チャート上にエントリー/エグジット・ライン・収支を表示"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\OrderInfo.mqh>

//==========================================================================
// 入力パラメータ
//==========================================================================

//--- Stochastics 設定
input group "=== Stochastics 設定 ==="
input int    InpStochK      = 9;      // %K 期間
input int    InpStochD      = 3;      // %D 期間
input int    InpStochSlowing= 3;      // スローイング
input double InpOversold    = 20.0;   // 売られすぎライン（ロング用）
input double InpOverbought  = 80.0;   // 買われすぎライン（ショート用）

//--- ロット管理設定
input group "=== ロット管理設定 ==="
input double InpBaseLot     = 0.01;   // 基本ロット（テスト用）
input bool   InpAutoLot     = true;   // 段階的ロットアップを使用する
input double InpLotStage1   = 0.01;   // フェーズ1ロット（〜¥10万）
input double InpLotStage2   = 0.05;   // フェーズ2ロット（¥10万〜¥50万）
input double InpLotStage3   = 0.20;   // フェーズ3ロット（¥50万〜¥100万）
input double InpLotStage4   = 0.66;   // フェーズ4ロット（¥100万〜）
input double InpStageThresh1= 100000; // フェーズ2開始残高（円）
input double InpStageThresh2= 500000; // フェーズ3開始残高（円）
input double InpStageThresh3= 1000000;// フェーズ4開始残高（円）

//--- リスク管理設定
input group "=== リスク管理設定 ==="
input double InpMaxLot      = 1.00;   // 最大ロット上限
input double InpRuinPct     = 30.0;   // 破産ライン（初期残高の%）
input bool   InpUseSL       = false;  // 固定SLを使用する
input double InpSLPoints    = 500;    // 固定SL（ポイント）
input bool   InpUseTP       = false;  // 固定TPを使用する
input double InpTPPoints    = 1000;   // 固定TP（ポイント）

//--- サーバー時刻設定
input group "=== サーバー時刻設定 ==="
input int    InpServerOffset= 3;      // サーバーUTCオフセット（夏時間=3, 冬時間=2）

//--- EA設定
input group "=== EA設定 ==="
input int    InpMagicNumber = 202601; // マジックナンバー
input int    InpMaxPositions= 1;      // 最大同時ポジション数
input int    InpSlippage    = 30;     // スリッページ（ポイント）
input bool   InpEnableLog   = true;   // ログ出力を有効にする

//--- ビジュアル表示設定
input group "=== ビジュアル表示設定 ==="
input bool   InpShowVisuals = true;   // チャート上にエントリー/エグジットを表示する
input color  InpColorBuy    = clrDodgerBlue;  // ロングエントリー矢印色
input color  InpColorSell   = clrOrangeRed;   // ショートエントリー矢印色
input color  InpColorLine   = clrGray;        // 接続ライン色
input int    InpArrowSize   = 2;              // 矢印サイズ（1〜5）
input double InpUSDJPY      = 150.0;          // 損益計算用 USD/JPY レート

//==========================================================================
// グローバル変数
//==========================================================================
CTrade        trade;
CPositionInfo posInfo;

string   g_symbol       = "";
double   g_initialBalance = 0.0;
datetime g_lastBarTime5M  = 0;
datetime g_lastBarTime1H  = 0;
datetime g_lastBarTime4H  = 0;

// Stochastics ハンドル
int g_stoch5M  = INVALID_HANDLE;
int g_stoch1H  = INVALID_HANDLE;
int g_stoch4H  = INVALID_HANDLE;

// 4H足の状態管理
bool g_4h_long_mode  = false;  // 4H足ロングモード中
bool g_4h_short_mode = false;  // 4H足ショートモード中

// ビジュアル表示用
struct TradeRecord
{
   ulong    ticket;
   datetime entryTime;
   double   entryPrice;
   double   lot;
   int      type;  // 0=BUY, 1=SELL
};
TradeRecord g_openTrades[100];  // 最大100ポジション記録
int g_tradeCount = 0;

//==========================================================================
// 初期化
//==========================================================================
int OnInit()
{
   g_symbol = Symbol();
   g_initialBalance = AccountInfoDouble(ACCOUNT_BALANCE);

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   // Stochastics インジケーターハンドル作成
   g_stoch5M = iStochastic(g_symbol, PERIOD_M5,  InpStochK, InpStochD, InpStochSlowing, MODE_SMA, STO_LOWHIGH);
   g_stoch1H = iStochastic(g_symbol, PERIOD_H1,  InpStochK, InpStochD, InpStochSlowing, MODE_SMA, STO_LOWHIGH);
   g_stoch4H = iStochastic(g_symbol, PERIOD_H4,  InpStochK, InpStochD, InpStochSlowing, MODE_SMA, STO_LOWHIGH);

   if(g_stoch5M == INVALID_HANDLE || g_stoch1H == INVALID_HANDLE || g_stoch4H == INVALID_HANDLE)
   {
      Print("ERROR: Stochastics ハンドル作成失敗");
      return(INIT_FAILED);
   }

   // 破産ライン確認
   double ruinLine = g_initialBalance * (InpRuinPct / 100.0);
   Print("=== StochLogic2EA v1.1 起動 ===");
   Print("シンボル: ", g_symbol);
   Print("初期残高: ", g_initialBalance);
   Print("破産ライン: ", ruinLine, " (", InpRuinPct, "%)");
   Print("段階的ロットアップ: ", InpAutoLot ? "有効" : "無効");
   Print("ビジュアル表示: ", InpShowVisuals ? "有効" : "無効");

   // 既存のビジュアルオブジェクトをクリア
   if(InpShowVisuals)
      DeleteAllVisuals();

   EventSetTimer(1);
   return(INIT_SUCCEEDED);
}

//==========================================================================
// 終了処理
//==========================================================================
void OnDeinit(const int reason)
{
   EventKillTimer();
   if(g_stoch5M != INVALID_HANDLE) IndicatorRelease(g_stoch5M);
   if(g_stoch1H != INVALID_HANDLE) IndicatorRelease(g_stoch1H);
   if(g_stoch4H != INVALID_HANDLE) IndicatorRelease(g_stoch4H);
   
   // ビジュアルオブジェクトは残す（削除しない）
   // if(InpShowVisuals) DeleteAllVisuals();
   
   Print("StochLogic2EA v1.1 終了");
}

//==========================================================================
// メインティック処理
//==========================================================================
void OnTick()
{
   // 破産ライン確認（最優先）
   if(IsRuined()) return;

   // 新しい5M足確認
   datetime currentBar5M = iTime(g_symbol, PERIOD_M5, 0);
   if(currentBar5M == g_lastBarTime5M) return;
   g_lastBarTime5M = currentBar5M;

   // Stochastics 値取得
   double k4h_cur, k4h_prev, d4h_cur, d4h_prev;
   double k1h_cur, k1h_prev, d1h_cur, d1h_prev;
   double k5m_cur, k5m_prev, d5m_cur, d5m_prev;

   if(!GetStochValues(g_stoch4H, k4h_cur, k4h_prev, d4h_cur, d4h_prev)) return;
   if(!GetStochValues(g_stoch1H, k1h_cur, k1h_prev, d1h_cur, d1h_prev)) return;
   if(!GetStochValues(g_stoch5M, k5m_cur, k5m_prev, d5m_cur, d5m_prev)) return;

   // 4H足モード更新
   Update4HMode(k4h_cur, k4h_prev, d4h_cur, d4h_prev);

   // イグジット確認（既存ポジション）
   CheckExit(k5m_cur, k5m_prev, d5m_cur, d5m_prev);

   // 最大ポジション数確認
   if(CountPositions() >= InpMaxPositions) return;

   // ロット計算
   double lot = GetCurrentLot();

   // エントリー判定
   bool can_long  = g_4h_long_mode  && (k1h_cur > d1h_cur);
   bool can_short = g_4h_short_mode && (k1h_cur < d1h_cur);

   // ロングエントリー: 5M足が0〜20圏内でゴールデンクロス
   if(can_long)
   {
      bool gc5m = (k5m_prev <= d5m_prev) && (k5m_cur > d5m_cur) && (k5m_cur <= InpOversold);
      if(gc5m)
      {
         if(InpEnableLog) Print("ロングエントリーシグナル | K=", k5m_cur, " D=", d5m_cur);
         OpenLong(lot);
      }
   }

   // ショートエントリー: 5M足が80〜100圏内でデッドクロス
   if(can_short)
   {
      bool dc5m = (k5m_prev >= d5m_prev) && (k5m_cur < d5m_cur) && (k5m_cur >= InpOverbought);
      if(dc5m)
      {
         if(InpEnableLog) Print("ショートエントリーシグナル | K=", k5m_cur, " D=", d5m_cur);
         OpenShort(lot);
      }
   }
}

//==========================================================================
// 4H足モード更新
//==========================================================================
void Update4HMode(double k4h_cur, double k4h_prev, double d4h_cur, double d4h_prev)
{
   // ロングモード開始条件: 4H足が0〜20圏内でゴールデンクロス
   bool gc4h = (k4h_prev <= d4h_prev) && (k4h_cur > d4h_cur) && (k4h_cur <= InpOversold);
   if(gc4h && !g_4h_long_mode)
   {
      g_4h_long_mode  = true;
      g_4h_short_mode = false;
      if(InpEnableLog) Print("4H足 ロングモード開始 | K=", k4h_cur, " D=", d4h_cur);
   }

   // ロングモード終了条件: 4H足が80〜100圏内でデッドクロス
   bool dc4h_exit = (k4h_prev >= d4h_prev) && (k4h_cur < d4h_cur) && (k4h_cur >= InpOverbought);
   if(dc4h_exit && g_4h_long_mode)
   {
      g_4h_long_mode = false;
      if(InpEnableLog) Print("4H足 ロングモード終了 | K=", k4h_cur, " D=", d4h_cur);
   }

   // ショートモード開始条件: 4H足が80〜100圏内でデッドクロス
   bool dc4h = (k4h_prev >= d4h_prev) && (k4h_cur < d4h_cur) && (k4h_cur >= InpOverbought);
   if(dc4h && !g_4h_short_mode)
   {
      g_4h_short_mode = true;
      g_4h_long_mode  = false;
      if(InpEnableLog) Print("4H足 ショートモード開始 | K=", k4h_cur, " D=", d4h_cur);
   }

   // ショートモード終了条件: 4H足が0〜20圏内でゴールデンクロス
   bool gc4h_exit = (k4h_prev <= d4h_prev) && (k4h_cur > d4h_cur) && (k4h_cur <= InpOversold);
   if(gc4h_exit && g_4h_short_mode)
   {
      g_4h_short_mode = false;
      if(InpEnableLog) Print("4H足 ショートモード終了 | K=", k4h_cur, " D=", d4h_cur);
   }
}

//==========================================================================
// イグジット確認
//==========================================================================
void CheckExit(double k5m_cur, double k5m_prev, double d5m_cur, double d5m_prev)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!posInfo.SelectByIndex(i)) continue;
      if(posInfo.Symbol() != g_symbol) continue;
      if(posInfo.Magic() != InpMagicNumber) continue;

      ulong ticket = posInfo.Ticket();
      ENUM_POSITION_TYPE posType = posInfo.PositionType();

      // ロングポジションのイグジット: 5M足が80〜100圏内でデッドクロス
      if(posType == POSITION_TYPE_BUY)
      {
         bool dc5m_exit = (k5m_prev >= d5m_prev) && (k5m_cur < d5m_cur) && (k5m_cur >= InpOverbought);
         if(dc5m_exit)
         {
            if(InpEnableLog) Print("ロングイグジット | Ticket=", ticket, " K=", k5m_cur);
            
            // イグジット前にビジュアル描画
            if(InpShowVisuals)
            {
               double exitPrice = SymbolInfoDouble(g_symbol, SYMBOL_BID);
               DrawExitAndLine(ticket, TimeCurrent(), exitPrice);
            }
            
            trade.PositionClose(ticket);
         }
      }

      // ショートポジションのイグジット: 5M足が0〜20圏内でゴールデンクロス
      if(posType == POSITION_TYPE_SELL)
      {
         bool gc5m_exit = (k5m_prev <= d5m_prev) && (k5m_cur > d5m_cur) && (k5m_cur <= InpOversold);
         if(gc5m_exit)
         {
            if(InpEnableLog) Print("ショートイグジット | Ticket=", ticket, " K=", k5m_cur);
            
            // イグジット前にビジュアル描画
            if(InpShowVisuals)
            {
               double exitPrice = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
               DrawExitAndLine(ticket, TimeCurrent(), exitPrice);
            }
            
            trade.PositionClose(ticket);
         }
      }
   }
}

//==========================================================================
// ロングエントリー
//==========================================================================
void OpenLong(double lot)
{
   double ask = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
   double sl  = InpUseSL ? NormalizeDouble(ask - InpSLPoints * _Point, _Digits) : 0.0;
   double tp  = InpUseTP ? NormalizeDouble(ask + InpTPPoints * _Point, _Digits) : 0.0;

   if(!trade.Buy(lot, g_symbol, ask, sl, tp, "StochL2_Long"))
      Print("ERROR: ロングエントリー失敗 | ", trade.ResultRetcodeDescription());
   else
   {
      Print("ロングエントリー成功 | Lot=", lot, " Ask=", ask, " SL=", sl, " TP=", tp);
      
      // ビジュアル表示
      if(InpShowVisuals && trade.ResultRetcode() == TRADE_RETCODE_DONE)
      {
         ulong ticket = trade.ResultOrder();
         RecordTrade(ticket, TimeCurrent(), ask, lot, 0);
         DrawEntryArrow(TimeCurrent(), ask, 0, ticket, lot);
      }
   }
}

//==========================================================================
// ショートエントリー
//==========================================================================
void OpenShort(double lot)
{
   double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
   double sl  = InpUseSL ? NormalizeDouble(bid + InpSLPoints * _Point, _Digits) : 0.0;
   double tp  = InpUseTP ? NormalizeDouble(bid - InpTPPoints * _Point, _Digits) : 0.0;

   if(!trade.Sell(lot, g_symbol, bid, sl, tp, "StochL2_Short"))
      Print("ERROR: ショートエントリー失敗 | ", trade.ResultRetcodeDescription());
   else
   {
      Print("ショートエントリー成功 | Lot=", lot, " Bid=", bid, " SL=", sl, " TP=", tp);
      
      // ビジュアル表示
      if(InpShowVisuals && trade.ResultRetcode() == TRADE_RETCODE_DONE)
      {
         ulong ticket = trade.ResultOrder();
         RecordTrade(ticket, TimeCurrent(), bid, lot, 1);
         DrawEntryArrow(TimeCurrent(), bid, 1, ticket, lot);
      }
   }
}

//==========================================================================
// 段階的ロット計算
//==========================================================================
double GetCurrentLot()
{
   if(!InpAutoLot) return NormalizeDouble(InpBaseLot, 2);

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double lot;

   if(balance >= InpStageThresh3)
      lot = InpLotStage4;
   else if(balance >= InpStageThresh2)
      lot = InpLotStage3;
   else if(balance >= InpStageThresh1)
      lot = InpLotStage2;
   else
      lot = InpLotStage1;

   // 最大ロット上限
   lot = MathMin(lot, InpMaxLot);

   // ブローカーのロット制限確認
   double minLot  = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_STEP);

   lot = MathMax(lot, minLot);
   lot = MathMin(lot, maxLot);
   lot = NormalizeDouble(MathRound(lot / stepLot) * stepLot, 2);

   return lot;
}

//==========================================================================
// 破産ライン確認
//==========================================================================
bool IsRuined()
{
   double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
   double ruinLine = g_initialBalance * (InpRuinPct / 100.0);

   if(balance <= ruinLine)
   {
      Print("WARNING: 破産ライン到達！残高=", balance, " ライン=", ruinLine);
      // 全ポジションをクローズ
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(posInfo.SelectByIndex(i) && posInfo.Symbol() == g_symbol && posInfo.Magic() == InpMagicNumber)
            trade.PositionClose(posInfo.Ticket());
      }
      return true;
   }
   return false;
}

//==========================================================================
// Stochastics 値取得ヘルパー
//==========================================================================
bool GetStochValues(int handle, double &k_cur, double &k_prev, double &d_cur, double &d_prev)
{
   double k_buf[], d_buf[];
   ArraySetAsSeries(k_buf, true);
   ArraySetAsSeries(d_buf, true);

   if(CopyBuffer(handle, MAIN_LINE,   0, 3, k_buf) < 3) return false;
   if(CopyBuffer(handle, SIGNAL_LINE, 0, 3, d_buf) < 3) return false;

   k_cur  = k_buf[1];   // 確定済み直近足
   k_prev = k_buf[2];   // 1本前
   d_cur  = d_buf[1];
   d_prev = d_buf[2];

   return true;
}

//==========================================================================
// ポジション数カウント（このEA管理分のみ）
//==========================================================================
int CountPositions()
{
   int count = 0;
   for(int i = 0; i < PositionsTotal(); i++)
   {
      if(posInfo.SelectByIndex(i) && posInfo.Symbol() == g_symbol && posInfo.Magic() == InpMagicNumber)
         count++;
   }
   return count;
}

//==========================================================================
// タイマー（定期ログ出力）
//==========================================================================
void OnTimer()
{
   static int tick_count = 0;
   tick_count++;
   if(tick_count % 3600 != 0) return;  // 1時間ごとにログ出力

   double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity   = AccountInfoDouble(ACCOUNT_EQUITY);
   double lot      = GetCurrentLot();

   Print("=== 定期レポート ===");
   Print("残高: ", balance, " | 評価額: ", equity);
   Print("現在ロット: ", lot);
   Print("4H ロングモード: ", g_4h_long_mode, " | ショートモード: ", g_4h_short_mode);
   Print("ポジション数: ", CountPositions());
}

//==========================================================================
// ビジュアル表示関数群
//==========================================================================

// トレード記録
void RecordTrade(ulong ticket, datetime time, double price, double lot, int type)
{
   if(g_tradeCount >= 100) return;  // 上限
   
   g_openTrades[g_tradeCount].ticket     = ticket;
   g_openTrades[g_tradeCount].entryTime  = time;
   g_openTrades[g_tradeCount].entryPrice = price;
   g_openTrades[g_tradeCount].lot        = lot;
   g_openTrades[g_tradeCount].type       = type;
   g_tradeCount++;
}

// エントリー矢印描画
void DrawEntryArrow(datetime time, double price, int type, ulong ticket, double lot)
{
   string objName = "StochL2_Entry_" + IntegerToString(ticket);
   
   if(ObjectFind(0, objName) >= 0)
      ObjectDelete(0, objName);
   
   int arrowCode = (type == 0) ? 233 : 234;  // 0=上矢印(BUY), 1=下矢印(SELL)
   color arrowColor = (type == 0) ? InpColorBuy : InpColorSell;
   
   ObjectCreate(0, objName, OBJ_ARROW, 0, time, price);
   ObjectSetInteger(0, objName, OBJPROP_ARROWCODE, arrowCode);
   ObjectSetInteger(0, objName, OBJPROP_COLOR, arrowColor);
   ObjectSetInteger(0, objName, OBJPROP_WIDTH, InpArrowSize);
   ObjectSetInteger(0, objName, OBJPROP_BACK, false);
   ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, false);
   ObjectSetString(0, objName, OBJPROP_TOOLTIP, "Entry | Ticket:" + IntegerToString(ticket) + " Lot:" + DoubleToString(lot, 2));
}

// イグジット矢印とライン・収支テキスト描画
void DrawExitAndLine(ulong ticket, datetime exitTime, double exitPrice)
{
   // 記録からエントリー情報を取得
   int idx = -1;
   for(int i = 0; i < g_tradeCount; i++)
   {
      if(g_openTrades[i].ticket == ticket)
      {
         idx = i;
         break;
      }
   }
   
   if(idx < 0) return;  // 記録なし
   
   datetime entryTime  = g_openTrades[idx].entryTime;
   double   entryPrice = g_openTrades[idx].entryPrice;
   double   lot        = g_openTrades[idx].lot;
   int      type       = g_openTrades[idx].type;
   
   // 損益計算（GOLD: 1lot=100oz想定）
   double priceDiff = (type == 0) ? (exitPrice - entryPrice) : (entryPrice - exitPrice);
   double profitUSD = priceDiff * lot * 100.0;  // 100oz/lot
   double profitJPY = profitUSD * InpUSDJPY;    // USD/JPY換算
   
   // イグジット矢印
   string objExit = "StochL2_Exit_" + IntegerToString(ticket);
   if(ObjectFind(0, objExit) >= 0)
      ObjectDelete(0, objExit);
   
   int exitArrowCode = (type == 0) ? 234 : 233;  // BUYは下矢印、SELLは上矢印
   color exitColor = (profitJPY >= 0) ? clrLime : clrRed;
   
   ObjectCreate(0, objExit, OBJ_ARROW, 0, exitTime, exitPrice);
   ObjectSetInteger(0, objExit, OBJPROP_ARROWCODE, exitArrowCode);
   ObjectSetInteger(0, objExit, OBJPROP_COLOR, exitColor);
   ObjectSetInteger(0, objExit, OBJPROP_WIDTH, InpArrowSize);
   ObjectSetInteger(0, objExit, OBJPROP_BACK, false);
   ObjectSetInteger(0, objExit, OBJPROP_SELECTABLE, false);
   ObjectSetString(0, objExit, OBJPROP_TOOLTIP, "Exit | Profit:" + DoubleToString(profitJPY, 0) + "円");
   
   // 接続ライン
   string objLine = "StochL2_Line_" + IntegerToString(ticket);
   if(ObjectFind(0, objLine) >= 0)
      ObjectDelete(0, objLine);
   
   ObjectCreate(0, objLine, OBJ_TREND, 0, entryTime, entryPrice, exitTime, exitPrice);
   ObjectSetInteger(0, objLine, OBJPROP_COLOR, InpColorLine);
   ObjectSetInteger(0, objLine, OBJPROP_STYLE, STYLE_DOT);
   ObjectSetInteger(0, objLine, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, objLine, OBJPROP_BACK, true);
   ObjectSetInteger(0, objLine, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, objLine, OBJPROP_RAY_RIGHT, false);
   
   // 収支テキスト（ラインの中央）
   string objText = "StochL2_Text_" + IntegerToString(ticket);
   if(ObjectFind(0, objText) >= 0)
      ObjectDelete(0, objText);
   
   datetime midTime = entryTime + (exitTime - entryTime) / 2;
   double midPrice = (entryPrice + exitPrice) / 2.0;
   
   string profitText = DoubleToString(lot, 2) + "lot | " + DoubleToString(profitJPY, 0) + "円";
   
   ObjectCreate(0, objText, OBJ_TEXT, 0, midTime, midPrice);
   ObjectSetString(0, objText, OBJPROP_TEXT, profitText);
   ObjectSetInteger(0, objText, OBJPROP_COLOR, exitColor);
   ObjectSetInteger(0, objText, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, objText, OBJPROP_BACK, false);
   ObjectSetInteger(0, objText, OBJPROP_SELECTABLE, false);
}

// 全ビジュアルオブジェクト削除
void DeleteAllVisuals()
{
   int total = ObjectsTotal(0, 0, OBJ_ARROW);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, OBJ_ARROW);
      if(StringFind(name, "StochL2_") == 0)
         ObjectDelete(0, name);
   }
   
   total = ObjectsTotal(0, 0, OBJ_TREND);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, OBJ_TREND);
      if(StringFind(name, "StochL2_") == 0)
         ObjectDelete(0, name);
   }
   
   total = ObjectsTotal(0, 0, OBJ_TEXT);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, OBJ_TEXT);
      if(StringFind(name, "StochL2_") == 0)
         ObjectDelete(0, name);
   }
}
//+------------------------------------------------------------------+
