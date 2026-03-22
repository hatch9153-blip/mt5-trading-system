//+------------------------------------------------------------------+
//|                                               LotManager.mq5     |
//|                          MT5 Lot Management & Grid Order EA       |
//|                                         Version 1.0               |
//+------------------------------------------------------------------+
#property copyright "MT5 Trading System"
#property link      "https://github.com/hatch9153-blip/mt5-trading-system"
#property version   "1.00"
#property description "Lot management EA with average price display, position counter, and GUI-based grid order placement."

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\OrderInfo.mqh>

//--- Input Parameters
input double InpBaseLot        = 0.1;    // Base lot size per entry
input double InpBalancePer1000 = 0.1;    // Lot per 1000 balance (e.g. 0.1 lot per 1000)
input int    InpSLOffsetDollar = 5;      // SL offset from swing high/low ($)
input color  InpAvgBuyColor    = clrDodgerBlue;   // Average Buy price line color
input color  InpAvgSellColor   = clrOrangeRed;    // Average Sell price line color
input int    InpPanelX         = 10;     // Panel X position
input int    InpPanelY         = 30;     // Panel Y position

//--- Global Objects
CTrade         trade;
CPositionInfo  posInfo;
COrderInfo     orderInfo;

//--- Panel constants
#define PANEL_WIDTH   320
#define PANEL_HEIGHT  580
#define PANEL_NAME    "LM_Panel"
#define MAX_ZONES     5

//--- Zone structure
struct ZoneInfo
{
   double priceHigh;
   double priceLow;
   int    splits;
   double sl;
   double tp;
   bool   active;
};

//--- Global state
ZoneInfo  g_zones[MAX_ZONES];
int       g_zoneCount       = 1;
double    g_globalSL        = 0.0;
double    g_globalTP        = 0.0;
int       g_slMode          = 0;    // 0=Global, 1=PerOrder, 2=PerZone
bool      g_autoSL          = false;
string    g_symbol          = "";
double    g_tickValue       = 0.0;
double    g_tickSize        = 0.0;
double    g_pointValue      = 0.0;
int       g_digits          = 0;
bool      g_panelVisible    = true;

// Input field edit states (reserved for future use)
bool      g_editingField    = false;

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit()
{
   g_symbol     = Symbol();
   g_tickValue  = SymbolInfoDouble(g_symbol, SYMBOL_TRADE_TICK_VALUE);
   g_tickSize   = SymbolInfoDouble(g_symbol, SYMBOL_TRADE_TICK_SIZE);
   g_pointValue = SymbolInfoDouble(g_symbol, SYMBOL_POINT);
   g_digits     = (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS);

   // Initialize zones with defaults
   for(int i = 0; i < MAX_ZONES; i++)
   {
      g_zones[i].priceHigh = 0.0;
      g_zones[i].priceLow  = 0.0;
      g_zones[i].splits    = 3;
      g_zones[i].sl        = 0.0;
      g_zones[i].tp        = 0.0;
      g_zones[i].active    = (i == 0);
   }

   trade.SetExpertMagicNumber(202601);
   trade.SetDeviationInPoints(30);

   BuildPanel();
   UpdateAveragePriceLines();
   UpdatePanelInfo();

   ChartSetInteger(0, CHART_EVENT_MOUSE_MOVE, true);
   EventSetTimer(1);

   Print("LotManager v1.0 initialized on ", g_symbol);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteAllObjects();
   Print("LotManager deinitialized.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   UpdateAveragePriceLines();
   UpdatePanelInfo();
}

//+------------------------------------------------------------------+
//| Timer function - periodic refresh                                 |
//+------------------------------------------------------------------+
void OnTimer()
{
   UpdateAveragePriceLines();
   UpdatePanelInfo();
}

//+------------------------------------------------------------------+
//| Chart event handler                                               |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_OBJECT_CLICK)
   {
      HandleButtonClick(sparam);
   }
   if(id == CHARTEVENT_KEYDOWN)
   {
      // ESC key closes edit mode
      if(lparam == 27) g_editingField = false;
   }
}

//+------------------------------------------------------------------+
//| === FEATURE 1 & 2: Average Price Lines & Position Info ===        |
//+------------------------------------------------------------------+

//--- Calculate average entry price for Buy or Sell positions
double CalcAveragePrice(ENUM_POSITION_TYPE posType, double &totalLots, int &posCount)
{
   double totalVolume = 0.0;
   double weightedSum = 0.0;
   posCount = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(posInfo.SelectByIndex(i))
      {
         if(posInfo.Symbol() == g_symbol && posInfo.PositionType() == posType)
         {
            double vol   = posInfo.Volume();
            double price = posInfo.PriceOpen();
            weightedSum += price * vol;
            totalVolume += vol;
            posCount++;
         }
      }
   }

   totalLots = totalVolume;
   if(totalVolume > 0.0)
      return(weightedSum / totalVolume);
   return(0.0);
}

//--- Draw or update average price horizontal line
void DrawAverageLine(string name, double price, color clr, string label)
{
   if(price <= 0.0)
   {
      ObjectDelete(0, name);
      return;
   }

   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
      ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetString(0, name, OBJPROP_TOOLTIP, label);
   }
   else
   {
      ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   }

   // Label near the line
   string lblName = name + "_lbl";
   if(ObjectFind(0, lblName) < 0)
      ObjectCreate(0, lblName, OBJ_TEXT, 0, TimeCurrent(), price);

   ObjectSetDouble(0, lblName, OBJPROP_PRICE, price);
   ObjectSetInteger(0, lblName, OBJPROP_TIME, iTime(g_symbol, PERIOD_CURRENT, 3));
   ObjectSetString(0, lblName, OBJPROP_TEXT, label + ": " + DoubleToString(price, g_digits));
   ObjectSetInteger(0, lblName, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, lblName, OBJPROP_FONTSIZE, 9);
}

//--- Update both Buy and Sell average price lines
void UpdateAveragePriceLines()
{
   double buyLots = 0.0, sellLots = 0.0;
   int    buyCnt  = 0,   sellCnt  = 0;

   double avgBuy  = CalcAveragePrice(POSITION_TYPE_BUY,  buyLots,  buyCnt);
   double avgSell = CalcAveragePrice(POSITION_TYPE_SELL, sellLots, sellCnt);

   DrawAverageLine("LM_AvgBuy",  avgBuy,  InpAvgBuyColor,  "Avg Buy");
   DrawAverageLine("LM_AvgSell", avgSell, InpAvgSellColor, "Avg Sell");
}

//--- Calculate max allowed lots based on balance
double CalcMaxAllowedLots()
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   return MathFloor((balance / 1000.0) * InpBalancePer1000 * 10.0) / 10.0;
}

//--- Calculate current total lots held for this symbol
double CalcCurrentLots()
{
   double total = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(posInfo.SelectByIndex(i))
      {
         if(posInfo.Symbol() == g_symbol)
            total += posInfo.Volume();
      }
   }
   return total;
}

//+------------------------------------------------------------------+
//| === FEATURE 3: Swing High/Low Detection for Auto SL ===           |
//+------------------------------------------------------------------+

//--- Find the most recent swing high (highest high in recent bars, fractal-like)
double FindSwingHigh(int lookback)
{
   double highest = -1.0;
   for(int i = 1; i <= lookback; i++)
   {
      double h = iHigh(g_symbol, PERIOD_CURRENT, i);
      if(h > highest)
         highest = h;
   }
   return highest;
}

//--- Find the most recent swing low
double FindSwingLow(int lookback)
{
   double lowest = DBL_MAX;
   for(int i = 1; i <= lookback; i++)
   {
      double l = iLow(g_symbol, PERIOD_CURRENT, i);
      if(l < lowest)
         lowest = l;
   }
   return lowest;
}

//--- Convert dollar offset to price offset for GOLD
double DollarToPrice(double dollars)
{
   // For XAUUSD: 1 lot = 100oz, tick value per 0.01 move = tickValue
   // price_offset = dollars / (lots * contract_size / tickSize * tickValue)
   // Simplified: for 0.1 lot XAUUSD, $1 ≈ 1 point (0.01)
   // We use: priceOffset = dollars * tickSize / tickValue * (1/InpBaseLot)
   if(g_tickValue <= 0.0 || InpBaseLot <= 0.0) return dollars * 0.01;
   double pricePerDollar = g_tickSize / (g_tickValue * InpBaseLot);
   return dollars * pricePerDollar;
}

//--- Auto-calculate SL for Buy (below swing low) or Sell (above swing high)
double CalcAutoSL(bool isBuy, int lookback = 100)
{
   double offset = DollarToPrice((double)InpSLOffsetDollar);
   if(isBuy)
   {
      double swingLow = FindSwingLow(lookback);
      return NormalizeDouble(swingLow - offset, g_digits);
   }
   else
   {
      double swingHigh = FindSwingHigh(lookback);
      return NormalizeDouble(swingHigh + offset, g_digits);
   }
}

//+------------------------------------------------------------------+
//| === FEATURE 3: Grid Order Placement ===                           |
//+------------------------------------------------------------------+

//--- Calculate expected P/L for a set of orders
void CalcExpectedPL(double &totalRisk, double &totalReward)
{
   totalRisk   = 0.0;
   totalReward = 0.0;

   for(int z = 0; z < g_zoneCount; z++)
   {
      if(!g_zones[z].active) continue;
      if(g_zones[z].priceHigh <= 0.0 || g_zones[z].priceLow <= 0.0) continue;
      if(g_zones[z].splits <= 0) continue;

      double range   = MathAbs(g_zones[z].priceHigh - g_zones[z].priceLow);
      double step    = (g_zones[z].splits > 1) ? range / (g_zones[z].splits - 1) : 0;
      double sl      = (g_slMode == 2) ? g_zones[z].sl : g_globalSL;
      double tp      = (g_slMode == 2) ? g_zones[z].tp : g_globalTP;

      for(int s = 0; s < g_zones[z].splits; s++)
      {
         double entryPrice = g_zones[z].priceHigh - step * s;
         bool   isBuy      = (g_zones[z].priceHigh > g_zones[z].priceLow);

         // Risk per order
         if(sl > 0.0)
         {
            double slDist = MathAbs(entryPrice - sl);
            double risk   = slDist / g_tickSize * g_tickValue * InpBaseLot;
            totalRisk    += risk;
         }
         // Reward per order
         if(tp > 0.0)
         {
            double tpDist  = MathAbs(tp - entryPrice);
            double reward  = tpDist / g_tickSize * g_tickValue * InpBaseLot;
            totalReward   += reward;
         }
      }
   }
}

//--- Place grid orders for all active zones
void PlaceGridOrders()
{
   int totalPlaced = 0;

   for(int z = 0; z < g_zoneCount; z++)
   {
      if(!g_zones[z].active) continue;
      if(g_zones[z].priceHigh <= 0.0 || g_zones[z].priceLow <= 0.0)
      {
         Print("Zone ", z+1, ": price range not set, skipping.");
         continue;
      }
      if(g_zones[z].splits <= 0) continue;

      double high   = g_zones[z].priceHigh;
      double low    = g_zones[z].priceLow;
      bool   isBuy  = (high >= low);
      double range  = MathAbs(high - low);
      double step   = (g_zones[z].splits > 1) ? range / (g_zones[z].splits - 1) : 0;

      double sl = (g_slMode == 2) ? g_zones[z].sl : g_globalSL;
      double tp = (g_slMode == 2) ? g_zones[z].tp : g_globalTP;

      // Auto SL if enabled and not set
      if(g_autoSL && sl == 0.0)
         sl = CalcAutoSL(isBuy);

      for(int s = 0; s < g_zones[z].splits; s++)
      {
         double price = NormalizeDouble(high - step * s, g_digits);
         double slNorm = NormalizeDouble(sl, g_digits);
         double tpNorm = NormalizeDouble(tp, g_digits);

         bool result = false;
         if(isBuy)
         {
            double ask = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
            if(price < ask)
               result = trade.BuyLimit(InpBaseLot, price, g_symbol, slNorm, tpNorm, ORDER_TIME_GTC, 0, "LM_Z" + IntegerToString(z+1));
            else
               result = trade.BuyStop(InpBaseLot, price, g_symbol, slNorm, tpNorm, ORDER_TIME_GTC, 0, "LM_Z" + IntegerToString(z+1));
         }
         else
         {
            double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
            if(price > bid)
               result = trade.SellLimit(InpBaseLot, price, g_symbol, slNorm, tpNorm, ORDER_TIME_GTC, 0, "LM_Z" + IntegerToString(z+1));
            else
               result = trade.SellStop(InpBaseLot, price, g_symbol, slNorm, tpNorm, ORDER_TIME_GTC, 0, "LM_Z" + IntegerToString(z+1));
         }

         if(result)
            totalPlaced++;
         else
            Print("Order placement failed at ", price, " | Error: ", GetLastError());
      }
   }

   Print("LotManager: Placed ", totalPlaced, " orders.");
   UpdatePanelInfo();
}

//--- Cancel all pending orders placed by this EA for this symbol
void CancelAllGridOrders()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(orderInfo.SelectByIndex(i))
      {
         if(orderInfo.Symbol() == g_symbol && orderInfo.Magic() == 202601)
            trade.OrderDelete(orderInfo.Ticket());
      }
   }
   Print("LotManager: All grid orders cancelled.");
}

//+------------------------------------------------------------------+
//| === GUI PANEL CONSTRUCTION ===                                    |
//+------------------------------------------------------------------+

void DeleteAllObjects()
{
   ObjectsDeleteAll(0, "LM_");
}

//--- Create a rectangle label (background box)
void CreateRect(string name, int x, int y, int w, int h, color bgColor, int corner = CORNER_LEFT_UPPER)
{
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,  y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE,      w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE,      h);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR,    bgColor);
   ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clrGray);
   ObjectSetInteger(0, name, OBJPROP_CORNER,     corner);
   ObjectSetInteger(0, name, OBJPROP_BACK,       false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
}

//--- Create a text label
void CreateLabel(string name, int x, int y, string text, color clr, int fontSize = 9, int corner = CORNER_LEFT_UPPER)
{
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,  y);
   ObjectSetString(0, name,  OBJPROP_TEXT,       text);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   fontSize);
   ObjectSetInteger(0, name, OBJPROP_CORNER,     corner);
   ObjectSetInteger(0, name, OBJPROP_BACK,       false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
}

//--- Create a button
void CreateButton(string name, int x, int y, int w, int h, string text, color bgColor, color textColor, int corner = CORNER_LEFT_UPPER)
{
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,  y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE,      w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE,      h);
   ObjectSetString(0, name,  OBJPROP_TEXT,       text);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR,    bgColor);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      textColor);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   9);
   ObjectSetInteger(0, name, OBJPROP_CORNER,     corner);
   ObjectSetInteger(0, name, OBJPROP_BACK,       false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
}

//--- Create an edit field (using OBJ_EDIT)
void CreateEdit(string name, int x, int y, int w, int h, string text, int corner = CORNER_LEFT_UPPER)
{
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_EDIT, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,  y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE,      w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE,      h);
   ObjectSetString(0, name,  OBJPROP_TEXT,       text);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR,    clrWhiteSmoke);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clrBlack);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   9);
   ObjectSetInteger(0, name, OBJPROP_CORNER,     corner);
   ObjectSetInteger(0, name, OBJPROP_BACK,       false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_READONLY,   false);
}

//--- Build the full panel
void BuildPanel()
{
   int x  = InpPanelX;
   int y  = InpPanelY;
   int w  = PANEL_WIDTH;
   int lh = 20;  // line height
   int py = y;

   // === Main background ===
   CreateRect("LM_BG", x, py, w, PANEL_HEIGHT, C'30,30,40');
   py += 5;

   // === Title ===
   CreateLabel("LM_Title", x + 10, py, "=== LotManager v1.0 ===", clrGold, 10);
   py += 22;

   // === Section: Account Info ===
   CreateLabel("LM_SecInfo", x + 10, py, "-- Account & Position Info --", clrSilver, 9);
   py += lh;
   CreateLabel("LM_LblBalance",  x + 10, py,       "Balance:",        clrWhite, 9);
   CreateLabel("LM_ValBalance",  x + 90, py,       "---",             clrYellow, 9);
   py += lh;
   CreateLabel("LM_LblMaxLot",   x + 10, py,       "Max Lots:",       clrWhite, 9);
   CreateLabel("LM_ValMaxLot",   x + 90, py,       "---",             clrYellow, 9);
   py += lh;
   CreateLabel("LM_LblCurLot",   x + 10, py,       "Current Lots:",   clrWhite, 9);
   CreateLabel("LM_ValCurLot",   x + 90, py,       "---",             clrCyan, 9);
   py += lh;
   CreateLabel("LM_LblAddLot",   x + 10, py,       "Addable Lots:",   clrWhite, 9);
   CreateLabel("LM_ValAddLot",   x + 90, py,       "---",             clrLimeGreen, 9);
   py += lh;
   CreateLabel("LM_LblPosCnt",   x + 10, py,       "Positions:",      clrWhite, 9);
   CreateLabel("LM_ValPosCnt",   x + 90, py,       "Buy:0  Sell:0",   clrCyan, 9);
   py += lh;
   CreateLabel("LM_LblAvgBuy",   x + 10, py,       "Avg Buy:",        clrDodgerBlue, 9);
   CreateLabel("LM_ValAvgBuy",   x + 90, py,       "---",             clrDodgerBlue, 9);
   py += lh;
   CreateLabel("LM_LblAvgSell",  x + 10, py,       "Avg Sell:",       clrOrangeRed, 9);
   CreateLabel("LM_ValAvgSell",  x + 90, py,       "---",             clrOrangeRed, 9);
   py += lh + 5;

   // === Section: Zone Count ===
   CreateLabel("LM_SecZone", x + 10, py, "-- Zone Settings --", clrSilver, 9);
   py += lh;
   CreateLabel("LM_LblZoneCnt", x + 10, py, "Active Zones:", clrWhite, 9);
   CreateButton("LM_BtnZ1", x + 100, py, 22, 18, "1", (g_zoneCount==1?clrGold:C'50,50,70'), clrWhite);
   CreateButton("LM_BtnZ2", x + 124, py, 22, 18, "2", (g_zoneCount==2?clrGold:C'50,50,70'), clrWhite);
   CreateButton("LM_BtnZ3", x + 148, py, 22, 18, "3", (g_zoneCount==3?clrGold:C'50,50,70'), clrWhite);
   CreateButton("LM_BtnZ4", x + 172, py, 22, 18, "4", (g_zoneCount==4?clrGold:C'50,50,70'), clrWhite);
   CreateButton("LM_BtnZ5", x + 196, py, 22, 18, "5", (g_zoneCount==5?clrGold:C'50,50,70'), clrWhite);
   py += lh + 5;

   // === Zone Input Rows (up to 5 zones) ===
   for(int z = 0; z < MAX_ZONES; z++)
   {
      string zs = IntegerToString(z + 1);
      color  zc = (z < g_zoneCount) ? clrWhite : clrDimGray;
      // color ec = (z < g_zoneCount) ? clrWhiteSmoke : C'50,50,60'; // reserved for future edit field styling

      CreateLabel("LM_LblZ" + zs,    x + 10,  py, "Z" + zs + " High:", zc, 9);
      CreateEdit("LM_EditZH" + zs,   x + 65,  py, 75, 16,
                 (g_zones[z].priceHigh > 0 ? DoubleToString(g_zones[z].priceHigh, g_digits) : "0.00"));
      CreateLabel("LM_LblZL" + zs,   x + 145, py, "Low:", zc, 9);
      CreateEdit("LM_EditZL" + zs,   x + 170, py, 75, 16,
                 (g_zones[z].priceLow > 0 ? DoubleToString(g_zones[z].priceLow, g_digits) : "0.00"));
      py += lh;

      CreateLabel("LM_LblZS" + zs,   x + 10,  py, "   Splits:", zc, 9);
      CreateEdit("LM_EditZS" + zs,   x + 65,  py, 40, 16, IntegerToString(g_zones[z].splits));
      CreateLabel("LM_LblZTP" + zs,  x + 115, py, "TP:", zc, 9);
      CreateEdit("LM_EditZTP" + zs,  x + 135, py, 60, 16,
                 (g_zones[z].tp > 0 ? DoubleToString(g_zones[z].tp, g_digits) : "0.00"));
      CreateLabel("LM_LblZSL" + zs,  x + 200, py, "SL:", zc, 9);
      CreateEdit("LM_EditZSL" + zs,  x + 220, py, 60, 16,
                 (g_zones[z].sl > 0 ? DoubleToString(g_zones[z].sl, g_digits) : "0.00"));
      py += lh + 2;
   }

   // === Section: Global SL/TP ===
   CreateLabel("LM_SecSLTP", x + 10, py, "-- Global SL/TP --", clrSilver, 9);
   py += lh;
   CreateLabel("LM_LblGSL",  x + 10,  py, "Global SL:", clrWhite, 9);
   CreateEdit("LM_EditGSL",  x + 80,  py, 70, 16, "0.00");
   CreateLabel("LM_LblGTP",  x + 160, py, "Global TP:", clrWhite, 9);
   CreateEdit("LM_EditGTP",  x + 230, py, 70, 16, "0.00");
   py += lh;

   // SL Mode buttons
   CreateLabel("LM_LblSLMode", x + 10, py, "SL Mode:", clrWhite, 9);
   CreateButton("LM_BtnSLM0", x + 75,  py, 65, 18, "Global",   (g_slMode==0?clrGold:C'50,50,70'), clrWhite);
   CreateButton("LM_BtnSLM1", x + 143, py, 65, 18, "PerOrder", (g_slMode==1?clrGold:C'50,50,70'), clrWhite);
   CreateButton("LM_BtnSLM2", x + 211, py, 65, 18, "PerZone",  (g_slMode==2?clrGold:C'50,50,70'), clrWhite);
   py += lh;

   // Auto SL toggle
   CreateButton("LM_BtnAutoSL", x + 10, py, 140, 18,
                (g_autoSL ? "[ON] Auto SL (Swing)" : "[OFF] Auto SL (Swing)"),
                (g_autoSL ? clrDarkGreen : C'50,50,70'), clrWhite);
   py += lh + 5;

   // === Section: Expected P/L ===
   CreateLabel("LM_SecPL",    x + 10, py, "-- Expected P/L --", clrSilver, 9);
   py += lh;
   CreateLabel("LM_LblRisk",  x + 10, py, "Max Risk ($):",   clrWhite, 9);
   CreateLabel("LM_ValRisk",  x + 110, py, "---",            clrOrangeRed, 9);
   py += lh;
   CreateLabel("LM_LblReward",x + 10, py, "Max Reward ($):", clrWhite, 9);
   CreateLabel("LM_ValReward",x + 110, py, "---",            clrLimeGreen, 9);
   py += lh + 5;

   // === Action Buttons ===
   CreateButton("LM_BtnCalc",   x + 10,  py, 90, 22, "Calc P/L",     C'0,80,120',  clrWhite);
   CreateButton("LM_BtnPlace",  x + 110, py, 90, 22, "Place Orders", C'0,120,0',   clrWhite);
   CreateButton("LM_BtnCancel", x + 210, py, 90, 22, "Cancel All",   C'140,0,0',   clrWhite);
   py += 28;
   CreateButton("LM_BtnRefresh",x + 10,  py, 90, 22, "Refresh",      C'60,60,80',  clrWhite);
   CreateButton("LM_BtnRead",   x + 110, py, 90, 22, "Read Fields",  C'80,60,20',  clrWhite);

   ChartRedraw(0);
}

//--- Read all edit field values into g_zones and global SL/TP
void ReadPanelFields()
{
   for(int z = 0; z < MAX_ZONES; z++)
   {
      string zs = IntegerToString(z + 1);
      g_zones[z].priceHigh = StringToDouble(ObjectGetString(0, "LM_EditZH" + zs, OBJPROP_TEXT));
      g_zones[z].priceLow  = StringToDouble(ObjectGetString(0, "LM_EditZL" + zs, OBJPROP_TEXT));
      g_zones[z].splits    = (int)StringToInteger(ObjectGetString(0, "LM_EditZS" + zs, OBJPROP_TEXT));
      g_zones[z].tp        = StringToDouble(ObjectGetString(0, "LM_EditZTP" + zs, OBJPROP_TEXT));
      g_zones[z].sl        = StringToDouble(ObjectGetString(0, "LM_EditZSL" + zs, OBJPROP_TEXT));
      g_zones[z].active    = (z < g_zoneCount);
   }
   g_globalSL = StringToDouble(ObjectGetString(0, "LM_EditGSL", OBJPROP_TEXT));
   g_globalTP = StringToDouble(ObjectGetString(0, "LM_EditGTP", OBJPROP_TEXT));
}

//--- Update dynamic labels in the panel
void UpdatePanelInfo()
{
   double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
   double maxLots  = CalcMaxAllowedLots();
   double curLots  = CalcCurrentLots();
   double addLots  = MathMax(0.0, maxLots - curLots);
   int    addPosns = (InpBaseLot > 0) ? (int)MathFloor(addLots / InpBaseLot) : 0;

   double buyLots = 0.0, sellLots = 0.0;
   int    buyCnt  = 0,   sellCnt  = 0;
   double avgBuy  = CalcAveragePrice(POSITION_TYPE_BUY,  buyLots, buyCnt);
   double avgSell = CalcAveragePrice(POSITION_TYPE_SELL, sellLots, sellCnt);

   ObjectSetString(0, "LM_ValBalance", OBJPROP_TEXT, DoubleToString(balance, 2));
   ObjectSetString(0, "LM_ValMaxLot",  OBJPROP_TEXT, DoubleToString(maxLots, 2) + " lots");
   ObjectSetString(0, "LM_ValCurLot",  OBJPROP_TEXT, DoubleToString(curLots, 2) + " lots");
   ObjectSetString(0, "LM_ValAddLot",  OBJPROP_TEXT, DoubleToString(addLots, 2) + " lots (" + IntegerToString(addPosns) + " pos)");
   ObjectSetString(0, "LM_ValPosCnt",  OBJPROP_TEXT, "Buy:" + IntegerToString(buyCnt) + "  Sell:" + IntegerToString(sellCnt));
   ObjectSetString(0, "LM_ValAvgBuy",  OBJPROP_TEXT, (avgBuy  > 0 ? DoubleToString(avgBuy,  g_digits) : "---"));
   ObjectSetString(0, "LM_ValAvgSell", OBJPROP_TEXT, (avgSell > 0 ? DoubleToString(avgSell, g_digits) : "---"));

   ChartRedraw(0);
}

//--- Update expected P/L display
void UpdateExpectedPL()
{
   ReadPanelFields();
   double risk = 0.0, reward = 0.0;
   CalcExpectedPL(risk, reward);
   ObjectSetString(0, "LM_ValRisk",   OBJPROP_TEXT, DoubleToString(risk,   2));
   ObjectSetString(0, "LM_ValReward", OBJPROP_TEXT, DoubleToString(reward, 2));
   ChartRedraw(0);
}

//--- Rebuild zone count buttons highlighting
void RefreshZoneButtons()
{
   for(int i = 1; i <= MAX_ZONES; i++)
   {
      string name = "LM_BtnZ" + IntegerToString(i);
      ObjectSetInteger(0, name, OBJPROP_BGCOLOR, (i == g_zoneCount ? clrGold : C'50,50,70'));
   }
   ChartRedraw(0);
}

//--- Rebuild SL mode buttons highlighting
void RefreshSLModeButtons()
{
   ObjectSetInteger(0, "LM_BtnSLM0", OBJPROP_BGCOLOR, (g_slMode==0 ? clrGold : C'50,50,70'));
   ObjectSetInteger(0, "LM_BtnSLM1", OBJPROP_BGCOLOR, (g_slMode==1 ? clrGold : C'50,50,70'));
   ObjectSetInteger(0, "LM_BtnSLM2", OBJPROP_BGCOLOR, (g_slMode==2 ? clrGold : C'50,50,70'));
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Button click handler                                              |
//+------------------------------------------------------------------+
void HandleButtonClick(string name)
{
   // Zone count selection
   if(name == "LM_BtnZ1") { g_zoneCount = 1; RefreshZoneButtons(); return; }
   if(name == "LM_BtnZ2") { g_zoneCount = 2; RefreshZoneButtons(); return; }
   if(name == "LM_BtnZ3") { g_zoneCount = 3; RefreshZoneButtons(); return; }
   if(name == "LM_BtnZ4") { g_zoneCount = 4; RefreshZoneButtons(); return; }
   if(name == "LM_BtnZ5") { g_zoneCount = 5; RefreshZoneButtons(); return; }

   // SL mode selection
   if(name == "LM_BtnSLM0") { g_slMode = 0; RefreshSLModeButtons(); return; }
   if(name == "LM_BtnSLM1") { g_slMode = 1; RefreshSLModeButtons(); return; }
   if(name == "LM_BtnSLM2") { g_slMode = 2; RefreshSLModeButtons(); return; }

   // Auto SL toggle
   if(name == "LM_BtnAutoSL")
   {
      g_autoSL = !g_autoSL;
      ObjectSetString(0, "LM_BtnAutoSL", OBJPROP_TEXT,
                      (g_autoSL ? "[ON] Auto SL (Swing)" : "[OFF] Auto SL (Swing)"));
      ObjectSetInteger(0, "LM_BtnAutoSL", OBJPROP_BGCOLOR,
                       (g_autoSL ? clrDarkGreen : C'50,50,70'));
      // Reset button state
      ObjectSetInteger(0, name, OBJPROP_STATE, false);
      ChartRedraw(0);
      return;
   }

   // Calculate P/L
   if(name == "LM_BtnCalc")
   {
      UpdateExpectedPL();
      ObjectSetInteger(0, name, OBJPROP_STATE, false);
      return;
   }

   // Place orders
   if(name == "LM_BtnPlace")
   {
      ReadPanelFields();
      PlaceGridOrders();
      ObjectSetInteger(0, name, OBJPROP_STATE, false);
      return;
   }

   // Cancel all grid orders
   if(name == "LM_BtnCancel")
   {
      CancelAllGridOrders();
      ObjectSetInteger(0, name, OBJPROP_STATE, false);
      return;
   }

   // Refresh display
   if(name == "LM_BtnRefresh")
   {
      DeleteAllObjects();
      BuildPanel();
      UpdateAveragePriceLines();
      UpdatePanelInfo();
      ObjectSetInteger(0, name, OBJPROP_STATE, false);
      return;
   }

   // Read fields manually
   if(name == "LM_BtnRead")
   {
      ReadPanelFields();
      UpdateExpectedPL();
      ObjectSetInteger(0, name, OBJPROP_STATE, false);
      return;
   }
}
//+------------------------------------------------------------------+
