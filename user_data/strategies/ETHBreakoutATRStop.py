"""
ETHBreakoutATRStop — ETHVolBreakout fork: identical, + ATR-scaled hard stop

Paradigm: breakout (stoploss ablation of ETHVolBreakout)
Hypothesis: ETHVolBreakout (robust +0.197) sells on SMA50 breakdown with
            stoploss=-0.99 (effectively no hard stop — the SMA50 exit IS
            the risk control). This fork adds a volatility-adaptive hard
            stop via custom_stoploss: -3×ATR(14,4h) from entry. In high
            vol the stop is wider (respects noise), in low vol tighter
            (cuts losers fast). Clean single-variable ablation: does a
            vol-scaled stop improve the Pareto point vs pure SMA50 exit?
            Watch Goodhart: if Sharpe rises but profit collapses, the stop
            is compressing return variance, not finding edge.
Parent: ETHVolBreakout (fork, r11)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHBreakoutATRStop(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 100}
    stoploss = -0.99  # fallback; custom_stoploss below overrides
    trailing_stop = False
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 250

    pair_basket = ["ETH/USDT"]

    test_timeranges = [
        ("train_21_24", "20210101-20241231"),
        ("holdout_25",  "20250101-20251231"),
    ]

    # ATR-stop: distance in ATR multiples from entry
    atr_stop_mult = 3.0

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # IDENTICAL to ETHVolBreakout r8 (Donchian-48)
        dataframe["donchian_high_48"] = dataframe["high"].rolling(48).max().shift(1)
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # IDENTICAL to ETHVolBreakout r8 entry
        dataframe.loc[
            (dataframe["close"] > dataframe["donchian_high_48"])
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # IDENTICAL to parent — SMA50 breakdown
        dataframe.loc[dataframe["close"] < dataframe["sma50"], "exit_long"] = 1
        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        # Vol-scaled hard stop: -3×ATR(4h) from entry. If trade already in
        # profit beyond the stop distance, return the fallback (don't stop
        # out winners early — SMA50 exit handles those).
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "atr_4h" not in df.columns:
            return self.stoploss
        atr = float(df["atr_4h"].iloc[-1])
        entry = float(trade.open_rate)
        if atr <= 0 or entry <= 0:
            return self.stoploss
        stop_pct = -(self.atr_stop_mult * atr) / entry
        # Never tighter than the fallback; never stop out a winner that has
        # already moved past the SMA50-exit zone (SMA50 exit is primary)
        return max(stop_pct, self.stoploss)

    def custom_stake_amount(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_stake: float,
        min_stake,
        max_stake: float,
        leverage: float,
        entry_tag: str,
        side: str,
        **kwargs,
    ) -> float:
        # IDENTICAL to ETHVolBreakout r2 (vol_target 0.008)
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "atr_pct_4h" not in df.columns:
            return proposed_stake
        atr_pct = df["atr_pct_4h"].iloc[-1]
        if atr_pct != atr_pct or atr_pct <= 0:
            return proposed_stake
        vol_target = 0.008
        scale = min(1.0, vol_target / atr_pct)
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
