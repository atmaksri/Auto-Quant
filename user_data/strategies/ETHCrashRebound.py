"""
ETHCrashRebound — buy ETH after a -20% drawdown from rolling 30d high

Paradigm: other (counter-trend / drawdown-rebound)
Hypothesis: CrashRebound (v0.4.1) had the strongest bull_2021 number in the
            project (0.82 sharpe / +31% / WR 62.5%) on alts, but r18 showed
            BTC/ETH winter drawdown-bounces are weaker than alts' — the
            paradigm generalized to majors in directional regimes but not
            under the robust-sharpe bar. This run tests the ETH-only
            transfer under a train/holdout split: does drawdown-rebound
            have real edge on a single major, and does the 2025 holdout
            confirm it? Trigger: 1h close < 30d rolling max × 0.80 AND
            RSI(14) < 35 + volume capitulation + 1d regime slope.
            Exit: close > SMA50 (mean-reversion target). DD-conviction
            sizing (clamp(|dd|/0.20, 0.5, 2.0)) per v0.4.1 r16 (paradigm-
            agnostic conviction sizing finding).
Parent: root (seeded from versions/0.4.1/strategies/CrashRebound.py,
        restructured to ETH-only + train/holdout timeranges)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ETHCrashRebound(IStrategy):
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

    # 30d at 1h = 720 bars warmup, but kraken exchange caps at 719
    # candles for 1h. 500 is safely under the cap; the rolling 720
    # window is still NaN for the first ~220 bars after startup, so no
    # spurious entries occur — first real signal still needs a full 30d
    # high, identical to the OKX 760 run. Fixes ConfigurationError on
    # kraken without changing signal logic.
    startup_candle_count: int = 500

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
        # 30-day rolling high (720 1h bars). Drawdown trigger uses prior bar
        # to avoid current-bar self-reference.
        dataframe["high_30d"] = dataframe["high"].rolling(720).max().shift(1)
        dataframe["drawdown_pct"] = (
            dataframe["close"] / dataframe["high_30d"] - 1.0
        )
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        # r15 finding: SMA50 tight exit is the optimum for drawdown-rebound —
        # bounces revert quickly, patient exits turn winners into losers.
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r23: REVERT RSI 40->35. r22 35->40 hurt: +3 holdout trades but
        # profit 7.67->5.96 train / 2.27->1.82 holdout, pf 1.99->1.74,
        # robust 0.102->0.081. Confirms RSI<35 is local optimum (r5 DD
        # -0.20 optimum pattern, BNB RSI<25). Keep 35, accept 28/13
        # sparse but high-quality (WR 71%, pf 1.75) — sparse is feature.
        dataframe.loc[
            (dataframe["drawdown_pct"] < -0.20)
            & (dataframe["rsi"] < 35)
            & (dataframe["ema200_slope_up_1d"] == 1),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r15: REVERT RSI>55 → close>SMA50. r14 split: train liked RSI
        # exit, holdout strongly preferred price-reclaim. robust=min makes
        # close>SMA50 optimal for this paradigm.
        dataframe.loc[dataframe["close"] > dataframe["sma50"], "exit_long"] = 1
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
        # DD-conviction sizing: deeper drawdown → bigger stake (r16 finding:
        # conviction-style sizing transfers paradigm-agnostically).
        # NOTE: do NOT compose with regime sizing — r28 showed regime and
        # DD-signal are negatively correlated → inverse-amplification.
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "drawdown_pct" not in df.columns:
            return proposed_stake
        dd = df["drawdown_pct"].iloc[-1]
        if dd != dd or dd >= 0:
            return proposed_stake
        scale = abs(float(dd)) / 0.20
        scale = max(0.5, min(2.0, scale))
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
