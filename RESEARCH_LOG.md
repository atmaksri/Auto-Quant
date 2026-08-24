
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
