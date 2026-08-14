"""
ETHBreakoutRSIExit — ETHVolBreakout fork: identical entries, RSI>75 exit

Paradigm: breakout (exit ablation of ETHVolBreakout)
Hypothesis: The run's core question is the OPTIMAL SELL POINT for ETH.
            ETHVolBreakout (robust +0.104) sells on close<SMA50 (patient
            breakdown). This fork keeps EVERYTHING identical — Donchian-24
            entry, 4h EMA50>200 regime gate, volume 1.3x, vol-target sizing
            — and changes ONLY the exit: sell into strength at RSI>75
            instead of waiting for trend breakdown. Clean single-variable
            ablation: does 'sell when overbought' beat 'sell when trend
            breaks' for the same trade set? (v0.1.0-style ROI-clip
            degeneracy watch: if Sharpe jumps while profit collapses,
            that's gaming — RSI>75 is a real market exit, not a
            variance-compressor, but track profit vs parent carefully.)
Parent: ETHVolBreakout (fork, r5)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHBreakoutRSIExit(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 100}
    stoploss = -0.99
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

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # IDENTICAL to ETHVolBreakout — entry side must not change
        dataframe["donchian_high_24"] = dataframe["high"].rolling(24).max().shift(1)
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # IDENTICAL to ETHVolBreakout r2 entry
        dataframe.loc[
            (dataframe["close"] > dataframe["donchian_high_24"])
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # THE ABLATION: sell into overbought strength instead of SMA50 break
        dataframe.loc[dataframe["rsi"] > 75, "exit_long"] = 1
        return dataframe

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
