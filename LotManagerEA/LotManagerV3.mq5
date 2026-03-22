//+------------------------------------------------------------------+
//|                                            LotManagerV3.mq5      |
//|                       MT5 Lot Management & Grid Order EA v3.0    |
//|          https://github.com/hatch9153-blip/mt5-trading-system    |
//+------------------------------------------------------------------+
//  v3.0 追加機能:
//    1. Buy/Sell 明示選択ボタン（ゾーンごと）
//    2. SL/TP ラインをチャート上に点線で表示
//    3. ゾーン別リアルタイム損益（保有ポジションの含み損益）
//+------------------------------------------------------------------+
#property copyright "MT5 Trading System"
#property link      "https://github.com/hatch9153-blip/mt5-trading-system"
#property version   "3.00"
#property description "Lot management EA v3.0: Buy/Sell select, SL/TP dotted lines, per-zone realtime P/L."

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\OrderInfo.mqh>

//--- Input Parameters
input double InpBaseLot          = 0.1;   // Base lot size per entry
input double InpBalancePer1000   = 0.1;   // Lot per 1000 balance
input int    InpSLOffsetDollar   = 5;     // Default Auto-SL offset ($)
input color  InpAvgBuyColor      = clrDodgerBlue;
input color  InpAvgSellColor     = clrOrangeRed;
input int    InpPanelX           = 10;
input int    InpPanelY           = 30;

//--- Global Objects
CTrade         trade;
CPositionInfo  posInfo;
COrderInfo     orderInfo;

//--- Panel constants
#define PANEL_WIDTH   360
#define MAX_ZONES     5
#define MAGIC         202603

//--- Line-pick mode enum
enum EPickMode { PICK_NONE=0, PICK_HIGH, PICK_LOW, PICK_SL, PICK_TP };

//--- Zone direction enum
enum EZoneDir { DIR_AUTO=0, DIR_BUY=1, DIR_SELL=2 };

//--- Zone structure (v3: added direction + realtime P/L)
struct ZoneInfo
{
   double   priceHigh;
   double   priceLow;
   int      splits;
   double   sl;
   double   tp;
   double   maxRisk;
   double   maxReward;
   bool     active;
   EZoneDir direction;   // v3: explicit Buy/Sell/Auto
};

//--- Global state
ZoneInfo  g_zones[MAX_ZONES];
int       g_zoneCount       = 1;
double    g_globalSL        = 0.0;
double    g_globalTP        = 0.0;
double    g_globalMaxRisk   = 0.0;
double    g_globalMaxReward = 0.0;
int       g_slMode          = 0;
bool      g_autoSL          = false;
int       g_autoSLOffset    = 5;
double    g_virtualBalance  = 0.0;
string    g_symbol          = "";
double    g_tickValue       = 0.0;
double    g_tickSize        = 0.0;
int       g_digits          = 0;

EPickMode g_pickMode        = PICK_NONE;
int       g_pickZone        = 0;

const string LINE_PICK      = "LM_PickLine";

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   g_symbol    = Symbol();
   g_tickValue = SymbolInfoDouble(g_symbol, SYMBOL_TRADE_TICK_VALUE);
   g_tickSize  = SymbolInfoDouble(g_symbol, SYMBOL_TRADE_TICK_SIZE);
   g_digits    = (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS);
   g_autoSLOffset = InpSLOffsetDollar;

   for(int i = 0; i < MAX_ZONES; i++)
   {
      g_zones[i].priceHigh  = 0.0;
      g_zones[i].priceLow   = 0.0;
      g_zones[i].splits     = 3;
      g_zones[i].sl         = 0.0;
      g_zones[i].tp         = 0.0;
      g_zones[i].maxRisk    = 0.0;
      g_zones[i].maxReward  = 0.0;
      g_zones[i].active     = (i == 0);
      g_zones[i].direction  = DIR_AUTO;
   }

   trade.SetExpertMagicNumber(MAGIC);
   trade.SetDeviationInPoints(30);

   BuildPanel();
   UpdateAveragePriceLines();
   UpdatePanelInfo();
   UpdateSLTPLines();

   ChartSetInteger(0, CHART_EVENT_MOUSE_MOVE, true);
   EventSetTimer(1);

   Print("LotManagerV3 initialized on ", g_symbol);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteAllObjects();
   // Remove SL/TP chart lines
   for(int z = 0; z < MAX_ZONES; z++)
   {
      string zs = IntegerToString(z+1);
      ObjectDelete(0, "LM_LineSL" + zs);
      ObjectDelete(0, "LM_LineTP" + zs);
   }
   ObjectDelete(0, "LM_LineGSL");
   ObjectDelete(0, "LM_LineGTP");
   Print("LotManagerV3 deinitialized.");
}

//+------------------------------------------------------------------+
//| Expert tick                                                       |
//+------------------------------------------------------------------+
void OnTick()
{
   UpdateAveragePriceLines();
   UpdatePanelInfo();
   UpdateZoneRealtimePL();
}

//+------------------------------------------------------------------+
//| Timer                                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   UpdateAveragePriceLines();
   UpdatePanelInfo();
   UpdateZoneRealtimePL();
}

//+------------------------------------------------------------------+
//| Chart event handler                                               |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_OBJECT_CLICK)
   {
      HandleButtonClick(sparam);
      return;
   }

   if(id == CHARTEVENT_OBJECT_DRAG && sparam == LINE_PICK)
   {
      double price = ObjectGetDouble(0, LINE_PICK, OBJPROP_PRICE, 0);
      ApplyPickedPrice(price);
      return;
   }

   // ESC key to cancel pick mode
   if(id == CHARTEVENT_KEYDOWN && lparam == 27)
   {
      if(g_pickMode != PICK_NONE) EndPickMode();
      return;
   }
}

//+------------------------------------------------------------------+
//| Feature 1 & 2: Average Price Lines & Position Info               |
//+------------------------------------------------------------------+

double CalcAveragePrice(ENUM_POSITION_TYPE posType, double &totalLots, int &posCount)
{
   double totalVolume = 0.0, weightedSum = 0.0;
   posCount = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(posInfo.SelectByIndex(i) &&
         posInfo.Symbol() == g_symbol &&
         posInfo.PositionType() == posType)
      {
         double vol = posInfo.Volume();
         weightedSum += posInfo.PriceOpen() * vol;
         totalVolume += vol;
         posCount++;
      }
   }
   totalLots = totalVolume;
   return (totalVolume > 0.0) ? weightedSum / totalVolume : 0.0;
}

void DrawAverageLine(string name, double price, color clr, string label)
{
   if(price <= 0.0)
   {
      ObjectDelete(0, name);
      ObjectDelete(0, name + "_lbl");
      return;
   }
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
      ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
      ObjectSetInteger(0, name, OBJPROP_STYLE,      STYLE_DASH);
      ObjectSetInteger(0, name, OBJPROP_WIDTH,      2);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   }
   else
      ObjectSetDouble(0, name, OBJPROP_PRICE, price);

   string lblName = name + "_lbl";
   if(ObjectFind(0, lblName) < 0)
      ObjectCreate(0, lblName, OBJ_TEXT, 0, iTime(g_symbol, PERIOD_CURRENT, 3), price);
   ObjectSetDouble(0,  lblName, OBJPROP_PRICE,    price);
   ObjectSetInteger(0, lblName, OBJPROP_TIME,     iTime(g_symbol, PERIOD_CURRENT, 3));
   ObjectSetString(0,  lblName, OBJPROP_TEXT,     label + ": " + DoubleToString(price, g_digits));
   ObjectSetInteger(0, lblName, OBJPROP_COLOR,    clr);
   ObjectSetInteger(0, lblName, OBJPROP_FONTSIZE, 9);
}

void UpdateAveragePriceLines()
{
   double buyLots = 0.0, sellLots = 0.0;
   int    buyCnt  = 0,   sellCnt  = 0;
   double avgBuy  = CalcAveragePrice(POSITION_TYPE_BUY,  buyLots, buyCnt);
   double avgSell = CalcAveragePrice(POSITION_TYPE_SELL, sellLots, sellCnt);
   DrawAverageLine("LM_AvgBuy",  avgBuy,  InpAvgBuyColor,  "Avg Buy");
   DrawAverageLine("LM_AvgSell", avgSell, InpAvgSellColor, "Avg Sell");
}

double GetEffectiveBalance()
{
   return (g_virtualBalance > 0.0) ? g_virtualBalance : AccountInfoDouble(ACCOUNT_BALANCE);
}

double CalcMaxAllowedLots()
{
   return MathFloor((GetEffectiveBalance() / 1000.0) * InpBalancePer1000 * 10.0) / 10.0;
}

double CalcCurrentLots()
{
   double total = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(posInfo.SelectByIndex(i) && posInfo.Symbol() == g_symbol)
         total += posInfo.Volume();
   return total;
}

//+------------------------------------------------------------------+
//| v3 NEW: SL/TP dotted lines on chart                              |
//+------------------------------------------------------------------+
void DrawSLTPLine(string name, double price, color clr, string label)
{
   if(price <= 0.0)
   {
      ObjectDelete(0, name);
      ObjectDelete(0, name + "_lbl");
      return;
   }
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
      ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
      ObjectSetInteger(0, name, OBJPROP_STYLE,      STYLE_DOT);
      ObjectSetInteger(0, name, OBJPROP_WIDTH,      1);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_BACK,       true);
   }
   else
      ObjectSetDouble(0, name, OBJPROP_PRICE, price);

   string lblName = name + "_lbl";
   if(ObjectFind(0, lblName) < 0)
      ObjectCreate(0, lblName, OBJ_TEXT, 0, iTime(g_symbol, PERIOD_CURRENT, 5), price);
   ObjectSetDouble(0,  lblName, OBJPROP_PRICE,    price);
   ObjectSetInteger(0, lblName, OBJPROP_TIME,     iTime(g_symbol, PERIOD_CURRENT, 5));
   ObjectSetString(0,  lblName, OBJPROP_TEXT,     label + ": " + DoubleToString(price, g_digits));
   ObjectSetInteger(0, lblName, OBJPROP_COLOR,    clr);
   ObjectSetInteger(0, lblName, OBJPROP_FONTSIZE, 8);
}

void UpdateSLTPLines()
{
   // Global SL/TP lines
   DrawSLTPLine("LM_LineGSL", g_globalSL, clrTomato,      "GSL");
   DrawSLTPLine("LM_LineGTP", g_globalTP, clrMediumOrchid,"GTP");

   // Per-zone SL/TP lines (only when SL mode = PerZone)
   for(int z = 0; z < MAX_ZONES; z++)
   {
      string zs = IntegerToString(z+1);
      if(g_slMode == 2 && z < g_zoneCount && g_zones[z].active)
      {
         DrawSLTPLine("LM_LineSL" + zs, g_zones[z].sl, clrOrangeRed,   "Z" + zs + "-SL");
         DrawSLTPLine("LM_LineTP" + zs, g_zones[z].tp, clrDeepSkyBlue, "Z" + zs + "-TP");
      }
      else
      {
         ObjectDelete(0, "LM_LineSL" + zs);
         ObjectDelete(0, "LM_LineSL" + zs + "_lbl");
         ObjectDelete(0, "LM_LineTP" + zs);
         ObjectDelete(0, "LM_LineTP" + zs + "_lbl");
      }
   }
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| v3 NEW: Per-zone realtime P/L (open positions tagged by comment) |
//+------------------------------------------------------------------+
double CalcZoneRealtimePL(int zoneIdx)
{
   double pl = 0.0;
   string tag = "LMv3_Z" + IntegerToString(zoneIdx + 1);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(posInfo.SelectByIndex(i) &&
         posInfo.Symbol() == g_symbol &&
         posInfo.Comment() == tag)
      {
         pl += posInfo.Commission() + posInfo.Swap() + posInfo.Profit();
      }
   }
   return pl;
}

void UpdateZoneRealtimePL()
{
   for(int z = 0; z < g_zoneCount; z++)
   {
      string zs  = IntegerToString(z+1);
      string obj = "LM_ValZPL" + zs;
      if(ObjectFind(0, obj) < 0) continue;

      double pl = CalcZoneRealtimePL(z);
      string txt = (pl >= 0.0)
                   ? "+" + DoubleToString(pl, 2)
                   :        DoubleToString(pl, 2);
      color  clr = (pl >= 0.0) ? clrLimeGreen : clrOrangeRed;
      ObjectSetString(0,  obj, OBJPROP_TEXT,  txt);
      ObjectSetInteger(0, obj, OBJPROP_COLOR, clr);
   }
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Swing High/Low & Auto SL                                         |
//+------------------------------------------------------------------+

double FindSwingHigh(int lookback)
{
   double highest = -1.0;
   for(int i = 1; i <= lookback; i++)
   {
      double h = iHigh(g_symbol, PERIOD_CURRENT, i);
      if(h > highest) highest = h;
   }
   return highest;
}

double FindSwingLow(int lookback)
{
   double lowest = DBL_MAX;
   for(int i = 1; i <= lookback; i++)
   {
      double l = iLow(g_symbol, PERIOD_CURRENT, i);
      if(l < lowest) lowest = l;
   }
   return lowest;
}

double DollarToPrice(double dollars, double lots = 0.0)
{
   double useLots = (lots > 0.0) ? lots : InpBaseLot;
   if(g_tickValue <= 0.0 || useLots <= 0.0) return dollars * 0.01;
   return dollars * g_tickSize / (g_tickValue * useLots);
}

double CalcAutoSL(bool isBuy, int lookback = 100)
{
   double offset = DollarToPrice((double)g_autoSLOffset);
   if(isBuy)
      return NormalizeDouble(FindSwingLow(lookback) - offset, g_digits);
   else
      return NormalizeDouble(FindSwingHigh(lookback) + offset, g_digits);
}

//+------------------------------------------------------------------+
//| Chart-Line Pick Mode                                              |
//+------------------------------------------------------------------+

void StartPickMode(EPickMode mode, int zoneIdx)
{
   g_pickMode = mode;
   g_pickZone = zoneIdx;

   double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
   if(ObjectFind(0, LINE_PICK) >= 0) ObjectDelete(0, LINE_PICK);
   ObjectCreate(0, LINE_PICK, OBJ_HLINE, 0, 0, bid);

   color  lineColor = clrYellow;
   string label     = "PICK";
   if(mode == PICK_HIGH) { lineColor = clrLime;       label = "Z" + IntegerToString(zoneIdx+1) + " HIGH  drag & ESC=cancel"; }
   if(mode == PICK_LOW)  { lineColor = clrAqua;       label = "Z" + IntegerToString(zoneIdx+1) + " LOW   drag & ESC=cancel"; }
   if(mode == PICK_SL)   { lineColor = clrOrangeRed;  label = "Z" + IntegerToString(zoneIdx+1) + " SL    drag & ESC=cancel"; }
   if(mode == PICK_TP)   { lineColor = clrDodgerBlue; label = "Z" + IntegerToString(zoneIdx+1) + " TP    drag & ESC=cancel"; }

   ObjectSetInteger(0, LINE_PICK, OBJPROP_COLOR,      lineColor);
   ObjectSetInteger(0, LINE_PICK, OBJPROP_STYLE,      STYLE_SOLID);
   ObjectSetInteger(0, LINE_PICK, OBJPROP_WIDTH,      2);
   ObjectSetInteger(0, LINE_PICK, OBJPROP_SELECTABLE, true);
   ObjectSetInteger(0, LINE_PICK, OBJPROP_SELECTED,   true);
   ObjectSetString(0,  LINE_PICK, OBJPROP_TOOLTIP,    label);

   ObjectSetString(0,  "LM_PickStatus", OBJPROP_TEXT,  "PICK: " + label);
   ObjectSetInteger(0, "LM_PickStatus", OBJPROP_COLOR, lineColor);
   ChartRedraw(0);
}

void ApplyPickedPrice(double price)
{
   string zs = IntegerToString(g_pickZone + 1);
   if(g_pickMode == PICK_HIGH)
   {
      g_zones[g_pickZone].priceHigh = NormalizeDouble(price, g_digits);
      ObjectSetString(0, "LM_EditZH"  + zs, OBJPROP_TEXT, DoubleToString(price, g_digits));
   }
   else if(g_pickMode == PICK_LOW)
   {
      g_zones[g_pickZone].priceLow = NormalizeDouble(price, g_digits);
      ObjectSetString(0, "LM_EditZL"  + zs, OBJPROP_TEXT, DoubleToString(price, g_digits));
   }
   else if(g_pickMode == PICK_SL)
   {
      g_zones[g_pickZone].sl = NormalizeDouble(price, g_digits);
      ObjectSetString(0, "LM_EditZSL" + zs, OBJPROP_TEXT, DoubleToString(price, g_digits));
      UpdateSLTPLines();
   }
   else if(g_pickMode == PICK_TP)
   {
      g_zones[g_pickZone].tp = NormalizeDouble(price, g_digits);
      ObjectSetString(0, "LM_EditZTP" + zs, OBJPROP_TEXT, DoubleToString(price, g_digits));
      UpdateSLTPLines();
   }
   ChartRedraw(0);
}

void EndPickMode()
{
   g_pickMode = PICK_NONE;
   ObjectDelete(0, LINE_PICK);
   ObjectSetString(0, "LM_PickStatus", OBJPROP_TEXT, "");
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Grid Order Placement                                              |
//+------------------------------------------------------------------+

bool IsZoneBuy(int z)
{
   if(g_zones[z].direction == DIR_BUY)  return true;
   if(g_zones[z].direction == DIR_SELL) return false;
   // DIR_AUTO: High >= Low → Buy
   return (g_zones[z].priceHigh >= g_zones[z].priceLow);
}

void CalcExpectedPL(double &totalRisk, double &totalReward)
{
   totalRisk = 0.0; totalReward = 0.0;

   for(int z = 0; z < g_zoneCount; z++)
   {
      if(!g_zones[z].active) continue;
      if(g_zones[z].priceHigh <= 0.0 || g_zones[z].priceLow <= 0.0) continue;
      if(g_zones[z].splits <= 0) continue;

      double range = MathAbs(g_zones[z].priceHigh - g_zones[z].priceLow);
      double step  = (g_zones[z].splits > 1) ? range / (g_zones[z].splits - 1) : 0.0;
      double sl    = (g_slMode == 2) ? g_zones[z].sl : g_globalSL;
      double tp    = (g_slMode == 2) ? g_zones[z].tp : g_globalTP;

      double zoneRisk = 0.0, zoneReward = 0.0;

      for(int s = 0; s < g_zones[z].splits; s++)
      {
         double entryPrice = g_zones[z].priceHigh - step * s;
         if(sl > 0.0 && g_tickSize > 0.0)
            zoneRisk   += MathAbs(entryPrice - sl) / g_tickSize * g_tickValue * InpBaseLot;
         if(tp > 0.0 && g_tickSize > 0.0)
            zoneReward += MathAbs(tp - entryPrice)  / g_tickSize * g_tickValue * InpBaseLot;
      }

      if(g_zones[z].maxRisk   > 0.0) zoneRisk   = MathMin(zoneRisk,   g_zones[z].maxRisk);
      if(g_zones[z].maxReward > 0.0) zoneReward = MathMin(zoneReward, g_zones[z].maxReward);

      totalRisk   += zoneRisk;
      totalReward += zoneReward;
   }

   if(g_globalMaxRisk   > 0.0) totalRisk   = MathMin(totalRisk,   g_globalMaxRisk);
   if(g_globalMaxReward > 0.0) totalReward = MathMin(totalReward, g_globalMaxReward);
}

void PlaceGridOrders()
{
   ReadPanelFields();
   int totalPlaced = 0;

   for(int z = 0; z < g_zoneCount; z++)
   {
      if(!g_zones[z].active) continue;
      if(g_zones[z].priceHigh <= 0.0 || g_zones[z].priceLow <= 0.0)
      {
         Print("Zone ", z+1, ": price range not set.");
         continue;
      }
      if(g_zones[z].splits <= 0) continue;

      bool   isBuy = IsZoneBuy(z);
      double high  = g_zones[z].priceHigh;
      double low   = g_zones[z].priceLow;
      double range = MathAbs(high - low);
      double step  = (g_zones[z].splits > 1) ? range / (g_zones[z].splits - 1) : 0.0;

      double sl = (g_slMode == 2) ? g_zones[z].sl : g_globalSL;
      double tp = (g_slMode == 2) ? g_zones[z].tp : g_globalTP;
      if(g_autoSL && sl == 0.0) sl = CalcAutoSL(isBuy);

      string comment = "LMv3_Z" + IntegerToString(z+1);

      for(int s = 0; s < g_zones[z].splits; s++)
      {
         double price  = NormalizeDouble(high - step * s, g_digits);
         double slNorm = NormalizeDouble(sl, g_digits);
         double tpNorm = NormalizeDouble(tp, g_digits);
         bool   result = false;

         if(isBuy)
         {
            double ask = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
            if(price < ask)
               result = trade.BuyLimit(InpBaseLot,  price, g_symbol, slNorm, tpNorm, ORDER_TIME_GTC, 0, comment);
            else
               result = trade.BuyStop(InpBaseLot,   price, g_symbol, slNorm, tpNorm, ORDER_TIME_GTC, 0, comment);
         }
         else
         {
            double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
            if(price > bid)
               result = trade.SellLimit(InpBaseLot, price, g_symbol, slNorm, tpNorm, ORDER_TIME_GTC, 0, comment);
            else
               result = trade.SellStop(InpBaseLot,  price, g_symbol, slNorm, tpNorm, ORDER_TIME_GTC, 0, comment);
         }

         if(result) totalPlaced++;
         else Print("Order failed at ", price, " | Error: ", GetLastError());
      }
   }
   Print("LotManagerV3: Placed ", totalPlaced, " orders.");
   UpdatePanelInfo();
}

void CancelAllGridOrders()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(orderInfo.SelectByIndex(i) &&
         orderInfo.Symbol() == g_symbol &&
         orderInfo.Magic()  == MAGIC)
         trade.OrderDelete(orderInfo.Ticket());
   }
   Print("LotManagerV3: All grid orders cancelled.");
}

//+------------------------------------------------------------------+
//| GUI Panel helpers                                                 |
//+------------------------------------------------------------------+

void DeleteAllObjects() { ObjectsDeleteAll(0, "LM_"); }

void CreateRect(string name, int x, int y, int w, int h, color bgColor, int corner = CORNER_LEFT_UPPER)
{
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,   x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,   y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE,       w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE,       h);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR,     bgColor);
   ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, name, OBJPROP_COLOR,       clrGray);
   ObjectSetInteger(0, name, OBJPROP_CORNER,      corner);
   ObjectSetInteger(0, name, OBJPROP_BACK,        false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE,  false);
}

void CreateLabel(string name, int x, int y, string text, color clr, int fontSize = 9, int corner = CORNER_LEFT_UPPER)
{
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,  y);
   ObjectSetString(0,  name, OBJPROP_TEXT,       text);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   fontSize);
   ObjectSetInteger(0, name, OBJPROP_CORNER,     corner);
   ObjectSetInteger(0, name, OBJPROP_BACK,       false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
}

void CreateButton(string name, int x, int y, int w, int h, string text,
                  color bgColor, color textColor = clrWhite, int corner = CORNER_LEFT_UPPER)
{
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,  y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE,      w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE,      h);
   ObjectSetString(0,  name, OBJPROP_TEXT,       text);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR,    bgColor);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      textColor);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   9);
   ObjectSetInteger(0, name, OBJPROP_CORNER,     corner);
   ObjectSetInteger(0, name, OBJPROP_BACK,       false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
}

void CreateEdit(string name, int x, int y, int w, int h, string text, int corner = CORNER_LEFT_UPPER)
{
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_EDIT, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,  y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE,      w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE,      h);
   ObjectSetString(0,  name, OBJPROP_TEXT,       text);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR,    clrWhiteSmoke);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clrBlack);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   9);
   ObjectSetInteger(0, name, OBJPROP_CORNER,     corner);
   ObjectSetInteger(0, name, OBJPROP_BACK,       false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_READONLY,   false);
}

//+------------------------------------------------------------------+
//| Build the full panel                                              |
//+------------------------------------------------------------------+
void BuildPanel()
{
   int x  = InpPanelX;
   int lh = 20;
   int py = InpPanelY;

   // Estimate height: base + zones (4 rows each) + rest
   int panelH = 5 + 22 + lh*8 + 5 + lh + 5
              + g_zoneCount * (lh*4 + 4)
              + lh*4 + 5 + lh*2 + 5 + lh*2 + 5 + 28*2 + 20;

   CreateRect("LM_BG", x, py, PANEL_WIDTH, panelH, C'30,30,40');
   py += 5;

   // Title
   CreateLabel("LM_Title", x+10, py, "=== LotManagerV3 ===", clrGold, 10);
   py += 22;

   // Account & Position Info
   CreateLabel("LM_SecInfo", x+10, py, "-- Account & Position Info --", clrSilver, 9);
   py += lh;

   // Virtual Balance
   CreateLabel("LM_LblVBal",     x+10,  py, "VirtBal($):", clrWhite, 9);
   CreateEdit("LM_EditVBal",     x+90,  py, 80, 16,
              (g_virtualBalance > 0.0 ? DoubleToString(g_virtualBalance, 2) : "0"));
   CreateLabel("LM_LblVBalHint", x+175, py, "(0=real)", clrGray, 8);
   py += lh;

   CreateLabel("LM_LblBalance",  x+10, py, "Balance:",      clrWhite, 9);
   CreateLabel("LM_ValBalance",  x+90, py, "---",           clrYellow, 9);
   py += lh;
   CreateLabel("LM_LblMaxLot",   x+10, py, "Max Lots:",     clrWhite, 9);
   CreateLabel("LM_ValMaxLot",   x+90, py, "---",           clrYellow, 9);
   py += lh;
   CreateLabel("LM_LblCurLot",   x+10, py, "Current Lots:", clrWhite, 9);
   CreateLabel("LM_ValCurLot",   x+90, py, "---",           clrCyan, 9);
   py += lh;
   CreateLabel("LM_LblAddLot",   x+10, py, "Addable:",      clrWhite, 9);
   CreateLabel("LM_ValAddLot",   x+90, py, "---",           clrLimeGreen, 9);
   py += lh;
   CreateLabel("LM_LblPosCnt",   x+10, py, "Positions:",    clrWhite, 9);
   CreateLabel("LM_ValPosCnt",   x+90, py, "Buy:0 Sell:0",  clrCyan, 9);
   py += lh;
   CreateLabel("LM_LblAvgBuy",   x+10, py, "Avg Buy:",      clrDodgerBlue, 9);
   CreateLabel("LM_ValAvgBuy",   x+90, py, "---",           clrDodgerBlue, 9);
   py += lh;
   CreateLabel("LM_LblAvgSell",  x+10, py, "Avg Sell:",     clrOrangeRed, 9);
   CreateLabel("LM_ValAvgSell",  x+90, py, "---",           clrOrangeRed, 9);
   py += lh + 5;

   // Zone Count Selection
   CreateLabel("LM_SecZone",    x+10, py, "-- Active Zones --", clrSilver, 9);
   py += lh;
   CreateLabel("LM_LblZoneCnt", x+10, py, "Zones:", clrWhite, 9);
   for(int i = 1; i <= MAX_ZONES; i++)
   {
      color bc = (i == g_zoneCount) ? clrGold : C'50,50,70';
      CreateButton("LM_BtnZ" + IntegerToString(i),
                   x+55+(i-1)*26, py, 24, 18, IntegerToString(i), bc, clrWhite);
   }
   py += lh + 5;

   // Zone Input Rows
   for(int z = 0; z < g_zoneCount; z++)
   {
      string zs = IntegerToString(z+1);

      // Zone header + realtime P/L
      CreateLabel("LM_LblZHdr" + zs, x+10,  py, "[ Zone " + zs + " ]", clrGold, 9);
      CreateLabel("LM_LblZPL"  + zs, x+100, py, "P/L:",                 clrSilver, 9);
      CreateLabel("LM_ValZPL"  + zs, x+130, py, "---",                  clrLimeGreen, 9);
      py += lh;

      // Buy/Sell direction buttons (v3 new)
      CreateLabel("LM_LblZDir" + zs, x+10, py, "Dir:", clrWhite, 9);
      color cAuto = (g_zones[z].direction == DIR_AUTO) ? clrGold      : C'50,50,70';
      color cBuy  = (g_zones[z].direction == DIR_BUY)  ? clrDodgerBlue: C'50,50,70';
      color cSell = (g_zones[z].direction == DIR_SELL) ? clrOrangeRed : C'50,50,70';
      CreateButton("LM_BtnDirAuto" + zs, x+45,  py, 38, 16, "Auto", cAuto, clrWhite);
      CreateButton("LM_BtnDirBuy"  + zs, x+86,  py, 38, 16, "Buy",  cBuy,  clrWhite);
      CreateButton("LM_BtnDirSell" + zs, x+127, py, 38, 16, "Sell", cSell, clrWhite);
      py += lh;

      // High / Low row
      CreateLabel("LM_LblZH" + zs,    x+10,  py, "High:", clrWhite, 9);
      CreateEdit("LM_EditZH" + zs,     x+45,  py, 68, 16,
                 (g_zones[z].priceHigh > 0.0 ? DoubleToString(g_zones[z].priceHigh, g_digits) : "0.00"));
      CreateButton("LM_BtnPickH" + zs, x+116, py, 18, 16, "L", C'0,80,0', clrWhite);

      CreateLabel("LM_LblZL" + zs,    x+138, py, "Low:", clrWhite, 9);
      CreateEdit("LM_EditZL" + zs,     x+165, py, 68, 16,
                 (g_zones[z].priceLow > 0.0 ? DoubleToString(g_zones[z].priceLow, g_digits) : "0.00"));
      CreateButton("LM_BtnPickL" + zs, x+236, py, 18, 16, "L", C'0,60,80', clrWhite);
      py += lh;

      // Splits / TP / SL row
      CreateLabel("LM_LblZS" + zs,     x+10,  py, "Splits:", clrWhite, 9);
      CreateEdit("LM_EditZS" + zs,      x+55,  py, 30, 16, IntegerToString(g_zones[z].splits));

      CreateLabel("LM_LblZTP" + zs,    x+92,  py, "TP:", clrWhite, 9);
      CreateEdit("LM_EditZTP" + zs,     x+110, py, 60, 16,
                 (g_zones[z].tp > 0.0 ? DoubleToString(g_zones[z].tp, g_digits) : "0.00"));
      CreateButton("LM_BtnPickTP" + zs, x+173, py, 18, 16, "L", C'0,60,140', clrWhite);

      CreateLabel("LM_LblZSL" + zs,    x+195, py, "SL:", clrWhite, 9);
      CreateEdit("LM_EditZSL" + zs,     x+213, py, 60, 16,
                 (g_zones[z].sl > 0.0 ? DoubleToString(g_zones[z].sl, g_digits) : "0.00"));
      CreateButton("LM_BtnPickSL" + zs, x+276, py, 18, 16, "L", C'140,40,0', clrWhite);
      py += lh;

      // MaxRisk / MaxReward row
      CreateLabel("LM_LblZMR" + zs,   x+10,  py, "MaxRisk($):", clrWhite, 9);
      CreateEdit("LM_EditZMR" + zs,    x+80,  py, 50, 16,
                 (g_zones[z].maxRisk > 0.0 ? DoubleToString(g_zones[z].maxRisk, 2) : "0"));
      CreateLabel("LM_LblZMRw" + zs,  x+135, py, "MaxRwd($):", clrWhite, 9);
      CreateEdit("LM_EditZMRw" + zs,   x+205, py, 50, 16,
                 (g_zones[z].maxReward > 0.0 ? DoubleToString(g_zones[z].maxReward, 2) : "0"));
      py += lh + 4;
   }

   // Global SL/TP
   CreateLabel("LM_SecSLTP", x+10,  py, "-- Global SL/TP --", clrSilver, 9);
   py += lh;
   CreateLabel("LM_LblGSL",  x+10,  py, "Global SL:", clrWhite, 9);
   CreateEdit("LM_EditGSL",  x+80,  py, 70, 16, (g_globalSL > 0.0 ? DoubleToString(g_globalSL, g_digits) : "0.00"));
   CreateLabel("LM_LblGTP",  x+160, py, "Global TP:", clrWhite, 9);
   CreateEdit("LM_EditGTP",  x+230, py, 70, 16, (g_globalTP > 0.0 ? DoubleToString(g_globalTP, g_digits) : "0.00"));
   py += lh;

   // SL Mode
   CreateLabel("LM_LblSLMode", x+10,  py, "SL Mode:", clrWhite, 9);
   CreateButton("LM_BtnSLM0",  x+75,  py, 65, 18, "Global",   (g_slMode==0 ? clrGold : C'50,50,70'), clrWhite);
   CreateButton("LM_BtnSLM1",  x+143, py, 65, 18, "PerOrder", (g_slMode==1 ? clrGold : C'50,50,70'), clrWhite);
   CreateButton("LM_BtnSLM2",  x+211, py, 65, 18, "PerZone",  (g_slMode==2 ? clrGold : C'50,50,70'), clrWhite);
   py += lh;

   // Auto SL + editable offset
   CreateButton("LM_BtnAutoSL", x+10,  py, 130, 18,
                (g_autoSL ? "[ON] AutoSL(Swing)" : "[OFF] AutoSL(Swing)"),
                (g_autoSL ? clrDarkGreen : C'50,50,70'), clrWhite);
   CreateLabel("LM_LblASLOff",  x+145, py, "Offset($):", clrWhite, 9);
   CreateEdit("LM_EditASLOff",  x+215, py, 50, 16, IntegerToString(g_autoSLOffset));
   py += lh;

   // Global MaxRisk / MaxReward
   CreateLabel("LM_LblGMR",  x+10,  py, "MaxRisk($):", clrWhite, 9);
   CreateEdit("LM_EditGMR",  x+80,  py, 60, 16,
              (g_globalMaxRisk > 0.0 ? DoubleToString(g_globalMaxRisk, 2) : "0"));
   CreateLabel("LM_LblGMRw", x+148, py, "MaxRwd($):", clrWhite, 9);
   CreateEdit("LM_EditGMRw", x+218, py, 60, 16,
              (g_globalMaxReward > 0.0 ? DoubleToString(g_globalMaxReward, 2) : "0"));
   py += lh + 5;

   // Expected P/L
   CreateLabel("LM_SecPL",     x+10,  py, "-- Expected P/L --", clrSilver, 9);
   py += lh;
   CreateLabel("LM_LblRisk",   x+10,  py, "Max Risk ($):",   clrWhite, 9);
   CreateLabel("LM_ValRisk",   x+110, py, "---",             clrOrangeRed, 9);
   py += lh;
   CreateLabel("LM_LblReward", x+10,  py, "Max Reward ($):", clrWhite, 9);
   CreateLabel("LM_ValReward", x+110, py, "---",             clrLimeGreen, 9);
   py += lh + 5;

   // Action Buttons
   CreateButton("LM_BtnCalc",    x+10,  py, 90, 22, "Calc P/L",     C'0,80,120',  clrWhite);
   CreateButton("LM_BtnPlace",   x+110, py, 90, 22, "Place Orders", C'0,120,0',   clrWhite);
   CreateButton("LM_BtnCancel",  x+210, py, 90, 22, "Cancel All",   C'140,0,0',   clrWhite);
   py += 28;
   CreateButton("LM_BtnRefresh", x+10,  py, 90, 22, "Refresh",      C'60,60,80',  clrWhite);
   CreateButton("LM_BtnRead",    x+110, py, 90, 22, "Read Fields",  C'80,60,20',  clrWhite);
   py += 28;

   // Pick status label
   CreateLabel("LM_PickStatus", x+10, py, "", clrYellow, 9);

   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Read all edit field values into g_zones and globals              |
//+------------------------------------------------------------------+
void ReadPanelFields()
{
   // Virtual balance
   double vb = StringToDouble(ObjectGetString(0, "LM_EditVBal", OBJPROP_TEXT));
   g_virtualBalance = (vb > 0.0) ? vb : 0.0;

   // AutoSL offset
   int aslOff = (int)StringToInteger(ObjectGetString(0, "LM_EditASLOff", OBJPROP_TEXT));
   if(aslOff > 0) g_autoSLOffset = aslOff;

   // Global SL/TP and MaxRisk/Reward
   g_globalSL        = StringToDouble(ObjectGetString(0, "LM_EditGSL",  OBJPROP_TEXT));
   g_globalTP        = StringToDouble(ObjectGetString(0, "LM_EditGTP",  OBJPROP_TEXT));
   g_globalMaxRisk   = StringToDouble(ObjectGetString(0, "LM_EditGMR",  OBJPROP_TEXT));
   g_globalMaxReward = StringToDouble(ObjectGetString(0, "LM_EditGMRw", OBJPROP_TEXT));

   // Per-zone fields
   for(int z = 0; z < MAX_ZONES; z++)
   {
      string zs = IntegerToString(z+1);
      if(z < g_zoneCount)
      {
         g_zones[z].priceHigh = StringToDouble(ObjectGetString(0, "LM_EditZH"   + zs, OBJPROP_TEXT));
         g_zones[z].priceLow  = StringToDouble(ObjectGetString(0, "LM_EditZL"   + zs, OBJPROP_TEXT));
         g_zones[z].splits    = (int)StringToInteger(ObjectGetString(0, "LM_EditZS"  + zs, OBJPROP_TEXT));
         g_zones[z].tp        = StringToDouble(ObjectGetString(0, "LM_EditZTP"  + zs, OBJPROP_TEXT));
         g_zones[z].sl        = StringToDouble(ObjectGetString(0, "LM_EditZSL"  + zs, OBJPROP_TEXT));
         g_zones[z].maxRisk   = StringToDouble(ObjectGetString(0, "LM_EditZMR"  + zs, OBJPROP_TEXT));
         g_zones[z].maxReward = StringToDouble(ObjectGetString(0, "LM_EditZMRw" + zs, OBJPROP_TEXT));
      }
      g_zones[z].active = (z < g_zoneCount);
   }

   // Update SL/TP chart lines after reading
   UpdateSLTPLines();
}

//+------------------------------------------------------------------+
//| Update dynamic labels                                             |
//+------------------------------------------------------------------+
void UpdatePanelInfo()
{
   double balance  = GetEffectiveBalance();
   double maxLots  = CalcMaxAllowedLots();
   double curLots  = CalcCurrentLots();
   double addLots  = MathMax(0.0, maxLots - curLots);
   int    addPosns = (InpBaseLot > 0.0) ? (int)MathFloor(addLots / InpBaseLot) : 0;

   double buyLots = 0.0, sellLots = 0.0;
   int    buyCnt  = 0,   sellCnt  = 0;
   double avgBuy  = CalcAveragePrice(POSITION_TYPE_BUY,  buyLots, buyCnt);
   double avgSell = CalcAveragePrice(POSITION_TYPE_SELL, sellLots, sellCnt);

   string balLabel = DoubleToString(balance, 2);
   if(g_virtualBalance > 0.0) balLabel += " [VIRT]";

   ObjectSetString(0, "LM_ValBalance", OBJPROP_TEXT, balLabel);
   ObjectSetString(0, "LM_ValMaxLot",  OBJPROP_TEXT, DoubleToString(maxLots, 2) + " lots");
   ObjectSetString(0, "LM_ValCurLot",  OBJPROP_TEXT, DoubleToString(curLots, 2) + " lots");
   ObjectSetString(0, "LM_ValAddLot",  OBJPROP_TEXT,
                   DoubleToString(addLots, 2) + " lots (" + IntegerToString(addPosns) + " pos)");
   ObjectSetString(0, "LM_ValPosCnt",  OBJPROP_TEXT,
                   "Buy:" + IntegerToString(buyCnt) + " Sell:" + IntegerToString(sellCnt));
   ObjectSetString(0, "LM_ValAvgBuy",  OBJPROP_TEXT,
                   (avgBuy  > 0.0 ? DoubleToString(avgBuy,  g_digits) : "---"));
   ObjectSetString(0, "LM_ValAvgSell", OBJPROP_TEXT,
                   (avgSell > 0.0 ? DoubleToString(avgSell, g_digits) : "---"));

   ChartRedraw(0);
}

void UpdateExpectedPL()
{
   ReadPanelFields();
   double risk = 0.0, reward = 0.0;
   CalcExpectedPL(risk, reward);
   ObjectSetString(0, "LM_ValRisk",   OBJPROP_TEXT, DoubleToString(risk,   2));
   ObjectSetString(0, "LM_ValReward", OBJPROP_TEXT, DoubleToString(reward, 2));
   ChartRedraw(0);
}

void RefreshZoneButtons()
{
   for(int i = 1; i <= MAX_ZONES; i++)
      ObjectSetInteger(0, "LM_BtnZ" + IntegerToString(i), OBJPROP_BGCOLOR,
                       (i == g_zoneCount ? clrGold : C'50,50,70'));
   ChartRedraw(0);
}

void RefreshSLModeButtons()
{
   ObjectSetInteger(0, "LM_BtnSLM0", OBJPROP_BGCOLOR, (g_slMode==0 ? clrGold : C'50,50,70'));
   ObjectSetInteger(0, "LM_BtnSLM1", OBJPROP_BGCOLOR, (g_slMode==1 ? clrGold : C'50,50,70'));
   ObjectSetInteger(0, "LM_BtnSLM2", OBJPROP_BGCOLOR, (g_slMode==2 ? clrGold : C'50,50,70'));
   UpdateSLTPLines();
   ChartRedraw(0);
}

void RefreshDirButtons(int z)
{
   string zs = IntegerToString(z+1);
   ObjectSetInteger(0, "LM_BtnDirAuto" + zs, OBJPROP_BGCOLOR,
                    (g_zones[z].direction == DIR_AUTO ? clrGold       : C'50,50,70'));
   ObjectSetInteger(0, "LM_BtnDirBuy"  + zs, OBJPROP_BGCOLOR,
                    (g_zones[z].direction == DIR_BUY  ? clrDodgerBlue : C'50,50,70'));
   ObjectSetInteger(0, "LM_BtnDirSell" + zs, OBJPROP_BGCOLOR,
                    (g_zones[z].direction == DIR_SELL ? clrOrangeRed  : C'50,50,70'));
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Button click handler                                              |
//+------------------------------------------------------------------+
void HandleButtonClick(string name)
{
   // Zone count buttons
   for(int i = 1; i <= MAX_ZONES; i++)
   {
      if(name == "LM_BtnZ" + IntegerToString(i))
      {
         ReadPanelFields();
         g_zoneCount = i;
         for(int z = 0; z < MAX_ZONES; z++) g_zones[z].active = (z < g_zoneCount);
         DeleteAllObjects();
         BuildPanel();
         UpdatePanelInfo();
         UpdateSLTPLines();
         ObjectSetInteger(0, name, OBJPROP_STATE, false);
         return;
      }
   }

   // Direction buttons (v3 new)
   for(int z = 0; z < MAX_ZONES; z++)
   {
      string zs = IntegerToString(z+1);
      if(name == "LM_BtnDirAuto" + zs) { g_zones[z].direction = DIR_AUTO; RefreshDirButtons(z); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
      if(name == "LM_BtnDirBuy"  + zs) { g_zones[z].direction = DIR_BUY;  RefreshDirButtons(z); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
      if(name == "LM_BtnDirSell" + zs) { g_zones[z].direction = DIR_SELL; RefreshDirButtons(z); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
   }

   // Chart-line pick buttons
   for(int z = 0; z < MAX_ZONES; z++)
   {
      string zs = IntegerToString(z+1);
      if(name == "LM_BtnPickH"  + zs) { StartPickMode(PICK_HIGH, z); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
      if(name == "LM_BtnPickL"  + zs) { StartPickMode(PICK_LOW,  z); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
      if(name == "LM_BtnPickSL" + zs) { StartPickMode(PICK_SL,   z); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
      if(name == "LM_BtnPickTP" + zs) { StartPickMode(PICK_TP,   z); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
   }

   // SL mode
   if(name == "LM_BtnSLM0") { g_slMode = 0; RefreshSLModeButtons(); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
   if(name == "LM_BtnSLM1") { g_slMode = 1; RefreshSLModeButtons(); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
   if(name == "LM_BtnSLM2") { g_slMode = 2; RefreshSLModeButtons(); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }

   // Auto SL toggle
   if(name == "LM_BtnAutoSL")
   {
      g_autoSL = !g_autoSL;
      ObjectSetString(0,  "LM_BtnAutoSL", OBJPROP_TEXT,   (g_autoSL ? "[ON] AutoSL(Swing)" : "[OFF] AutoSL(Swing)"));
      ObjectSetInteger(0, "LM_BtnAutoSL", OBJPROP_BGCOLOR, (g_autoSL ? clrDarkGreen : C'50,50,70'));
      ObjectSetInteger(0, name, OBJPROP_STATE, false);
      ChartRedraw(0);
      return;
   }

   if(name == "LM_BtnCalc")   { UpdateExpectedPL();   ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
   if(name == "LM_BtnPlace")  { PlaceGridOrders();     ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }
   if(name == "LM_BtnCancel") { CancelAllGridOrders(); ObjectSetInteger(0, name, OBJPROP_STATE, false); return; }

   if(name == "LM_BtnRefresh")
   {
      DeleteAllObjects();
      BuildPanel();
      UpdateAveragePriceLines();
      UpdatePanelInfo();
      UpdateSLTPLines();
      UpdateZoneRealtimePL();
      ObjectSetInteger(0, name, OBJPROP_STATE, false);
      return;
   }

   if(name == "LM_BtnRead")
   {
      ReadPanelFields();
      UpdateExpectedPL();
      ObjectSetInteger(0, name, OBJPROP_STATE, false);
      return;
   }
}
//+------------------------------------------------------------------+
