"""
ETHMomentumTrend — 4h MACD momentum + ADX trend filter, ride with patient exit

Paradigm: trend-following (momentum)
Hypothesis: v0.4.1 found momentum caps at ~0.40 robust_sharpe even with the
            optimal filter stack (MomentumGoldFilters r25: "momentum 0.40
            cap is INTRINSIC"). That finding was on the 5-pair portfolio
            under 4-regime min-sharpe. This run tests whether the cap holds
            on ETH-only under a train/holdout split — a cleaner asset-level
            test of the momentum ceiling. Structure: 4h MACD histogram > 0
            AND 4h ADX > 25 (trend strength, not chop) AND 1d EMA200 slope
            up (regime gate). Exit: 4h MACD histogram flips < 0 OR close
            < 1h SMA50 (structure break). Patient exit — v0.4.0 found
            regime-mix prefers patient exits on momentum/breakout family,
            but v0.4.1 narrowed it to breakout-family; measuring it on
            pure momentum is the question. Equal-weight sizing (momentum
            has no natural conviction signal; v0.4.1 r24 removed volume
            filter from momentum — continuations don't spike volume).
Parent: root (new paradigm — not mean-reversion, not breakout)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHMomentumTrend(IStrategy):
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

    startup_candle_count: int = 300

    pair_basket = ["ETH/USDT"]

    test_timeranges = [
        ("train_21_24", "20210101-20241231"),
        ("holdout_25",  "20250101-20251231"),
    ]

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        macd_df = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd_df["macd"]
        dataframe["macd_signal"] = macd_df["macdsignal"]
        dataframe["macd_hist"] = macd_df["macdhist"]
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
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
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Momentum + trend strength + regime. NO volume filter —
        # v0.4.1 r24 finding: volume filter HURTS momentum/continuation.
        # NO close>donchian — this is momentum riding, not breakout.
        # r2: added 4h EMA50>EMA200 gate (v0.4.1 'second gold filter' —
        # flipped winter negative→positive on PerPairMR alts branch).
        dataframe.loc[
            (dataframe["macd_hist_4h"] > 0)
            & (dataframe["adx_4h"] > 25)
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["ema200_slope_up_1d"] == 1)
            & (dataframe["close"] > dataframe["ema20"])
            & (dataframe["ema20"] > dataframe["sma50"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Momentum flip OR structure break — patient-ish, rides the trend
        dataframe.loc[
            (dataframe["macd_hist_4h"] < 0)
            | (dataframe["close"] < dataframe["sma50"]),
            "exit_long",
        ] = 1
        return dataframe
