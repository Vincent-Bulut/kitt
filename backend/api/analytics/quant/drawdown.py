"""Drawdown series, episodes and maximum drawdown path (pure functions)."""

from typing import Any

import numpy as np
import pandas as pd


def drawdown_series(prices: pd.Series) -> pd.DataFrame:
    p = prices.dropna().copy()
    p.index = pd.to_datetime(p.index).tz_localize(None)
    rm = p.cummax()
    dd = p / rm - 1.0
    return pd.DataFrame({"Price": p, "RunningMax": rm, "Drawdown": dd})


def drawdown_metrics_and_episodes(prices: pd.Series) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    dd_df = drawdown_series(prices)
    dd = dd_df["Drawdown"]

    max_dd = float(dd.min())
    current_dd = float(dd.iloc[-1].item())

    in_dd = dd < 0
    episode_id = (in_dd != in_dd.shift(1, fill_value=False)).cumsum()

    durations = []
    troughs = []
    episodes = []
    for _, block in dd_df[in_dd].groupby(episode_id[in_dd]):
        durations.append(len(block))
        trough_val = float(block["Drawdown"].min())
        troughs.append(trough_val)
        
        trough_dt = block["Drawdown"].idxmin()
        start_dt = block.index[0]
        end_dt = block.index[-1]
        
        # Check if it's recovered (last point drawdown is 0 or it's the end of series)
        # In this loop we only have blocks where in_dd is True. 
        # If the block ends before the end of the full series, it means it recovered.
        recovered = end_dt < dd.index[-1]
        
        episodes.append({
            "start_date": start_dt.date().isoformat(),
            "trough_date": trough_dt.date().isoformat(),
            "end_date": end_dt.date().isoformat() if recovered else None,
            "duration_days": len(block),
            "max_drawdown": trough_val
        })

    metrics = {
        "observations": int(dd.dropna().shape[0]),
        "max_drawdown": max_dd,
        "current_drawdown": current_dd,
        "num_drawdown_episodes": len(durations),
        "avg_drawdown_length_trading_days": float(np.mean(durations)) if durations else 0.0,
        "max_drawdown_length_trading_days": int(max(durations)) if durations else 0,
        "worst_episode_trough": float(min(troughs)) if troughs else 0.0,
    }
    return metrics, episodes


def max_drawdown_path(prices: pd.Series) -> dict[str, Any]:
    dd_df = drawdown_series(prices)
    p = dd_df["Price"]
    dd = dd_df["Drawdown"]

    trough_dt = dd.idxmin()
    trough_dd = float(dd.loc[trough_dt])

    peak_dt = p.loc[:trough_dt].idxmax()
    peak_price = float(p.loc[peak_dt].item())

    after = p.loc[trough_dt:]
    rec = after[after >= peak_price]
    rec_dt = rec.index[0] if not rec.empty else None

    return {
        "peak_date": peak_dt.date().isoformat(),
        "trough_date": trough_dt.date().isoformat(),
        "recovery_date": None if rec_dt is None else rec_dt.date().isoformat(),
        "max_drawdown": trough_dd,
    }
