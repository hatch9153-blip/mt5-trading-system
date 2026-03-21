//+------------------------------------------------------------------+
//|                                              RiskManager.mq5     |
//|                         MT5 リスク管理EA v1.0                    |
//|  機能:                                                            |
//|   1. 時間帯フィルター（許可時間帯以外はエントリー警告）           |
//|   2. 1日の利益目標達成（+20%）でトレード終了                     |
//|   3. 連敗ストッパー（通常3連敗、NY時間1連敗でブロック）           |
//+------------------------------------------------------------------+
#property copyright "MT5 Trading System"
#property version   "1.00"
#property strict

//--- 入力パラメーター
input double InpDailyProfitTarget      = 20.0;  // 1日の利益目標（%）
input int    InpMaxLosses              = 3;     // 通常時間帯の連敗上限
input int    InpNYMaxLosses            = 1;     // NY時間帯の連敗上限
input bool   InpEnableTimeFilter       = true;  // 時間帯フィルター有効
input bool   InpEnableProfitTarget     = true;  // 利益目標終了有効
input bool   InpEnableStreakStopper    = true;  // 連敗ストッパー有効
input bool   InpAlertOnBlock           = true;  // ブロック時アラート

//--- グローバル変数
double g_startBalance    = 0.0;
double g_targetBalance   = 0.0;
int    g_consecutiveLosses = 0;
bool   g_blockedByProfit = false;
bool   g_blockedByStreak = false;
int    g_lastDay         = -1;
ulong  g_lastDealTicket  = 0;

//--- チャートオブジェクト名
string PREFIX = "RM_";

//+------------------------------------------------------------------+
//| EA初期化                                                          |
//+------------------------------------------------------------------+
int OnInit()
{
   // 開始残高を記録
   g_startBalance  = AccountInfoDouble(ACCOUNT_BALANCE);
   g_targetBalance = g_startBalance * (1.0 + InpDailyProfitTarget / 100.0);
   g_lastDay       = TimeDay(TimeCurrent());
   
   // 既存の決済履歴から連敗数を復元
   RestoreStreakFromHistory();
   
   // チャート表示を初期化
   UpdateChartDisplay();
   
   Print("RiskManager v1.0 初期化完了 | 開始残高: ", g_startBalance, 
         " | 目標残高: ", g_targetBalance);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| EA終了処理                                                        |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   // チャートオブジェクトを削除
   ObjectsDeleteAll(0, PREFIX);
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| ティック処理                                                      |
//+------------------------------------------------------------------+
void OnTick()
{
   // 日付変更チェック
   int currentDay = TimeDay(TimeCurrent());
   if(currentDay != g_lastDay)
   {
      ResetDailyState();
      g_lastDay = currentDay;
   }
   
   // 利益目標チェック
   if(InpEnableProfitTarget && !g_blockedByProfit)
   {
      double currentBalance = AccountInfoDouble(ACCOUNT_BALANCE);
      if(currentBalance >= g_targetBalance)
      {
         g_blockedByProfit = true;
         string msg = "✅ 本日の利益目標達成！新規エントリーをブロックしました。";
         Print(msg);
         if(InpAlertOnBlock) Alert(msg);
      }
   }
   
   // チャート表示更新
   UpdateChartDisplay();
}

//+------------------------------------------------------------------+
//| 取引イベント処理（連敗カウント更新）                              |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result)
{
   // 決済イベントのみ処理
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(trans.deal == 0 || trans.deal == g_lastDealTicket) return;
   
   // Dealの詳細を取得
   if(!HistoryDealSelect(trans.deal)) return;
   
   ENUM_DEAL_ENTRY dealEntry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(dealEntry != DEAL_ENTRY_OUT && dealEntry != DEAL_ENTRY_INOUT) return;
   
   double dealProfit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
   g_lastDealTicket  = trans.deal;
   
   // 連敗カウント更新
   if(!InpEnableStreakStopper || g_blockedByStreak) return;
   
   if(dealProfit < 0.0)
   {
      g_consecutiveLosses++;
      
      // 現在の時間帯に応じた上限を判定
      bool isNYTime = IsNYTime();
      int limit = isNYTime ? InpNYMaxLosses : InpMaxLosses;
      
      if(g_consecutiveLosses >= limit)
      {
         g_blockedByStreak = true;
         string timeLabel = isNYTime ? "NY時間" : "通常時間";
         string msg = StringFormat("⛔ 連敗ストッパー発動（%s: %d連敗）本日の新規エントリーをブロックしました。",
                                   timeLabel, g_consecutiveLosses);
         Print(msg);
         if(InpAlertOnBlock) Alert(msg);
      }
      else
      {
         Print(StringFormat("連敗カウント: %d / %d", g_consecutiveLosses, limit));
      }
   }
   else
   {
      // 勝利で連敗カウントリセット
      if(g_consecutiveLosses > 0)
         Print(StringFormat("連敗カウントリセット（%d連敗後の勝利）", g_consecutiveLosses));
      g_consecutiveLosses = 0;
   }
   
   UpdateChartDisplay();
}

//+------------------------------------------------------------------+
//| 現在時刻が許可時間帯かどうかを判定（JST基準）                    |
//+------------------------------------------------------------------+
bool IsAllowedTime()
{
   if(!InpEnableTimeFilter) return true;
   
   datetime serverTime = TimeCurrent();
   // サーバー時間をJSTに変換（UTC+9）
   // ※ブローカーのサーバー時間がUTCの場合。EET(UTC+2/+3)の場合は調整が必要
   // XMTradingのサーバーはEET(UTC+2/夏時間UTC+3)のため、JSTはUTC+9
   // サーバー時間オフセットを確認してください
   MqlDateTime dt;
   TimeToStruct(serverTime, dt);
   
   int serverOffsetHours = 2; // XMTradingのサーバーオフセット（冬時間UTC+2）
   // 夏時間（3月最終日曜〜10月最終日曜）はUTC+3に変更してください
   
   // JSTへの変換
   int jstHour = (dt.hour + 9 - serverOffsetHours + 24) % 24;
   int jstMin  = dt.min;
   int jstTime = jstHour * 100 + jstMin; // HHMM形式
   
   // 許可時間帯チェック
   if(jstTime >= 800  && jstTime < 900)  return true; // 08:00-09:00
   if(jstTime >= 1000 && jstTime < 1030) return true; // 10:00-10:30
   if(jstTime >= 1500 && jstTime < 1600) return true; // 15:00-16:00
   if(jstTime >= 2130 || jstTime < 0)    return true; // 21:30-00:00
   if(jstTime >= 0    && jstTime < 100)  return true; // 00:00-01:00（NY時間継続）
   
   return false;
}

//+------------------------------------------------------------------+
//| NY時間帯かどうかを判定（JST 21:30〜翌00:00）                    |
//+------------------------------------------------------------------+
bool IsNYTime()
{
   datetime serverTime = TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(serverTime, dt);
   
   int serverOffsetHours = 2;
   int jstHour = (dt.hour + 9 - serverOffsetHours + 24) % 24;
   int jstMin  = dt.min;
   int jstTime = jstHour * 100 + jstMin;
   
   if(jstTime >= 2130) return true;
   if(jstTime < 100)   return true;
   
   return false;
}

//+------------------------------------------------------------------+
//| 全ブロック状態の確認（チャート表示用）                           |
//+------------------------------------------------------------------+
bool IsBlocked()
{
   if(g_blockedByProfit) return true;
   if(g_blockedByStreak) return true;
   if(!IsAllowedTime())  return true;
   return false;
}

//+------------------------------------------------------------------+
//| 日次リセット処理                                                  |
//+------------------------------------------------------------------+
void ResetDailyState()
{
   g_startBalance      = AccountInfoDouble(ACCOUNT_BALANCE);
   g_targetBalance     = g_startBalance * (1.0 + InpDailyProfitTarget / 100.0);
   g_consecutiveLosses = 0;
   g_blockedByProfit   = false;
   g_blockedByStreak   = false;
   
   Print(StringFormat("日次リセット完了 | 新しい開始残高: %.2f | 目標残高: %.2f",
                      g_startBalance, g_targetBalance));
}

//+------------------------------------------------------------------+
//| 履歴から本日の連敗数を復元                                       |
//+------------------------------------------------------------------+
void RestoreStreakFromHistory()
{
   datetime todayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   
   if(!HistorySelect(todayStart, TimeCurrent())) return;
   
   int totalDeals = HistoryDealsTotal();
   int streak = 0;
   
   for(int i = totalDeals - 1; i >= 0; i--)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;
      
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT) continue;
      
      double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      if(profit < 0.0)
         streak++;
      else
         break;
   }
   
   g_consecutiveLosses = streak;
   
   // 連敗上限チェック
   if(InpEnableStreakStopper)
   {
      bool isNY = IsNYTime();
      int limit = isNY ? InpNYMaxLosses : InpMaxLosses;
      if(g_consecutiveLosses >= limit)
         g_blockedByStreak = true;
   }
   
   Print(StringFormat("履歴から連敗数を復元: %d連敗", g_consecutiveLosses));
}

//+------------------------------------------------------------------+
//| チャートステータスパネルを更新                                   |
//+------------------------------------------------------------------+
void UpdateChartDisplay()
{
   double currentBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   double profitPct = g_startBalance > 0 ?
                      (currentBalance - g_startBalance) / g_startBalance * 100.0 : 0.0;
   
   // 時間帯状態
   string timeStatus;
   color  timeColor;
   if(!InpEnableTimeFilter)
   {
      timeStatus = "フィルター無効";
      timeColor  = clrGray;
   }
   else if(IsAllowedTime())
   {
      string zone = IsNYTime() ? "NY時間" : "東京時間";
      timeStatus = "✅ エントリー許可 (" + zone + ")";
      timeColor  = clrLime;
   }
   else
   {
      timeStatus = "⛔ エントリー禁止時間帯";
      timeColor  = clrOrangeRed;
   }
   
   // 全体ブロック状態
   string blockStatus;
   color  blockColor;
   if(g_blockedByProfit)
   {
      blockStatus = "✅ 利益目標達成・本日終了";
      blockColor  = clrGold;
   }
   else if(g_blockedByStreak)
   {
      blockStatus = StringFormat("⛔ 連敗ストッパー発動（%d連敗）", g_consecutiveLosses);
      blockColor  = clrRed;
   }
   else if(!IsAllowedTime())
   {
      blockStatus = "⛔ 時間帯ブロック中";
      blockColor  = clrOrange;
   }
   else
   {
      blockStatus = "稼働中";
      blockColor  = clrLime;
   }
   
   // 連敗表示
   bool isNY = IsNYTime();
   int limit = isNY ? InpNYMaxLosses : InpMaxLosses;
   string streakStr = StringFormat("%d / %d (%s)", g_consecutiveLosses, limit,
                                   isNY ? "NY" : "通常");
   
   // ラベル描画
   DrawLabel(PREFIX + "Title",    "[ RiskManager v1.0 ]",
             10, 20, 14, clrWhite);
   DrawLabel(PREFIX + "Balance",  StringFormat("開始残高: %.2f", g_startBalance),
             10, 42, 11, clrSilver);
   DrawLabel(PREFIX + "Current",  StringFormat("現在残高: %.2f  (%.1f%%)", currentBalance, profitPct),
             10, 60, 11, profitPct >= 0 ? clrLime : clrRed);
   DrawLabel(PREFIX + "Target",   StringFormat("利益目標: %.2f  (+%.1f%%)", g_targetBalance, InpDailyProfitTarget),
             10, 78, 11, clrSilver);
   DrawLabel(PREFIX + "Streak",   StringFormat("連敗数:   %s", streakStr),
             10, 96, 11, g_consecutiveLosses > 0 ? clrOrange : clrSilver);
   DrawLabel(PREFIX + "Time",     StringFormat("時間帯:   %s", timeStatus),
             10, 114, 11, timeColor);
   DrawLabel(PREFIX + "Status",   StringFormat("本日状態: %s", blockStatus),
             10, 132, 12, blockColor);
   
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| テキストラベルを描画                                             |
//+------------------------------------------------------------------+
void DrawLabel(string name, string text, int x, int y, int fontSize, color clr)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, fontSize);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetString(0,  name, OBJPROP_TEXT, text);
   ObjectSetString(0,  name, OBJPROP_FONT, "MS Gothic");
}
//+------------------------------------------------------------------+
