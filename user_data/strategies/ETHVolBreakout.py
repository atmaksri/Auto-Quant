"""
ETHVolBreakout — per-pair Donchian-24 break w/ 4h regime + vol-target sizing (ETH)

Paradigm: breakout
Hypothesis: v0.3.0's BTCLeaderBreakX hit 1.07 via cross-pair Donchian on BTC;
            v0.4.0's VolBreakoutSized reached Sharpe 1.122 on the 5-pair
            universe with per-pair Donchian-24 + 4h EMA50>EMA200 regime gate
            + vol-target sizing. Transfer that exact structure to ETH-only
            under a train/holdout honesty split: does the breakout edge
            survive on a single major with a strict 2025 out-of-sample
            window? Vol-target (4h ATR%/close → ~0.3% ATR per trade) is the
            honesty mechanism: in bear ATRs balloon → smaller stakes.
            Patient SMA50 exit transfers v0.3.0 Finding 2 (breakouts ride).
Parent: root (seeded from versions/0.4.0/strategies/VolBreakoutSized.py,
        restructured to ETH-only + train/holdout timeranges)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHVolBreakout(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 100}
    stoploss = -0.99
    # r7: trailing_stop reverted to False. r6 experiment (ratchet +15%/
    # 8%) hurt robust 0.1017→0.0746 — SMA50 breakdown is the local
    # optimum exit for this entry. Both exit modifications tried
    # (RSI>75 r5, trailing r6) lost to patient breakdown.
    trailing_stop = False
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 250

    # ETH-only — this run optimizes the SELL point for ETH
    pair_basket = ["ETH/USDT"]

    # Train 2021-2024, holdout 2025 — clean OOS split (program.md pattern)
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
        # Per-pair Donchian-48 prior-bar high — r8: 24→48 (window
        # sensitivity test; longer breakout = more confirmed trend)
        dataframe["donchian_high_48"] = dataframe["high"].rolling(48).max().shift(1)
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Donchian-48 break + 4h regime gate + volume confirmation
        dataframe.loc[
            (dataframe["close"] > dataframe["donchian_high_48"])
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Patient ride-the-move exit (v0.3.0 Finding 2: breakouts benefit
        # from slow-SMA exits, not responsive ones)
        dataframe.loc[dataframe["close"] < dataframe["sma50"], "exit_long"] = 1
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
        # Vol-target sizing: scale stake so position-level ATR exposure
        # tracks ~0.3% per 4h bar. High-vol bear → smaller stake → de-risk.
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "atr_pct_4h" not in df.columns:
            return proposed_stake
        atr_pct = df["atr_pct_4h"].iloc[-1]
        if atr_pct != atr_pct or atr_pct <= 0:
            return proposed_stake
        # r2: vol_target 0.003→0.008. r1 showed 0.003 de-risks too hard —
        # avg_position 3.36% FAILs the 5% min-position gate and crushes
        # absolute profit. 0.008 ≈ 0.8% ATR per trade → ~8-10% positions
        # in normal vol, still de-risks in bear (ATR balloons).
        vol_target = 0.008
        scale = min(1.0, vol_target / atr_pct)
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
