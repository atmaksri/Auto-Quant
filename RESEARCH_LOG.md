
## r31 — grid-trading approximation (2026-08-24)
ETHGridDCA: DCA-ladder approximation of grid trading (3 tranches, rungs
-2.5%/-5%, BB-mid exit, ADX<22 regime gate + 30d-mean distance filter).
train **-0.65 Sharpe / -25.9% / 202 trades** — worst single result of the
entire program. Holdout also negative (-0.12).

Mechanism: healthy-looking win rate (57%) masks the failure — ladders
complete at max inventory precisely during drift-downs, so losses dwarf
wins. The "crypto ranges 70% of time" premise fails on ETH: its ranges
contain directional segments that finish grids at maximum exposure.

All four externally-proposed families now evaluated:
| family | verdict |
|---|---|
| market making | architecturally impossible in freqtrade |
| triangular arbitrage | architecturally impossible (latency) |
| RSI/BB scalping | killed r29 (two variants) |
| grid/DCA trading | killed r31 (-0.65, worst of program) |

Production lineup unchanged and further validated by contrast:
ETHTrendSMA + ETHCrashRebound remain the complete viable set for
long-only spot ETH.

## r31b — multi-pair basket scaling (2026-08-24)
MULTITrendSMA: TrendSMA logic generalized to a 17-pair Binance.US liquid
majors basket (max_open_trades=4, relative-strength rank filter).
train **-0.61 Sharpe / -20.1% / 680 trades**, holdout -0.37.
DECISIVE FAILURE vs the ETH-only parent (+0.19 / +12.8%).

Finding: the validated ETH trend edge does not transfer to alts by
naive replication. Alt pairs mean-revert harder and have noisier
volume confirms; the ETH-only focus of this program was a feature,
not a limitation. Multi-pair would need per-pair calibration and
stricter selection gates to be worth revisiting.

Also this round: run.py PAIRS extended to the 17-pair basket;
user_data/basket_config.json fragment added for future research runs.

## r32 — cross-asset control test: ETH -> BTC (2026-08-24)
BTCTrendSMA: byte-for-byte identical logic to production ETHTrendSMA r27,
only the pair changed to BTC/USDT.
train +0.13 Sharpe / +7.0% / 131 trades — plausible-looking.
holdout **-0.66 / -5.5%** / WR 31.9% — collapsed out-of-sample.

FINDING (sharpest of the program): the trend edge is genuinely
ETH-idiosyncratic. It does not transfer even to BTC, the most
structurally similar asset. This simultaneously:
1. Confirms single-asset specialization as correct design
2. Explains the multi-pair failure (r31b) at its root
3. Validates the train/holdout protocol — train-only evaluation
   would have admitted this strategy (+0.13 looked fine)

Conclusion: edge lives in the interaction of rule-set AND asset
microstructure. No generalization without per-asset re-validation,
and even then, prior evidence says most assets won't have an edge.
