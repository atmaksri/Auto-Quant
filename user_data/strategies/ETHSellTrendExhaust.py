"""
ETHSellTrendExhaust — sell when ETH uptrend loses structure

Paradigm: trend-following
Hypothesis: ETH trends are persistent but end with identifiable exhaustion:
            4h EMA cross rolls, Donchian high stops being refreshed, and
            volume fades. Strategy rides the trend (4h EMA20>EMA50 + 1d
            regime filter) and SELLS when price breaks below 1h SMA50 OR
            4h EMA20. The exit timing (immediate breakdown vs patient SMA
            ride) is the optimization variable — v0.4.1 found breakout
            paradigms prefer patient exits while MR prefers tight ones.
Parent: root
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHSellTrendExhaust(IStrategy):
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
        ("bull_2021",      "20210101-20211231"),
        ("winter_2022",    "20220101-20221231"),
        ("recovery_23_25", "20230101-20251231"),
        ("full_5y",        "20210101-20251231"),
    ]

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
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
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["donchian_high_48"] = dataframe["high"].rolling(48).max().shift(1)
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Enter on confirmed uptrend + breakout confirmation + volume
        prior_above = dataframe["close"].shift(1) > dataframe["donchian_high_48"].shift(1)
        dataframe.loc[
            (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["ema20_4h"] > dataframe["ema50_4h"])
            & (dataframe["ema200_slope_up_1d"] == 1)
            & (dataframe["close"] > dataframe["ema200_1d"])
            & (dataframe["close"] > dataframe["donchian_high_48"])
            & prior_above  # sustained breakout, not first poke
            & (dataframe["volume"] > 1.2 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # SELL when trend structure breaks — this is the optimization target
        # Start: patient SMA50 breakdown (lets winners ride, v0.4.0 finding
        # for breakouts). Tighter alternatives: close<ema20, rsi>75, etc.
        dataframe.loc[
            (dataframe["close"] < dataframe["sma50"])
            | (dataframe["rsi"] > 78),  # also sell into parabolic exhaustion
            "exit_long",
        ] = 1
        return dataframe
