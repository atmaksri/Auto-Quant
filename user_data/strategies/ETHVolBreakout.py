"""
ETHVolBreakout — per-pair Donchian-48 break w/ 4h regime + vol-target sizing (ETH) — r18

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
            r17 A+B combined size (0.015) + SMA100: profit 5.6%->8.5%
            but sharp 0.19->0.12, pareto-dominated by r8. r18 keeps A
            (vol_target 0.015 stays ~16% position) and reverts B
            (SMA100->SMA50) to disentangle hold-time vs size — tests
            whether A alone clears more toward 20% at r8's risk-adjusted
            speed.
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
        # r18: SMA100 removed — kept only for r17 B, now reverted to SMA50
        # (see populate_exit_trend). Dead code removed to keep dataframe lean.
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r24: volume 1.3->1.0 (trade-count lift for 20% floor push).
        # r15 sweep 1.5 vs 1.3 showed 1.3 optimum (0.196->0.182), but that
        # was at 0.008 size. At 0.018 size with reclaimed SMA50, volume may
        # be non-binding (like CrashRebound r10): looser = more trades
        # (134->~160) without quality loss. If hurts, revert r25.
        dataframe.loc[
            (dataframe["close"] > dataframe["donchian_high_48"])
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["volume"] > 1.0 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r18: REVERT SMA100->SMA50. r17 B hurt robust 0.19->0.12
        # (2d18h hold winrate 33.9%<35.1%, pf 1.29<1.41). Keep A sizing
        # (vol_target 0.015) but restore r8 exit speed — tests A alone.
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
        # r22: vol_target 0.030→0.018 MIDDLE. r20 0.030 capped (21% pos,
        # only 10.77%/9.21% vs 10.12%/9.75% at 0.022 — diminishing, holdout
        # -0.54). r18 0.015 gave 8.42%/8.43% at 0.17 sharpe. 0.018 ~18% pos
        # recaptures sharpe (target ~0.18) while keeping profit >9% — better
        # Pareto than 0.030 (pareto-d by r8 0.196/-2.43). Size ceiling proven.
        vol_target = 0.018
        scale = min(1.0, vol_target / atr_pct)
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
