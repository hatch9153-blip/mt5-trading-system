//+------------------------------------------------------------------+
//|                                                  StochLogic2.mq5 |
//| ロジック②: 4H/1H/5M Stochastics(9,3,3) — report_logic2.md 準拠   |
//| シグナル足: M5（チャートの時間足は任意・テスターも M5 以外で可）   |
//+------------------------------------------------------------------+
#property copyright "MT5 Trading System"
#property link      "https://github.com/hatch9153-blip/mt5-trading-system"
#property version   "1.01"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

input group "=== 取引 ==="
input double InpLot              = 0.01;     // ロット（C: 任意に変更）
input ulong  InpMagic            = 20260227;
input int    InpDeviationPoints  = 50;       // スリッページ（ポイント）

input group "=== 日次リスク（口座残高ベース）==="
input double InpDailyProfitPct   = 0.20;   // 当日 +n% で停止
input double InpDailyLossPct     = 0.10;   // 当日 -n% で停止
input int    InpMaxConsecLosses  = 5;      // 連敗 n で当日停止

input group "=== Stochastics(9,3,3) ==="
input int    InpKPeriod          = 9;
input int    InpDPeriod          = 3;
input int    InpSlowing          = 3;

input group "=== ゾーン（%K）==="
input double InpOversold         = 20.0;
input double InpOverbought       = 80.0;
input double InpZoneEps          = 5.0;    // 実質 0〜25 / 75〜100

input group "=== ログ ==="
input bool   InpLogTrades        = true;   // 決済時に Experts/Files に CSV 追記

//--- 内部定数
#define STRAT_NONE  0
#define STRAT_LONG  1
#define STRAT_SHORT 2

CTrade         g_trade;
CPositionInfo  g_pos;

int    g_h4 = INVALID_HANDLE;
int    g_h1 = INVALID_HANDLE;
int    g_h5 = INVALID_HANDLE;

datetime g_lastM5Bar = 0;

double   g_prevK4 = 0.0;
double   g_prevD4 = 0.0;
bool     g_havePrev4 = false;

int      g_strategy = STRAT_NONE;

int      g_dayYmd   = 0;
double   g_dayStartBalance = 0.0;
int      g_consecLosses = 0;
bool     g_dayBlocked = false;

string   g_logFile = "StochLogic2_trades.csv";

//+------------------------------------------------------------------+
//| シンボルが許可する約定タイプを CTrade に設定（テスター/ブローカー差対策） |
//+------------------------------------------------------------------+
void ApplySymbolFillingMode()
{
   long fm = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((fm & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else if((fm & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else
      g_trade.SetTypeFilling(ORDER_FILLING_RETURN);
}

//+------------------------------------------------------------------+
bool CopyStochK1(const int handle, const int buffer, const int shift, double &v)
{
   double buf[];
   if(CopyBuffer(handle, buffer, shift, 1, buf) != 1)
      return false;
   v = buf[0];
   return MathIsValidNumber(v);
}

//+------------------------------------------------------------------+
void ResetDayIfNeeded()
{
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   int ymd = t.year * 10000 + t.mon * 100 + t.day;
   if(ymd != g_dayYmd)
   {
      g_dayYmd = (int)ymd;
      g_dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
      g_consecLosses = 0;
      g_dayBlocked = false;
   }
}

//+------------------------------------------------------------------+
void UpdateDayRiskAfterClose(const double profitMoney)
{
   if(profitMoney > 0.0)
      g_consecLosses = 0;
   else
      g_consecLosses++;

   if(g_consecLosses >= InpMaxConsecLosses)
      g_dayBlocked = true;

   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   if(bal >= g_dayStartBalance * (1.0 + InpDailyProfitPct))
      g_dayBlocked = true;
   if(bal <= g_dayStartBalance * (1.0 - InpDailyLossPct))
      g_dayBlocked = true;
}

//+------------------------------------------------------------------+
bool IsNewM5Bar()
{
   datetime t = iTime(_Symbol, PERIOD_M5, 0);
   if(t == 0)
      return false;
   if(t == g_lastM5Bar)
      return false;
   g_lastM5Bar = t;
   return true;
}

//+------------------------------------------------------------------+
bool HasOurPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_pos.SelectByIndex(i))
      {
         if(g_pos.Symbol() == _Symbol && g_pos.Magic() == InpMagic)
            return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
void AppendTradeLog(const string side, const double profit, const double price)
{
   if(!InpLogTrades)
      return;
   int h = FileOpen(g_logFile, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
   if(h == INVALID_HANDLE)
   {
      Print("StochLogic2: FileOpen failed ", GetLastError());
      return;
   }
   FileSeek(h, 0, SEEK_END);
   if(FileSize(h) == 0)
      FileWrite(h, "time", "symbol", "side", "profit", "price");
   FileWrite(h, TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS), _Symbol, side,
             DoubleToString(profit, 2), DoubleToString(price, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS)));
   FileClose(h);
}

//+------------------------------------------------------------------+
int OnInit()
{
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviationPoints);
   ApplySymbolFillingMode();

   g_h4 = iStochastic(_Symbol, PERIOD_H4, InpKPeriod, InpDPeriod, InpSlowing, MODE_SMA, STO_LOWHIGH);
   g_h1 = iStochastic(_Symbol, PERIOD_H1, InpKPeriod, InpDPeriod, InpSlowing, MODE_SMA, STO_LOWHIGH);
   g_h5 = iStochastic(_Symbol, PERIOD_M5, InpKPeriod, InpDPeriod, InpSlowing, MODE_SMA, STO_LOWHIGH);

   if(g_h4 == INVALID_HANDLE || g_h1 == INVALID_HANDLE || g_h5 == INVALID_HANDLE)
   {
      Print("StochLogic2: iStochastic 作成失敗 err=", GetLastError());
      return INIT_FAILED;
   }

   MqlDateTime tm;
   TimeToStruct(TimeCurrent(), tm);
   g_dayYmd = tm.year * 10000 + tm.mon * 100 + tm.day;
   g_dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);

   Print("StochLogic2 v1.01: 初期化完了。シグナルは M5 足で判定（チャート時間足は任意）。Magic=", InpMagic,
         " filling=", (long)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_h4 != INVALID_HANDLE) IndicatorRelease(g_h4);
   if(g_h1 != INVALID_HANDLE) IndicatorRelease(g_h1);
   if(g_h5 != INVALID_HANDLE) IndicatorRelease(g_h5);
}

//+------------------------------------------------------------------+
void OnTick()
{
   // 注意: チャートが M1/H1 でも M5 の新バーで判定する（テスターは任意時間足で可）
   ResetDayIfNeeded();

   if(!IsNewM5Bar())
      return;

   if(Bars(_Symbol, PERIOD_M5) < 100)
      return;

   // インジケータ計算待ち（CopyBuffer が空になるのを防ぐ）
   if(BarsCalculated(g_h5) < 50 || BarsCalculated(g_h4) < 20 || BarsCalculated(g_h1) < 50)
      return;

   const double loZone = InpOversold + InpZoneEps;
   const double hiZone = InpOverbought - InpZoneEps;

   // 直近 **確定** した M5 バーはシフト1（新バー出現時点）
   double k5c, d5c, k5p, d5p;
   if(!CopyStochK1(g_h5, 0, 1, k5c) || !CopyStochK1(g_h5, 1, 1, d5c))
      return;
   if(!CopyStochK1(g_h5, 0, 2, k5p) || !CopyStochK1(g_h5, 1, 2, d5p))
      return;

   double k4c, d4c;
   if(!CopyStochK1(g_h4, 0, 1, k4c) || !CopyStochK1(g_h4, 1, 1, d4c))
      return;

   double k1c, d1c;
   if(!CopyStochK1(g_h1, 0, 1, k1c) || !CopyStochK1(g_h1, 1, 1, d1c))
      return;

   // --- 4H GC/DC（前 M5 処理時点の値と比較）---
   if(g_havePrev4)
   {
      bool gc4 = (g_prevK4 <= g_prevD4) && (k4c > d4c) && (k4c <= loZone);
      bool dc4 = (g_prevK4 >= g_prevD4) && (k4c < d4c) && (k4c >= hiZone);

      if(gc4)
         g_strategy = STRAT_LONG;
      else if(dc4)
         g_strategy = STRAT_SHORT;

      if(g_strategy == STRAT_LONG && dc4)
         g_strategy = STRAT_NONE;
      if(g_strategy == STRAT_SHORT && gc4)
         g_strategy = STRAT_NONE;
   }

   g_prevK4 = k4c;
   g_prevD4 = d4c;
   g_havePrev4 = true;

   bool inPos = HasOurPosition();

   // --- ポジション保有: イグジット ---
   if(inPos)
   {
      bool sel = false;
      for(int j = PositionsTotal() - 1; j >= 0; j--)
      {
         if(g_pos.SelectByIndex(j) && g_pos.Symbol() == _Symbol && g_pos.Magic() == InpMagic)
         {
            sel = true;
            break;
         }
      }
      if(!sel)
         return;

      long typ = g_pos.PositionType();
      bool exitSig = false;

      if(typ == POSITION_TYPE_BUY)
      {
         bool dc5 = (k5p >= d5p) && (k5c < d5c) && (k5c >= hiZone);
         if(dc5)
            exitSig = true;
      }
      else if(typ == POSITION_TYPE_SELL)
      {
         bool gc5 = (k5p <= d5p) && (k5c > d5c) && (k5c <= loZone);
         if(gc5)
            exitSig = true;
      }

      if(exitSig)
      {
         double pr = g_pos.Profit() + g_pos.Swap() + g_pos.Commission();
         double px = (typ == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                                  : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         if(g_trade.PositionClose(g_pos.Ticket()))
         {
            UpdateDayRiskAfterClose(pr);
            AppendTradeLog(typ == POSITION_TYPE_BUY ? "close_long" : "close_short", pr, px);
         }
      }
      return;
   }

   // --- 新規 ---
   if(g_dayBlocked)
      return;

   if(g_strategy == STRAT_NONE)
      return;

   bool k1r = (k1c > d1c);
   bool k1f = (k1c < d1c);
   bool k4r = (k4c > d4c);
   bool k4f = (k4c < d4c);

   if(g_strategy == STRAT_LONG)
   {
      if(!(k4r && k1r))
         return;
      bool gc5e = (k5p <= d5p) && (k5c > d5c) && (k5c <= loZone);
      if(gc5e)
      {
         if(g_trade.Buy(InpLot, _Symbol, 0, 0, 0, "L2 long"))
            Print("StochLogic2: Buy ", InpLot, " lot");
         else
            Print("StochLogic2: Buy failed retcode=", g_trade.ResultRetcode(), " ", g_trade.ResultComment());
      }
   }
   else if(g_strategy == STRAT_SHORT)
   {
      if(!(k4f && k1f))
         return;
      bool dc5e = (k5p >= d5p) && (k5c < d5c) && (k5c >= hiZone);
      if(dc5e)
      {
         if(g_trade.Sell(InpLot, _Symbol, 0, 0, 0, "L2 short"))
            Print("StochLogic2: Sell ", InpLot, " lot");
         else
            Print("StochLogic2: Sell failed retcode=", g_trade.ResultRetcode(), " ", g_trade.ResultComment());
      }
   }
}

//+------------------------------------------------------------------+
