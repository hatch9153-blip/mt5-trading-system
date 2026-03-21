//+------------------------------------------------------------------+
//|                                                      StoTest.mq5 |
//| 動作確認用：ストキャスティクス%Kを1本だけ表示するテスト         |
//+------------------------------------------------------------------+
#property version     "1.00"
#property indicator_separate_window
#property indicator_minimum  0.0
#property indicator_maximum  100.0
#property indicator_buffers  1
#property indicator_plots    1

#property indicator_label1  "SlowK(60)"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrLime
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

double g_SlowK[];
int    g_hSlow = INVALID_HANDLE;

int OnInit()
{
   SetIndexBuffer(0, g_SlowK, INDICATOR_DATA);
   PlotIndexSetDouble(0, PLOT_EMPTY_VALUE, 0.0);

   g_hSlow = iStochastic(_Symbol, _Period, 60, 3, 3, MODE_SMA, STO_LOWHIGH);
   if(g_hSlow == INVALID_HANDLE)
   {
      Print("ハンドル作成失敗: ", GetLastError());
      return INIT_FAILED;
   }
   Print("StoTest: ハンドル作成成功 handle=", g_hSlow);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_hSlow != INVALID_HANDLE) IndicatorRelease(g_hSlow);
}

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
   if(rates_total < 70) return 0;

   int limit = (prev_calculated == 0) ? rates_total : rates_total - prev_calculated + 1;
   if(limit <= 0) limit = 1;

   double sk[];
   ArraySetAsSeries(sk, true);

   int copied = CopyBuffer(g_hSlow, 0, 0, limit, sk);
   Print("StoTest OnCalculate: rates_total=", rates_total,
         " limit=", limit, " copied=", copied,
         " sk[0]=", (copied > 0 ? sk[0] : -1));

   if(copied <= 0) return prev_calculated;

   for(int i = 0; i < copied; i++)
   {
      int idx = rates_total - 1 - i;
      if(idx < 0) break;
      g_SlowK[idx] = sk[i];
   }

   return rates_total;
}
//+------------------------------------------------------------------+
