"""
HackSphere 3.0 - Energy Demand Prediction Module

This module provides demand forecasting for the Smart Energy Microgrid.
It integrates with Zoho Catalyst QuickML for production predictions
and includes an improved fallback model for local development.

Usage:
    python predict.py --input sample_test_input.csv --output predictions.csv
"""

import argparse
import os
import sys
from typing import Union, List

import numpy as np
import pandas as pd
import requests

try:
    from .preprocessing import (
        prepare_features,
        validate_input_dataframe,
        clean_input_dataframe,
    )
    from .transition import process_forecast_from_df
except ImportError:
    # When run as script or from tests
    from preprocessing import (
        prepare_features,
        validate_input_dataframe,
        clean_input_dataframe,
    )
    from transition import process_forecast_from_df

# Published QuickML-backed API (Catalyst Advanced I/O function that calls the
# QuickML endpoint server-side, keeping the endpoint key off this machine).
# Override with the QUICKML_ENDPOINT_URL env var or --quickml-url.
DEFAULT_QUICKML_ENDPOINT_URL = (
    "https://project-rainfall-60093145112.development.catalystserverless.in/"
    "server/predict/execute"
)
QUICKML_ENDPOINT_URL = os.environ.get("QUICKML_ENDPOINT_URL", DEFAULT_QUICKML_ENDPOINT_URL)


# ============================================================================
# Model Coefficients (derived from training data analysis)
# ============================================================================

# Hourly base load pattern (learned from training data means)
HOURLY_BASE_LOAD = {
    0: 92.4, 1: 91.9, 2: 91.8, 3: 90.8, 4: 91.5, 5: 91.8,
    6: 136.1, 7: 177.3, 8: 181.1, 9: 186.5, 10: 159.4,
    11: 163.7, 12: 165.3, 13: 170.2, 14: 172.4, 15: 171.0,
    16: 173.0, 17: 171.3, 18: 220.6, 19: 217.8, 20: 215.0,
    21: 209.4, 22: 204.7, 23: 114.8
}

# Training data statistics for normalization
TRAIN_STATS = {
    'ambient_temp_c_mean': 18.5,
    'ambient_temp_c_std': 10.2,
    'humidity_pct_mean': 68.0,
    'humidity_pct_std': 15.0,
    'solar_irradiance_wm2_mean': 120.0,
    'solar_irradiance_wm2_std': 150.0,
    'target_mean': 156.6,
    'target_std': 50.5
}


def predict(input_df: pd.DataFrame) -> np.ndarray:
    """
    Predict energy demand for input DataFrame.

    Parameters:
        input_df (pandas.DataFrame): DataFrame with columns
            ['timestamp', 'ambient_temp_c', 'humidity_pct', 'solar_irradiance_wm2']

    Returns:
        numpy.ndarray: Predicted demand (kW) for each input row.

    Raises:
        ValueError: If input DataFrame is invalid or missing required columns.
    """
    # Clean FIRST (requirement 2): coerce numerics, impute missing values,
    # clamp ranges, normalize timestamps. Only a missing required column
    # raises; dirty values are repaired so the API payload is always
    # JSON-serializable (NaN would otherwise serialize as invalid JSON).
    try:
        cleaned_df = clean_input_dataframe(input_df)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise

    # Validate and prepare features from the cleaned copy
    try:
        validate_input_dataframe(cleaned_df)
        features_df = prepare_features(cleaned_df, add_derived=True)
    except ValueError as e:
        print(f"Warning: Input validation issue - {e}", file=sys.stderr)
        # Continue with cleaned data (ranges already clamped by cleaning)
        features_df = prepare_features(cleaned_df.copy(), add_derived=True)

    # Call the published QuickML-backed API (one batch request for all rows).
    if QUICKML_ENDPOINT_URL:
        try:
            payload = {"data": cleaned_df.to_dict(orient="records")}
            response = requests.post(
                QUICKML_ENDPOINT_URL,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            predictions = np.array(result["predictions"], dtype=float)

            # Surface which backend produced the numbers (QuickML vs fallback).
            note = result.get("note", "")
            if note and "QuickML" not in note:
                print(f"Warning: API used fallback model instead of the trained "
                      f"QuickML model ({result.get('quickml_error', note)})",
                      file=sys.stderr)

            # Validate QuickML response
            if len(predictions) != len(input_df):
                print("Warning: QuickML returned unexpected prediction count",
                      file=sys.stderr)
                raise ValueError("Prediction count mismatch")

            if np.isnan(predictions).any() or np.isinf(predictions).any():
                print("Warning: QuickML returned NaN/Inf values",
                      file=sys.stderr)
                raise ValueError("Invalid predictions from QuickML")

            return predictions

        except Exception as e:
            print(f"Warning: QuickML endpoint call failed ({e}). Using fallback model.",
                  file=sys.stderr)

    # Fallback: Improved heuristic model based on training data analysis
    predictions = _improved_fallback_model(features_df)
    return predictions


def _improved_fallback_model(features_df: pd.DataFrame) -> np.ndarray:
    """
    Improved fallback prediction model using multiple factors.

    This model uses:
    - Hourly base load pattern (from training data)
    - Temperature effect (cooling load above 24°C)
    - Humidity effect (inverse correlation with demand)
    - Solar irradiance effect (small positive correlation)
    - Peak hour boost (18-22 additional load)

    Args:
        features_df: DataFrame with prepared features

    Returns:
        Array of predicted demand values
    """
    hours = features_df['hour'].values
    temp = features_df['ambient_temp_c'].values
    humidity = features_df['humidity_pct'].values
    solar = features_df['solar_irradiance_wm2'].values

    # 1. Base load from hourly pattern (scaled to be more conservative)
    base_load = np.array([HOURLY_BASE_LOAD.get(h, 140.0) for h in hours]) * 0.85

    # 2. Temperature effect (cooling load)
    # Training correlation: 0.53 with ambient_temp_c
    temp_effect = np.maximum(0, temp - 24.0) * 5.0

    # 3. Humidity effect (negative correlation: -0.50)
    # Lower humidity often means higher temperatures and more AC use
    humidity_effect = (68.0 - humidity) * 0.25

    # 4. Solar effect (small positive correlation: 0.28)
    # Higher solar during day hours correlates with higher activity
    solar_effect = (solar / 100.0) * 1.5

    # 5. Peak hour modifier (18-22 already in base, but add slight boost)
    peak_mask = ((hours >= 18) & (hours <= 22)).astype(float)
    peak_boost = peak_mask * 5.0

    # Combine all effects
    predictions = base_load + temp_effect + humidity_effect + solar_effect + peak_boost

    # Add small random variation to avoid perfectly flat predictions
    # (seeded for reproducibility)
    np.random.seed(42)
    noise = np.random.normal(0, 3.0, len(predictions))
    predictions += noise

    # Ensure predictions are within reasonable bounds
    # Training data: min=51, max=306, mean=157, std=50
    predictions = np.clip(predictions, 50.0, 310.0)

    return predictions


def predict_with_transition(
    input_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Predict demand and generate grid transition signals.

    This is a convenience function that combines prediction with
    the transition controller logic.

    Args:
        input_df: Input DataFrame with weather features

    Returns:
        DataFrame with predictions and grid state information
    """
    predictions = predict(input_df)
    results_df = process_forecast_from_df(input_df, predictions)
    return results_df


def save_predictions(
    input_df: pd.DataFrame,
    predictions: np.ndarray,
    output_path: str
) -> None:
    """
    Save predictions to CSV file in required format.

    Format:
        timestamp,target_demand_kw
        2024-01-01 00:00:00,128.45

    Args:
        input_df: Original input DataFrame (for timestamps)
        predictions: Array of predicted values
        output_path: Path to output CSV file
    """
    output_df = pd.DataFrame({
        'timestamp': input_df['timestamp'],
        'target_demand_kw': np.round(predictions, 2)
    })
    output_df.to_csv(output_path, index=False)
    print(f"Predictions saved to {output_path}")
    print(f"Total predictions: {len(predictions)}")


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description='HackSphere 3.0 Energy Demand Prediction'
    )
    parser.add_argument(
        '--input',
        type=str,
        default='sample_test_input.csv',
        help='Input CSV file path (default: sample_test_input.csv)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='predictions.csv',
        help='Output CSV file path (default: predictions.csv)'
    )
    parser.add_argument(
        '--quickml-url',
        type=str,
        default=None,
        help='QuickML endpoint URL (overrides default)'
    )

    args = parser.parse_args()

    # Override QuickML URL if provided
    if args.quickml_url:
        global QUICKML_ENDPOINT_URL
        QUICKML_ENDPOINT_URL = args.quickml_url

    print("=" * 60)
    print("HackSphere 3.0 - Energy Demand Prediction")
    print("=" * 60)

    # Load input data
    try:
        input_df = pd.read_csv(args.input)
        print(f"Loaded {len(input_df)} rows from {args.input}")
    except FileNotFoundError:
        print(f"Error: Input file '{args.input}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading input file: {e}")
        sys.exit(1)

    # Show input stats
    print(f"\nInput data summary:")
    print(f"  Timestamps: {input_df['timestamp'].min()} to {input_df['timestamp'].max()}")
    print(f"  Temp range: {input_df['ambient_temp_c'].min():.1f}°C to {input_df['ambient_temp_c'].max():.1f}°C")
    print(f"  Humidity range: {input_df['humidity_pct'].min():.1f}% to {input_df['humidity_pct'].max():.1f}%")
    print(f"  Solar range: {input_df['solar_irradiance_wm2'].min():.1f} to {input_df['solar_irradiance_wm2'].max():.1f} W/m²")

    # Generate predictions
    print("\nGenerating predictions...")
    predictions = predict(input_df)

    # Show prediction stats
    print(f"\nPrediction summary:")
    print(f"  Mean: {np.mean(predictions):.2f} kW")
    print(f"  Min: {np.min(predictions):.2f} kW")
    print(f"  Max: {np.max(predictions):.2f} kW")
    print(f"  Std: {np.std(predictions):.2f} kW")

    # Show first few predictions
    print(f"\nFirst 5 predictions:")
    for i in range(min(5, len(predictions))):
        ts = input_df['timestamp'].iloc[i]
        print(f"  {ts}: {predictions[i]:.2f} kW")

    # Save to file
    save_predictions(input_df, predictions, args.output)

    # Show transition summary if 24 hours
    if len(input_df) == 24:
        print("\n" + "=" * 60)
        print("Grid Transition Summary (24-hour forecast)")
        print("=" * 60)

        results_df = process_forecast_from_df(input_df, predictions)

        renewable_count = (results_df['grid_mode'] == 'renewable').sum()
        main_grid_count = (results_df['grid_mode'] == 'main_grid').sum()
        overload_count = (results_df['alert_state'] == 'critical').sum()

        print(f"  Renewable Storage Mode: {renewable_count} hours")
        print(f"  Main Grid Mode: {main_grid_count} hours")
        print(f"  Critical Overload Alerts: {overload_count}")

        if overload_count > 0:
            print("\n  ⚠️  CRITICAL ALERTS:")
            alerts = results_df[results_df['alert_state'] == 'critical']
            for _, row in alerts.iterrows():
                print(f"    {row['timestamp']}: {row['predicted_demand_kw']:.2f} kW")

    print("\n" + "=" * 60)
    print("Prediction complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
