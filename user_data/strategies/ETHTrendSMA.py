"""
ETHTrendSMA — 1h EMA trend under 1d bull regime (ETH) — r17 C (3rd slot)

Paradigm: trend-following
Hypothesis: ETH exhibits exploitable 1h trend persistence (EMA50>EMA200) only
            when the 1d macro trend is bullish (close > EMA200_1d) and
            momentum is confirmed (ADX>20). Without the 1d filter, 1h EMAs
            chop in 2022 winter (reproduced by ETHTrailingTrend r3-4:
            EMA-stack entries fired in chop, both windows negative). This
            slot tests the v0.4.1 'second gold filter' thesis in isolation
            on a pure trend paradigm, with equal-weight sizing (no
            custom_stake_amount) as a control against VolBreakout's
            vol-target. Exit is patient SMA50 break (mirrors VolBreakout;
            lets us compare breakout-entry vs trend-entry on same exit).
            If trend-entry is worse, the edge is breakout-specific not
            trend-generic.
Parent: root (new paradigm for eth1, complements breakout + crash-rebound)
Created: r17 — 3rd slot alongside A+B VolBreakout evolution
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHTrendSMA(IStrategy):
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

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r21 proven: ADX25+vol1.5 fixed TrendSMA 0.074->0.209 (13.13%/3.32%,
        # 108/29 trades). r26: volume 1.5->1.3 test (MUST: counter 3).
        # Train 13.13% already large vs holdout 3.32%: volume may be
        # binding — looser 1.3 -> more trades, maybe higher worst profit.
        # If hurts, revert r27.
        dataframe.loc[
            (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["adx"] > 25)
            & (dataframe["close"] > dataframe["ema200_1d"])
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Patient exit shared with VolBreakout for comparability — SMA50 break
        # (r17 B uses SMA100 on VolBreakout; this stays on 50 as control)
        dataframe.loc[dataframe["close"] < dataframe["sma50"], "exit_long"] = 1
        return dataframe
