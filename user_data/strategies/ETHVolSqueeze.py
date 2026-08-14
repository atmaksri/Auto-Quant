"""
ETHVolSqueeze — Bollinger-Band width squeeze → expansion breakout (ETH)

Paradigm: volatility (squeeze/expansion)
Hypothesis: ETH ranges compress before big moves. BB width (20,2) in the
            bottom X% of its own 1y history = squeeze; expansion fires when
            BB width expands AND close breaks above the squeeze-range high
            (Donchian of the squeeze window). Sell: BB-upper touch OR
            close<SMA50. This is a THIRD distinct paradigm for the run —
            not mean-reversion, not Donchian-breakout (entry is
            volatility-state-driven, not price-level-driven), not momentum.
            It answers: does the 'optimal sell point' for ETH depend on the
            volatility regime it entered in? Uses 1d EMA200 slope as bull
            regime gate (second gold filter from v0.4.1).
Parent: root (new paradigm — volatility squeeze/expansion)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHVolSqueeze(IStrategy):
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

    startup_candle_count: int = 400

    pair_basket = ["ETH/USDT"]

    test_timeranges = [
        ("train_21_24", "20210101-20241231"),
        ("holdout_25",  "20250101-20251231"),
    ]

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = (
            dataframe["ema200"] > dataframe["ema200"].shift(7)
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        period, std = 20, 2.0
        sma = dataframe["close"].rolling(period).mean()
        sd = dataframe["close"].rolling(period).std()
        dataframe["bb_upper"] = sma + std * sd
        dataframe["bb_lower"] = sma - std * sd
        dataframe["bb_mid"] = sma
        # BB width normalized — squeeze = width in bottom 20% of last 365d
        dataframe["bb_width"] = (dataframe["bb_upper"] - dataframe["bb_lower"]) / sma
        # Percentile of CURRENT width within trailing 365d window
        # (r8 fix: compare w[-1] against window, not full series)
        dataframe["bb_width_pctile"] = dataframe["bb_width"].rolling(365).apply(
            lambda w: (w[-1] < w).mean(), raw=True
        )
        # Squeeze-range high: Donchian of the last 60 bars while squeezed
        dataframe["donchian_high_60"] = dataframe["high"].rolling(60).max().shift(1)
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r9: squeeze pctile <0.20→<0.35 and break window 120→60 bars.
        # r8 had 6+2 trades — too strict, no sample. Loosen to get
        # tradable count while keeping volatility-state entry.
        dataframe.loc[
            (dataframe["bb_width_pctile"] < 0.35)
            & (dataframe["close"] > dataframe["donchian_high_60"])
            & (dataframe["close"] > dataframe["bb_mid"])
            & (dataframe["ema200_slope_up_1d"] == 1)
            & (dataframe["rsi"] < 70),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Sell: BB-upper touch (expansion target) OR SMA50 breakdown
        dataframe.loc[
            (dataframe["close"] > dataframe["bb_upper"])
            | (dataframe["close"] < dataframe["sma50"]),
            "exit_long",
        ] = 1
        return dataframe
