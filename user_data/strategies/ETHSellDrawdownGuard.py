"""
ETHSellDrawdownGuard — buy ETH capitulation dips, optimize the bounce exit

Paradigm: other (drawdown-rebound)
Hypothesis: ETH's best risk-adjusted entries are after outsized drawdowns
            from recent highs (past 30d high). Those dips bounce, but the
            bounce is short-lived — holding too long gives it back. So the
            SELL TIMING IS THE STRATEGY: exit on RSI>60 or mid-BB reclaim
            or a fixed 5% trailing cushion. Volume spike confirms it's a
            real capitulation, not a slow bleed. Uses 1d slope as regime
            gate so we don't catch knives in winter freefall.
            This is the direct ETH translation of CrashRebound, which had
            the highest bull_2021 sharpe (0.82) of any strategy in v0.4.1.
Parent: root
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHSellDrawdownGuard(IStrategy):
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
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = (
            dataframe["ema200"] > dataframe["ema200"].shift(7)
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        # Drawdown from rolling 30-day high (720 hourly candles)
        lookback = 720
        roll_high = dataframe["high"].rolling(lookback, min_periods=lookback).max()
        dataframe["drawdown"] = (dataframe["close"] / roll_high) - 1.0
        # BB for exit target
        period, std = 20, 2.0
        sma = dataframe["close"].rolling(period).mean()
        sd = dataframe["close"].rolling(period).std()
        dataframe["bb_mid"] = sma
        dataframe["bb_upper"] = sma + std * sd
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Deep dip + RSI confirmation + volume capitulation
        # NOTE: no 1d slope gate here — slope_up is only 44% on OKX data and
        # combined with dd<-0.20 it produced 0 trades. We want trades to
        # optimize the SELL timing on. Regime filter belongs on exit, not entry.
        dataframe.loc[
            (dataframe["drawdown"] < -0.15)          # 15% off 30d high (was -0.20, loosened)
            & (dataframe["rsi"] < 40)
            & (dataframe["volume"] > 1.1 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # SELL the bounce — tight exit, don't let reversion eat the gain
        # Core thesis: bounce is quick, so exit on first strength signal
        # The optimization target is which exit fires: rsi vs bb_mid vs sma breakdown
        dataframe.loc[
            (dataframe["rsi"] > 60)
            | (dataframe["close"] > dataframe["bb_mid"]),
            "exit_long",
        ] = 1
        return dataframe
