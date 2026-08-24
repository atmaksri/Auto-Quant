"""
Fee sensitivity analysis for ETHVolBreakout + ETHCrashRebound on OKX feathers.
Reuses run.py's loading/metric machinery but overrides the fee per scenario.
Scenarios: 0.1% (baseline), 0.25% (Kraken maker), 0.40% (Kraken taker).
Read-only wrt repo files. Results printed as a comparison table.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import run  # noqa: E402  (repo oracle module)
from freqtrade.configuration import Configuration
from freqtrade.enums import RunMode
from freqtrade.optimize.backtesting import Backtesting

SCENARIOS = [
    ("bus_maker_0.0%", 0.0),
    ("bus_0.075%", 0.00075),
    ("baseline_0.10%", 0.001),
    ("kraken_maker_0.25%", 0.0025),
    ("kraken_taker_0.40%", 0.004),
]
STRATEGIES = ["ETHVolBreakout", "ETHCrashRebound"]
TIMERANGE = "20210101-20241231"


def run_one(strategy: str, fee: float):
    args = {
        "config": [str(run.CONFIG)],
        "user_data_dir": str(run.USER_DATA),
        "datadir": str(run.DATA_DIR),
        "strategy": strategy,
        "strategy_path": str(run.STRATEGIES_DIR),
        "timerange": TIMERANGE,
        "export": "none",
        "exportfilename": None,
        "cache": "none",
    }
    config = Configuration(args, RunMode.BACKTEST).get_config()
    config["fee"] = fee
    basket = getattr(run.load_strategy_class(strategy), "pair_basket", None)
    if basket:
        config["exchange"]["pair_whitelist"] = list(basket)
    bt = Backtesting(config)
    bt.start()
    return run.extract_metrics(bt.results, strategy, [basket[0]] if basket else run.PAIRS)


def main():
    print(f"timerange: {TIMERANGE} (train window)\n")
    header = f"{'scenario':<20} {'strategy':<18} {'sharpe':>7} {'profit%':>9} {'trades':>7} {'win%':>6}"
    print(header)
    print("-" * len(header))
    results = {}
    for label, fee in SCENARIOS:
        for strat in STRATEGIES:
            m = run_one(strat, fee)["aggregate"]
            results[(label, strat)] = m
            print(f"{label:<20} {strat:<18} {m['sharpe']:>7.3f} {m['total_profit_pct']:>9.2f} "
                  f"{m['trade_count']:>7d} {m['win_rate_pct']:>6.1f}")
    print()
    # deltas vs baseline
    for strat in STRATEGIES:
        base = results[("baseline_0.10%", strat)]
        print(f"{strat}: baseline profit {base['total_profit_pct']:.2f}%")
        for label, _ in SCENARIOS[1:]:
            m = results[(label, strat)]
            delta = m["total_profit_pct"] - base["total_profit_pct"]
            print(f"  {label}: profit {m['total_profit_pct']:.2f}% ({delta:+.2f} pts)")


if __name__ == "__main__":
    main()
