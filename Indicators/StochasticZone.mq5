//+------------------------------------------------------------------+
//|                                              StochasticZone.mq5 |
//| ver 1.70                                                         |
//|                                                                  |
//| ストキャスティクス2本（短期9,3,3 / 長期60,3,3）をサブチャートに  |
//| 重ねて表示し、長期60,3,3の%Kを基準にサブチャートの背景色を       |
//| ゾーンごとに変更するインジケーター。                             |
//| ※ 背景色はサブウィンドウ全体を覆う矩形オブジェクトで実装。      |
//|                                                                  |
//| 背景色ロジック（長期60,3,3の%Kを基準）:                          |
//|   80〜100%: 黄色（通常）/ 赤（%K < %D の下降クロス時）          |
//|   20〜80% : 水色（%K上昇中）/ ピンク（%K下降中）                |
//|    0〜20% : 黄色（通常）/ 濃い青（%K > %D の上昇クロス時）      |
//+------------------------------------------------------------------+

#property version     "1.70"
#property indicator_separate_window
#property indicator_minimum  0.0
#property indicator_maximum  100.0
#property indicator_buffers  4
#property indicator_plots    4

#property indicator_label1  "Fast %K(9)"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDodgerBlue
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

#property indicator_label2  "Fast %D(9)"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrRed
#property indicator_style2  STYLE_SOLID
#property indicator_width2  2

#property indicator_label3  "Slow %K(60)"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrLime
#property indicator_style3  STYLE_SOLID
#property indicator_width3  2

#property indicator_label4  "Slow %D(60)"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrOrange
#property indicator_style4  STYLE_SOLID
#property indicator_width4  2

//--- 入力パラメータ
input group "=== 短期ストキャスティクス ==="
input int    InpFastKPeriod = 9;
input int    InpFastDPeriod = 3;
input int    InpFastSlowing = 3;

input group "=== 長期ストキャスティクス ==="
input int    InpSlowKPeriod = 60;
input int    InpSlowDPeriod = 3;
input int    InpSlowSlowing = 3;

input group "=== ゾーン閾値 ==="
input double InpLevelHigh   = 80.0;
input double InpLevelLow    = 20.0;

input group "=== 背景色設定 ==="
input color  InpColorYellow   = C'255,255,150';
input color  InpColorRed      = C'255,100,100';
input color  InpColorDarkBlue = C'100,149,237';
input color  InpColorCyan     = C'200,235,255';
input color  InpColorPink     = C'255,210,220';

//--- バッファ
double g_FastK[];
double g_FastD[];
double g_SlowK[];
double g_SlowD[];

//--- ハンドル
int g_hFast = INVALID_HANDLE;
int g_hSlow = INVALID_HANDLE;

//--- サブウィンドウ番号
int g_myWindow = -1;

//--- 背景矩形オブジェクト名
string g_rectName = "StoZone_BG";

//--- 直前の背景色（不要な再描画を避けるため）
color g_lastBgColor = clrNONE;

//+------------------------------------------------------------------+
//| 背景矩形を作成または更新する                                      |
//+------------------------------------------------------------------+
void SetBgRect(color clr)
{
   if(g_myWindow < 1) return;
   if(clr == g_lastBgColor) return;  // 色が変わっていなければスキップ
   g_lastBgColor = clr;

   // チャートの最初と最後の時刻を取得
   datetime t1 = (datetime)ChartGetInteger(0, CHART_FIRST_VISIBLE_BAR);
   // 表示範囲より広く取るため、十分な過去と未来の時刻を使う
   datetime timeFrom = (datetime)0;
   datetime timeTo   = (datetime)D'2099.12.31';

   if(ObjectFind(0, g_rectName) < 0)
   {
      // 矩形オブジェクトを新規作成
      ObjectCreate(0, g_rectName, OBJ_RECTANGLE, g_myWindow,
                   timeFrom, 105.0,   // 左上: 時刻, 値（最大値より上）
                   timeTo,   -5.0);   // 右下: 時刻, 値（最小値より下）
      ObjectSetInteger(0, g_rectName, OBJPROP_COLOR,     clr);
      ObjectSetInteger(0, g_rectName, OBJPROP_STYLE,     STYLE_SOLID);
      ObjectSetInteger(0, g_rectName, OBJPROP_WIDTH,     1);
      ObjectSetInteger(0, g_rectName, OBJPROP_FILL,      true);   // 塗りつぶし
      ObjectSetInteger(0, g_rectName, OBJPROP_BACK,      true);   // 背面に表示
      ObjectSetInteger(0, g_rectName, OBJPROP_SELECTABLE,false);
      ObjectSetInteger(0, g_rectName, OBJPROP_SELECTED,  false);
      ObjectSetInteger(0, g_rectName, OBJPROP_HIDDEN,    true);
   }
   else
   {
      // 色だけ更新
      ObjectSetInteger(0, g_rectName, OBJPROP_COLOR, clr);
   }
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0, g_FastK, INDICATOR_DATA);
   SetIndexBuffer(1, g_FastD, INDICATOR_DATA);
   SetIndexBuffer(2, g_SlowK, INDICATOR_DATA);
   SetIndexBuffer(3, g_SlowD, INDICATOR_DATA);

   PlotIndexSetDouble(0, PLOT_EMPTY_VALUE, 0.0);
   PlotIndexSetDouble(1, PLOT_EMPTY_VALUE, 0.0);
   PlotIndexSetDouble(2, PLOT_EMPTY_VALUE, 0.0);
   PlotIndexSetDouble(3, PLOT_EMPTY_VALUE, 0.0);

   g_hFast = iStochastic(_Symbol, _Period,
                          InpFastKPeriod, InpFastDPeriod, InpFastSlowing,
                          MODE_SMA, STO_LOWHIGH);
   g_hSlow = iStochastic(_Symbol, _Period,
                          InpSlowKPeriod, InpSlowDPeriod, InpSlowSlowing,
                          MODE_SMA, STO_LOWHIGH);

   if(g_hFast == INVALID_HANDLE || g_hSlow == INVALID_HANDLE)
   {
      Print("StochasticZone: ハンドル作成失敗 err=", GetLastError());
      return INIT_FAILED;
   }

   IndicatorSetInteger(INDICATOR_LEVELS, 2);
   IndicatorSetDouble(INDICATOR_LEVELVALUE,  0, InpLevelHigh);
   IndicatorSetDouble(INDICATOR_LEVELVALUE,  1, InpLevelLow);
   IndicatorSetInteger(INDICATOR_LEVELCOLOR, 0, clrGray);
   IndicatorSetInteger(INDICATOR_LEVELCOLOR, 1, clrGray);
   IndicatorSetInteger(INDICATOR_LEVELSTYLE, 0, STYLE_DASH);
   IndicatorSetInteger(INDICATOR_LEVELSTYLE, 1, STYLE_DASH);

   g_myWindow    = -1;
   g_lastBgColor = clrNONE;

   // 既存の矩形オブジェクトを削除（再初期化時のクリーンアップ）
   ObjectDelete(0, g_rectName);

   Print("StochasticZone v1.70: 初期化完了 hFast=", g_hFast, " hSlow=", g_hSlow);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_hFast != INVALID_HANDLE) { IndicatorRelease(g_hFast); g_hFast = INVALID_HANDLE; }
   if(g_hSlow != INVALID_HANDLE) { IndicatorRelease(g_hSlow); g_hSlow = INVALID_HANDLE; }
   ObjectDelete(0, g_rectName);
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   int minBars = InpSlowKPeriod + InpSlowSlowing + InpSlowDPeriod + 10;
   if(rates_total < minBars) return 0;

   int limit = (prev_calculated == 0) ? rates_total - minBars : rates_total - prev_calculated + 1;
   if(limit <= 0) limit = 1;

   double fk[], fd[], sk[], sd[];
   ArraySetAsSeries(fk, true);
   ArraySetAsSeries(fd, true);
   ArraySetAsSeries(sk, true);
   ArraySetAsSeries(sd, true);

   int c1 = CopyBuffer(g_hFast, 0, 0, limit, fk);
   int c2 = CopyBuffer(g_hFast, 1, 0, limit, fd);
   int c3 = CopyBuffer(g_hSlow, 0, 0, limit, sk);
   int c4 = CopyBuffer(g_hSlow, 1, 0, limit, sd);

   if(c1 <= 0 || c2 <= 0 || c3 <= 0 || c4 <= 0)
      return prev_calculated;

   int writeCount = MathMin(MathMin(c1, c2), MathMin(c3, c4));
   for(int i = 0; i < writeCount; i++)
   {
      int idx = rates_total - 1 - i;
      if(idx < 0) break;
      g_FastK[idx] = fk[i];
      g_FastD[idx] = fd[i];
      g_SlowK[idx] = sk[i];
      g_SlowD[idx] = sd[i];
   }

   // 背景色の決定
   double curSK  = sk[0];
   double curSD  = sd[0];
   double prevSK = (writeCount >= 2) ? sk[1] : sk[0];
   color  bgColor = GetBgColor(curSK, curSD, prevSK);

   // サブウィンドウ番号を取得（未取得の場合のみ検索）
   if(g_myWindow < 1)
   {
      int totalWin = (int)ChartGetInteger(0, CHART_WINDOWS_TOTAL);
      for(int w = 1; w < totalWin; w++)
      {
         int cnt = ChartIndicatorsTotal(0, w);
         for(int n = 0; n < cnt; n++)
         {
            string nm = ChartIndicatorName(0, w, n);
            if(StringFind(nm, "StochasticZone") >= 0)
            {
               g_myWindow = w;
               Print("StochasticZone: サブウィンドウ=", g_myWindow, " name=", nm);
               break;
            }
         }
         if(g_myWindow >= 1) break;
      }
   }

   // 矩形オブジェクトで背景色を設定
   SetBgRect(bgColor);

   return rates_total;
}

//+------------------------------------------------------------------+
color GetBgColor(double sk, double sd, double prevSk)
{
   if(sk >= InpLevelHigh)
      return (sk < sd) ? InpColorRed : InpColorYellow;

   if(sk <= InpLevelLow)
      return (sk > sd) ? InpColorDarkBlue : InpColorYellow;

   if(sk > prevSk) return InpColorCyan;
   if(sk < prevSk) return InpColorPink;
   return (sk > sd) ? InpColorCyan : InpColorPink;
}

//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lp, const double &dp, const string &sp)
{
   if(id == CHARTEVENT_CHART_CHANGE)
   {
      g_myWindow    = -1;
      g_lastBgColor = clrNONE;
      ChartRedraw(0);
   }
}
//+------------------------------------------------------------------+
