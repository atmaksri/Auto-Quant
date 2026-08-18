"""
ETHVolBreakout — per-pair Donchian-48 break w/ 4h regime + vol-target sizing (ETH) — r17 A+B

Paradigm: breakout
Hypothesis: v0.3.0's BTCLeaderBreakX hit 1.07 via cross-pair Donchian on BTC;
            v0.4.0's VolBreakoutSized reached Sharpe 1.122 on the 5-pair
            universe with per-pair Donchian-24 + 4h EMA50>EMA200 regime gate
            + vol-target sizing. Transfer that exact structure to ETH-only
            under a train/holdout honesty split: does the breakout edge
            survive on a single major with a strict 2025 out-of-sample
            window? Vol-target (4h ATR%/close) is the honesty mechanism:
            in bear ATRs balloon → smaller stakes. Patient SMA exit
            transfers v0.3.0 Finding 2 (breakouts ride).
            r17 combines A (vol_target 0.008->0.015, size ~8.9%->~16%,
            profit ~5.6%->~10% linearly, DD 2.4%->~4.5%) + B (SMA50->SMA100
            exit, ride longer: 1d15h->~2.5d, fewer trades 134->~80)—
            both target profit_floor 20% from different axes (size vs
            hold-time). If SMA100 hurts, r18 reverts it but keeps sizing.
Parent: root (seeded from versions/0.4.0/strategies/VolBreakoutSized.py,
        restructured to ETH-only + train/holdout timeranges)
Created: r17 — A+B combined (was pending until r17)
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
        # Per-pair Donchian-48 prior-bar high — r13: 72→48 (REVERT.
        # Window sweep: 24→0.10, 48→0.20, 72→0.11 — 48 is the local
        # optimum; longer misses early-cycle breaks)
        dataframe["donchian_high_48"] = dataframe["high"].rolling(48).max().shift(1)
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["sma100"] = ta.SMA(dataframe, timeperiod=100)  # r17 B: slow exit
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Donchian-48 break + 4h regime gate + volume confirmation
        # r15: volume 1.5→1.3 (REVERT — r14 slightly worse, 1.3 optimum)
        dataframe.loc[
            (dataframe["close"] > dataframe["donchian_high_48"])
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r17 B: SMA50->SMA100 — ride longer (v0.3.0 Finding 2: slow exits
        # help breakouts). If this hurts robust, r18 reverts to SMA50
        # but keeps sizing (A) — disentangles hold-time vs size.
        dataframe.loc[dataframe["close"] < dataframe["sma100"], "exit_long"] = 1
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
        # r17 A: vol_target 0.008→0.015. r2 0.003→0.008 fixed min_position
        # 3.36%->8.9% PASS; 0.015 ≈ 1.5% ATR per trade → ~16% positions in
        # normal vol, profit scales ~linearly (5.6%->~10% train) while
        # DD 2.4%->~4.5% stays single-digit. Still de-risks in bear.
        vol_target = 0.015
        scale = min(1.0, vol_target / atr_pct)
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
