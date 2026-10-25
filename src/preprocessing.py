"""
Data preprocessing module for HackSphere 3.0.
Handles feature engineering and data validation for energy demand forecasting.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional


def validate_input_dataframe(df: pd.DataFrame) -> bool:
    """
    Validate that input DataFrame has required columns and valid data.

    Required columns: timestamp, ambient_temp_c, humidity_pct, solar_irradiance_wm2

    Args:
        df: Input DataFrame to validate

    Returns:
        True if valid, raises ValueError otherwise
    """
    required_columns = ['timestamp', 'ambient_temp_c', 'humidity_pct', 'solar_irradiance_wm2']

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Check for NaN in required columns
    for col in required_columns:
        if df[col].isnull().any():
            # Fill missing values with column median
            df[col] = df[col].fillna(df[col].median())

    # Validate timestamp format
    try:
        pd.to_datetime(df['timestamp'])
    except Exception as e:
        raise ValueError(f"Invalid timestamp format: {e}")

    # Validate numeric ranges
    if (df['ambient_temp_c'] < -50).any() or (df['ambient_temp_c'] > 60).any():
        raise ValueError("ambient_temp_c outside valid range (-50 to 60 C)")

    if (df['humidity_pct'] < 0).any() or (df['humidity_pct'] > 100).any():
        raise ValueError("humidity_pct outside valid range (0-100%)")

    if (df['solar_irradiance_wm2'] < 0).any() or (df['solar_irradiance_wm2'] > 1500).any():
        raise ValueError("solar_irradiance_wm2 outside valid range (0-1500 W/m²)")

    return True


def clean_input_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and standardize raw telemetry before validation/prediction
    (problem statement requirement 2: "clean and validate data, handle
    missing values, and prepare feature vectors").

    Never fails on dirty *values* — only on a missing required *column*:
    - coerces numeric columns ("31.5" strings, blanks, "N/A" → float/NaN)
    - fills NaN with the column median (or a sane default if all values bad)
    - clamps to physically valid ranges (same bounds validate uses)
    - normalizes timestamps to "YYYY-MM-DD HH:MM:SS"; unparsable timestamps
      are forward/back-filled from neighbors, else defaulted to epoch day

    Returns a cleaned copy; the input frame is not modified.
    """
    required = ['timestamp', 'ambient_temp_c', 'humidity_pct', 'solar_irradiance_wm2']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    out = df.copy()

    # --- Numeric coercion + missing-value imputation ---
    numeric_defaults = {
        'ambient_temp_c': 20.0,
        'humidity_pct': 60.0,
        'solar_irradiance_wm2': 0.0,
    }
    numeric_ranges = {
        'ambient_temp_c': (-50.0, 60.0),
        'humidity_pct': (0.0, 100.0),
        'solar_irradiance_wm2': (0.0, 1500.0),
    }
    for col, default in numeric_defaults.items():
        s = pd.to_numeric(out[col], errors='coerce')
        fill = s.median()
        if pd.isna(fill):
            fill = default
        s = s.fillna(fill)
        lo, hi = numeric_ranges[col]
        out[col] = s.clip(lo, hi)

    # --- Timestamp normalization ---
    ts = pd.to_datetime(out['timestamp'], errors='coerce')
    if ts.isna().any():
        ts = ts.ffill().bfill()
        ts = ts.fillna(pd.Timestamp('2024-01-01 00:00:00'))
    out['timestamp'] = ts.dt.strftime('%Y-%m-%d %H:%M:%S')

    return out


def extract_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract time-based features from timestamp column.

    Features added:
    - hour: Hour of day (0-23)
    - day_of_week: Day of week (0=Monday, 6=Sunday)
    - is_peak_hour: Boolean, True if hour in 18-22 range
    - hour_sin, hour_cos: Cyclical encoding of hour

    Args:
        df: DataFrame with 'timestamp' column

    Returns:
        DataFrame with additional time features
    """
    df = df.copy()
    dt = pd.to_datetime(df['timestamp'])

    df['hour'] = dt.dt.hour
    df['day_of_week'] = dt.dt.dayofweek

    # Peak hour indicator (18:00-22:00 inclusive)
    df['is_peak_hour'] = ((dt.dt.hour >= 18) & (dt.dt.hour <= 22)).astype(int)

    # Cyclical encoding for hour (captures 23->0 transition)
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)

    return df


def create_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create derived weather features.

    Features added:
    - temp_above_24: Temperature above 24°C threshold (for cooling load)
    - humidity_inv: Inverse humidity (higher demand when dry)
    - solar_normalized: Normalized solar irradiance

    Args:
        df: DataFrame with weather columns

    Returns:
        DataFrame with additional weather features
    """
    df = df.copy()

    # Cooling load indicator (temperature above comfort threshold)
    df['temp_above_24'] = np.maximum(0, df['ambient_temp_c'] - 24.0)

    # Humidity effect (inverted - lower humidity often correlates with higher temps)
    df['humidity_inv'] = 100 - df['humidity_pct']

    # Solar irradiance normalized to [0, 1]
    df['solar_normalized'] = df['solar_irradiance_wm2'] / 1000.0

    # Combined heat index approximation
    df['heat_load'] = (df['ambient_temp_c'] * 0.5 +
                       df['temp_above_24'] * 8.5 -
                       df['humidity_pct'] * 0.2)

    return df


def prepare_features(df: pd.DataFrame, add_derived: bool = True) -> pd.DataFrame:
    """
    Prepare complete feature set for model input.

    Args:
        df: Input DataFrame with raw columns
        add_derived: Whether to add derived features

    Returns:
        DataFrame with all features prepared
    """
    df = df.copy()

    # Validate and clean
    validate_input_dataframe(df)

    # Extract time features
    df = extract_time_features(df)

    if add_derived:
        # Create weather-derived features
        df = create_weather_features(df)

    return df


def load_training_data(filepath: str) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Load and prepare training data.

    Args:
        filepath: Path to training CSV file

    Returns:
        Tuple of (features DataFrame, target Series)
    """
    df = pd.read_csv(filepath)

    # Prepare features
    df = prepare_features(df, add_derived=True)

    # Separate target
    y = df['target_demand_kw']
    X = df.drop(columns=['target_demand_kw', 'timestamp'])

    return X, y


def load_test_data(filepath: str) -> pd.DataFrame:
    """
    Load and prepare test/inference data.

    Args:
        filepath: Path to test CSV file (without target_demand_kw)

    Returns:
        DataFrame with features ready for prediction
    """
    df = pd.read_csv(filepath)

    # Prepare features (test data has no target)
    df = prepare_features(df, add_derived=True)

    return df
