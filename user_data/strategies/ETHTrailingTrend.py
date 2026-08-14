"""
ETHTrailingTrend — EMA-stack trend following with trailing-stop exit

Paradigm: trend-following (trailing-stop exit)
Hypothesis: The user's goal is the OPTIMAL SELL POINT for ETH. The two
            surviving seeds sell on indicator signals (SMA50 cross,
            RSI threshold). A third, structurally different sell
            mechanism is a trailing stop: let winners run, ratchet the
            stop up, exit when momentum actually reverses — no fixed
            target. Entry: 4h EMA50>EMA200 regime + 1h EMA20>EMA50
            stack + close above EMA20 + 1d slope (bull context).
            Exit: FreqTrade trailing_stop (offset 12%, ratchet 6%)
            — the sell point is defined by how far price retraces
            from peak, not by an indicator crossing. Directly tests
            'sell on retracement-from-peak' as the ETH exit rule.
            This is NOT mean-reversion (no dip-buying), NOT breakout
            (no Donchian), NOT momentum (no MACD) — pure trend
            structure + stop ratcheting.
Parent: root (new paradigm — third distinct sell mechanism)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHTrailingTrend(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 100}
    stoploss = -0.99

    # Trailing-stop exit — the sell mechanism under test.
    # Offset 12% above entry before trailing activates; ratchet 6%
    # from the peak. Winners ride, exits happen on real reversal.
    trailing_stop = True
    trailing_stop_positive = 0.06
    trailing_stop_positive_offset = 0.12
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 300

    pair_basket = ["ETH/USDT"]

    test_timeranges = [
        ("train_21_24", "20210101-20241231"),
        ("holdout_25",  "20250101-20251231"),
    ]

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = (
            dataframe["ema200"] > dataframe["ema200"].shift(7)
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Trend stack: 4h regime + 1h structure + bull context
        dataframe.loc[
            (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["close"] > dataframe["ema20"])
            & (dataframe["close"] > dataframe["ema200"])
            & (dataframe["ema200_slope_up_1d"] == 1),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit is handled by trailing_stop. Keep exit signal as a hard
        # structure-break safety net (close below 1h EMA50 = trend dead).
        dataframe.loc[dataframe["close"] < dataframe["ema50"], "exit_long"] = 1
        return dataframe
