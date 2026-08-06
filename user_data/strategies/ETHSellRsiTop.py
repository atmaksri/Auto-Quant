"""
ETHSellRsiTop — sell into overbought exhaustion on ETH

Paradigm: mean-reversion
Hypothesis: ETH 1h frequently overshoots on RSI>70 + BB-upper tags; those
            marks are reliable local tops. Strategy enters on pullback
            (RSI<35) and exits into overbought (RSI>70 or close>BB-upper).
            The SELL TIMING is the edge: exit on first overbought tag vs
            waiting for RSI to roll over. Uses 4h RSI as regime gate so we
            don't sell bounces in a bear leg, and 1d EMA200 as trend filter
            so entries only happen in structurally bullish context.
Parent: root
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHSellRsiTop(IStrategy):
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

    # ETH-only — we are optimizing the SELL point for ETH
    pair_basket = ["ETH/USDT"]

    # 4 regimes so robust_sharpe = worst regime, not bull-only illusion
    test_timeranges = [
        ("bull_2021",      "20210101-20211231"),
        ("winter_2022",    "20220101-20221231"),
        ("recovery_23_25", "20230101-20251231"),
        ("full_5y",        "20210101-20251231"),
    ]

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
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
        # Bollinger 20, 2 sigma — upper tag is the sell signal
        period, std = 20, 2.0
        sma = dataframe["close"].rolling(period).mean()
        sd = dataframe["close"].rolling(period).std()
        dataframe["bb_upper"] = sma + std * sd
        dataframe["bb_lower"] = sma - std * sd
        dataframe["bb_mid"] = sma
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Buy dip in bullish structure; sell timing is where edge is tested
        dataframe.loc[
            (dataframe["rsi"] < 35)
            & (dataframe["close"] < dataframe["bb_lower"])
            & (dataframe["rsi_4h"] < 50)          # 4h not overheated
            & (dataframe["close"] > dataframe["ema200_1d"] * 0.90)  # not in deep bear
            & (dataframe["ema200_slope_up_1d"] == 1),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # SELL into exhaustion — the optimization target
        # Tight sell: first RSI>70 or BB-upper tag captures the top
        dataframe.loc[
            (dataframe["rsi"] > 70)
            | (dataframe["close"] > dataframe["bb_upper"]),
            "exit_long",
        ] = 1
        return dataframe
