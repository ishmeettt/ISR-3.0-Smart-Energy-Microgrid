"""
Transition Controller for HackSphere 3.0 Smart Energy Microgrid.

Implements power-source transition logic based on predicted demand and time rules.
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import numpy as np


@dataclass
class GridState:
    """Represents the grid state for a single hour."""
    timestamp: datetime
    predicted_demand_kw: float
    grid_mode: str  # 'renewable' or 'main_grid'
    is_overload_alert: bool
    hour: int


@dataclass
class TransitionSignal:
    """Output signal for power dispatch."""
    timestamp: datetime
    grid_mode: str
    alert_state: str  # 'normal', 'overload', or 'critical'
    predicted_demand_kw: float
    recommended_action: str


# Thresholds from problem statement
DEMAND_RENEWABLE_THRESHOLD = 160.0  # kW - above this, use renewable
DEMAND_OVERLOAD_THRESHOLD = 200.0   # kW - critical overload alert
PEAK_HOUR_START = 18                # 18:00
PEAK_HOUR_END = 22                  # 22:00 (inclusive)


def is_peak_hour(hour: int) -> bool:
    """
    Check if given hour is in peak window (18:00-22:00 inclusive).

    Args:
        hour: Hour of day (0-23)

    Returns:
        True if hour is in peak window
    """
    return PEAK_HOUR_START <= hour <= PEAK_HOUR_END


def determine_grid_mode(predicted_demand_kw: float, hour: int) -> str:
    """
    Determine grid mode based on demand and time rules.

    Rules:
    - Renewable Storage Mode: Demand > 160 kW OR hour in 18:00-22:00
    - Main Grid Mode: Otherwise (Demand ≤ 160 kW AND outside 18-22)

    Args:
        predicted_demand_kw: Predicted energy demand in kW
        hour: Hour of day (0-23)

    Returns:
        'renewable' or 'main_grid'
    """
    if predicted_demand_kw > DEMAND_RENEWABLE_THRESHOLD or is_peak_hour(hour):
        return 'renewable'
    return 'main_grid'


def check_overload_alert(predicted_demand_kw: float) -> bool:
    """
    Check if critical overload alert should be triggered.

    Alert triggers when demand >= 200 kW (independent of grid mode).

    Args:
        predicted_demand_kw: Predicted energy demand in kW

    Returns:
        True if overload alert should be triggered
    """
    return predicted_demand_kw >= DEMAND_OVERLOAD_THRESHOLD


def generate_transition_signal(
    timestamp: datetime,
    predicted_demand_kw: float
) -> TransitionSignal:
    """
    Generate a complete transition signal for a single timestamp.

    Args:
        timestamp: Timestamp for the forecast hour
        predicted_demand_kw: Predicted demand in kW

    Returns:
        TransitionSignal with grid mode, alert state, and recommended action
    """
    hour = timestamp.hour
    grid_mode = determine_grid_mode(predicted_demand_kw, hour)
    is_overload = check_overload_alert(predicted_demand_kw)

    # Determine alert state
    if is_overload:
        alert_state = 'critical'
        recommended_action = (
            "IMMEDIATE ACTION: Demand exceeds 200 kW threshold. "
            "Engage emergency battery discharge and notify grid operator."
        )
    elif grid_mode == 'renewable':
        alert_state = 'normal'
        recommended_action = (
            "Switch to Renewable Battery Storage. "
            "Battery SOC monitoring recommended."
        )
    else:
        alert_state = 'normal'
        recommended_action = (
            "Main Grid power sufficient. "
            "Maintain standard grid connection."
        )

    return TransitionSignal(
        timestamp=timestamp,
        grid_mode=grid_mode,
        alert_state=alert_state,
        predicted_demand_kw=predicted_demand_kw,
        recommended_action=recommended_action
    )


def process_forecast(
    timestamps: List[datetime],
    predictions: List[float]
) -> List[TransitionSignal]:
    """
    Process a full 24-hour forecast and generate transition signals.

    Args:
        timestamps: List of timestamps for each forecast hour
        predictions: List of predicted demand values (kW)

    Returns:
        List of TransitionSignal objects for each hour
    """
    if len(timestamps) != len(predictions):
        raise ValueError(
            f"Timestamp count ({len(timestamps)}) must match "
            f"prediction count ({len(predictions)})"
        )

    signals = []
    for ts, pred in zip(timestamps, predictions):
        signal = generate_transition_signal(ts, pred)
        signals.append(signal)

    return signals


def process_forecast_from_df(df: pd.DataFrame, predictions: np.ndarray) -> pd.DataFrame:
    """
    Process forecast from DataFrame and predictions array.

    Args:
        df: DataFrame with 'timestamp' column
        predictions: Array of predicted demand values

    Returns:
        DataFrame with grid state information
    """
    if len(df) != len(predictions):
        raise ValueError("DataFrame rows must match prediction count")

    results = []
    for idx, row in df.iterrows():
        ts = pd.to_datetime(row['timestamp'])
        pred = float(predictions[idx])

        signal = generate_transition_signal(ts, pred)

        results.append({
            'timestamp': ts,
            'predicted_demand_kw': pred,
            'grid_mode': signal.grid_mode,
            'alert_state': signal.alert_state,
            'hour': ts.hour,
            'is_peak_hour': is_peak_hour(ts.hour),
            'recommended_action': signal.recommended_action
        })

    return pd.DataFrame(results)


def summarize_forecast(signals: List[TransitionSignal]) -> Dict:
    """
    Generate a summary of the 24-hour forecast.

    Args:
        signals: List of TransitionSignal objects

    Returns:
        Dictionary with summary statistics
    """
    demands = [s.predicted_demand_kw for s in signals]
    grid_modes = [s.grid_mode for s in signals]
    alert_states = [s.alert_state for s in signals]

    return {
        'total_hours': len(signals),
        'avg_demand_kw': np.mean(demands),
        'max_demand_kw': max(demands),
        'min_demand_kw': min(demands),
        'renewable_hours': grid_modes.count('renewable'),
        'main_grid_hours': grid_modes.count('main_grid'),
        'overload_alerts': alert_states.count('critical'),
        'has_critical_alert': 'critical' in alert_states,
        'peak_demand_hour': timestamps_to_hour(
            [s.timestamp for s in signals],
            demands
        )
    }


def timestamps_to_hour(timestamps: List[datetime], values: List[float]) -> Optional[int]:
    """Find the hour with maximum demand."""
    if not values:
        return None
    max_idx = values.index(max(values))
    return timestamps[max_idx].hour


# Convenience function for direct usage
def get_grid_mode_for_hour(
    demand_kw: float,
    hour: int
) -> Tuple[str, bool]:
    """
    Quick function to get grid mode and overload status.

    Returns:
        Tuple of (grid_mode, is_overload_alert)
    """
    return determine_grid_mode(demand_kw, hour), check_overload_alert(demand_kw)
