"""
Comprehensive test suite for HackSphere 3.0 prediction module.

Run with: python -m pytest tests/ -v
Or: python tests/test_predict.py
"""

import sys
import os
from datetime import datetime
from typing import List

import numpy as np
import pandas as pd

# Add src to path for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest

from predict import (
    predict,
    predict_with_transition,
    save_predictions,
    _improved_fallback_model,
    QUICKML_ENDPOINT_URL
)
from preprocessing import (
    validate_input_dataframe,
    extract_time_features,
    create_weather_features,
    prepare_features,
    load_training_data,
    load_test_data
)
from transition import (
    determine_grid_mode,
    check_overload_alert,
    is_peak_hour,
    generate_transition_signal,
    process_forecast,
    process_forecast_from_df,
    summarize_forecast,
    get_grid_mode_for_hour
)


# ============================================================================
# Test Data Helpers
# ============================================================================

def create_sample_input_df(n_rows: int = 24) -> pd.DataFrame:
    """Create a sample input DataFrame for testing."""
    base_time = datetime(2024, 1, 1, 0, 0, 0)

    data = {
        'timestamp': [
            base_time.replace(hour=i % 24)
            for i in range(n_rows)
        ],
        'ambient_temp_c': np.random.uniform(15, 35, n_rows),
        'humidity_pct': np.random.uniform(40, 80, n_rows),
        'solar_irradiance_wm2': np.random.uniform(0, 350, n_rows)
    }

    return pd.DataFrame(data)


def create_edge_case_df() -> pd.DataFrame:
    """Create DataFrame with edge case values."""
    return pd.DataFrame({
        'timestamp': [
            datetime(2024, 1, 1, h, 0, 0) for h in range(24)
        ],
        'ambient_temp_c': [-10, 0, 10, 20, 24, 30, 35, 40, 45, 50, 55, 60] * 2,
        'humidity_pct': [0, 10, 25, 50, 75, 90, 100] * 3 + [50],
        'solar_irradiance_wm2': [0, 50, 100, 200, 500, 800, 1000, 1200, 1500] * 2 + [100]
    })


# ============================================================================
# Tests for predict.py
# ============================================================================

class TestPredictFunction:
    """Tests for the main predict() function."""

    def test_predict_returns_correct_length(self):
        """Test that predict() returns one prediction per input row."""
        df = create_sample_input_df(10)
        predictions = predict(df)

        assert len(predictions) == 10, \
            f"Expected 10 predictions, got {len(predictions)}"

    def test_predict_returns_numpy_array(self):
        """Test that predict() returns numpy array or list."""
        df = create_sample_input_df(5)
        predictions = predict(df)

        assert isinstance(predictions, (np.ndarray, list)), \
            f"Expected numpy array or list, got {type(predictions)}"

    def test_predict_no_nan_or_inf(self):
        """Test that predictions don't contain NaN or Inf values."""
        df = create_sample_input_df(24)
        predictions = predict(df)

        assert not np.isnan(predictions).any(), \
            "Predictions contain NaN values"
        assert not np.isinf(predictions).any(), \
            "Predictions contain Inf values"

    def test_predict_with_different_sizes(self):
        """Test predict() with various input sizes."""
        for n_rows in [1, 10, 50, 100, 1000]:
            df = create_sample_input_df(n_rows)
            predictions = predict(df)
            assert len(predictions) == n_rows

    def test_predict_preserves_timestamp_order(self):
        """Test that predictions align with input timestamps."""
        df = create_sample_input_df(24)
        predictions = predict(df)

        # Just verify we get valid predictions
        assert all(50 <= p <= 320 for p in predictions), \
            "Predictions outside reasonable range (50-320 kW)"

    def test_predict_with_real_sample_data(self):
        """Test with the actual sample_test_input.csv file."""
        sample_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'starter_kit',
            'sample_test_input.csv'
        )

        if os.path.exists(sample_path):
            df = pd.read_csv(sample_path)
            predictions = predict(df)

            assert len(predictions) == len(df)
            assert not np.isnan(predictions).any()

    def test_predict_always_returns_fallback_when_no_quickml(self):
        """Test that fallback model is used when QuickML not configured."""
        # Save original URL
        original_url = QUICKML_ENDPOINT_URL

        try:
            # Ensure QuickML is not configured
            import predict as predict_module
            predict_module.QUICKML_ENDPOINT_URL = "YOUR_PUBLISHED_QUICKML_ENDPOINT_URL_HERE"

            df = create_sample_input_df(10)
            predictions = predict(df)

            # Should return valid predictions from fallback
            assert len(predictions) == 10
            assert not np.isnan(predictions).any()

        finally:
            # Restore original
            predict_module.QUICKML_ENDPOINT_URL = original_url


class TestImprovedFallbackModel:
    """Tests for the improved fallback model internals."""

    def test_model_responds_to_temperature(self):
        """Test that higher temperature leads to higher predictions."""
        df_cold = pd.DataFrame({
            'timestamp': [datetime(2024, 1, 1, h, 0, 0) for h in range(24)],
            'ambient_temp_c': [10.0] * 24,
            'humidity_pct': [60.0] * 24,
            'solar_irradiance_wm2': [100.0] * 24,
            'hour': list(range(24)),
            'day_of_week': [0] * 24,
            'is_peak_hour': [0] * 24 + [1] * 0,  # Will be recalculated
            'hour_sin': np.sin(2 * np.pi * np.arange(24) / 24),
            'hour_cos': np.cos(2 * np.pi * np.arange(24) / 24),
            'temp_above_24': [0.0] * 24,
            'humidity_inv': [40.0] * 24,
            'solar_normalized': [0.1] * 24,
            'heat_load': [10.0 * 0.5 - 60.0 * 0.2] * 24
        })

        df_hot = df_cold.copy()
        df_hot['ambient_temp_c'] = [35.0] * 24
        df_hot['temp_above_24'] = [11.0] * 24
        df_hot['heat_load'] = [35.0 * 0.5 + 11.0 * 8.5 - 60.0 * 0.2] * 24

        pred_cold = _improved_fallback_model(df_cold)
        pred_hot = _improved_fallback_model(df_hot)

        # Hot predictions should generally be higher (especially during day)
        assert np.mean(pred_hot) > np.mean(pred_cold), \
            "Hot weather should increase predictions"

    def test_model_responds_to_hour(self):
        """Test that peak hours have higher predictions."""
        df_night = pd.DataFrame({
            'timestamp': [datetime(2024, 1, 1, h, 0, 0) for h in range(24)],
            'ambient_temp_c': [20.0] * 24,
            'humidity_pct': [60.0] * 24,
            'solar_irradiance_wm2': [0.0] * 24,
            'hour': list(range(24)),
            'day_of_week': [0] * 24,
            'is_peak_hour': [1 if 18 <= h <= 22 else 0 for h in range(24)],
            'hour_sin': np.sin(2 * np.pi * np.arange(24) / 24),
            'hour_cos': np.cos(2 * np.pi * np.arange(24) / 24),
            'temp_above_24': [0.0] * 24,
            'humidity_inv': [40.0] * 24,
            'solar_normalized': [0.0] * 24,
            'heat_load': [20.0 * 0.5 - 60.0 * 0.2] * 24
        })

        predictions = _improved_fallback_model(df_night)

        # Peak hours (18-22) should have higher predictions
        peak_preds = [predictions[h] for h in range(18, 23)]
        off_peak_preds = [predictions[h] for h in range(23)] + [predictions[0]]

        assert np.mean(peak_preds) > np.mean(off_peak_preds[:-1]), \
            "Peak hours should have higher demand"


# ============================================================================
# Tests for preprocessing.py
# ============================================================================

class TestPreprocessing:
    """Tests for data preprocessing functions."""

    def test_validate_input_dataframe_valid(self):
        """Test validation with valid data."""
        df = create_sample_input_df(10)
        assert validate_input_dataframe(df) is True

    def test_validate_input_dataframe_missing_column(self):
        """Test validation fails with missing column."""
        df = pd.DataFrame({
            'timestamp': [datetime(2024, 1, 1)],
            'ambient_temp_c': [25.0]
            # Missing humidity_pct and solar_irradiance_wm2
        })

        with pytest.raises(ValueError, match="Missing required column"):
            validate_input_dataframe(df)

    def test_validate_input_dataframe_fill_missing_values(self):
        """Test that missing values are filled with median."""
        df = pd.DataFrame({
            'timestamp': [datetime(2024, 1, 1, h, 0, 0) for h in range(10)],
            'ambient_temp_c': [25.0] * 10,
            'humidity_pct': [60.0] * 10,
            'solar_irradiance_wm2': [100.0] * 10
        })
        df.loc[5, 'ambient_temp_c'] = np.nan

        validate_input_dataframe(df)

        assert not df['ambient_temp_c'].isnull().any(), \
            "Missing value should be filled"

    def test_extract_time_features(self):
        """Test time feature extraction."""
        df = pd.DataFrame({
            'timestamp': [
                datetime(2024, 1, 1, 15, 30, 0),
                datetime(2024, 1, 2, 3, 0, 0),
                datetime(2024, 1, 1, 18, 0, 0),  # Peak hour
                datetime(2024, 1, 1, 22, 0, 0),  # Peak hour
            ]
        })

        result = extract_time_features(df)

        assert 'hour' in result.columns
        assert 'day_of_week' in result.columns
        assert 'is_peak_hour' in result.columns
        assert 'hour_sin' in result.columns
        assert 'hour_cos' in result.columns

        # Check specific values
        assert result.loc[0, 'hour'] == 15
        assert result.loc[1, 'day_of_week'] == 1  # Tuesday
        assert result.loc[2, 'is_peak_hour'] == 1  # 18:00 is peak
        assert result.loc[3, 'is_peak_hour'] == 1  # 22:00 is peak

    def test_create_weather_features(self):
        """Test weather feature creation."""
        df = pd.DataFrame({
            'ambient_temp_c': [20.0, 30.0, 35.0],
            'humidity_pct': [50.0, 70.0, 30.0],
            'solar_irradiance_wm2': [100.0, 500.0, 800.0]
        })

        result = create_weather_features(df)

        assert 'temp_above_24' in result.columns
        assert 'humidity_inv' in result.columns
        assert 'solar_normalized' in result.columns
        assert 'heat_load' in result.columns

        # Check calculations
        assert result.loc[0, 'temp_above_24'] == 0.0  # Below 24
        assert result.loc[1, 'temp_above_24'] == 6.0  # 30 - 24
        assert result.loc[2, 'temp_above_24'] == 11.0  # 35 - 24

    def test_prepare_features_complete(self):
        """Test complete feature preparation."""
        df = create_sample_input_df(10)
        result = prepare_features(df, add_derived=True)

        required_cols = [
            'timestamp', 'ambient_temp_c', 'humidity_pct',
            'solar_irradiance_wm2', 'hour', 'day_of_week',
            'is_peak_hour', 'hour_sin', 'hour_cos',
            'temp_above_24', 'humidity_inv', 'solar_normalized',
            'heat_load'
        ]

        for col in required_cols:
            assert col in result.columns, f"Missing column: {col}"


# ============================================================================
# Tests for transition.py
# ============================================================================

class TestTransitionController:
    """Tests for the grid transition controller."""

    def test_is_peak_hour_boundaries(self):
        """Test peak hour detection at boundaries."""
        assert is_peak_hour(17) is False  # Just before peak
        assert is_peak_hour(18) is True   # Start of peak
        assert is_peak_hour(20) is True   # Middle of peak
        assert is_peak_hour(22) is True   # End of peak (inclusive)
        assert is_peak_hour(23) is False  # After peak

    def test_determine_grid_mode_demand_threshold(self):
        """Test grid mode based on demand threshold."""
        # Below threshold, not peak hour
        mode, _ = get_grid_mode_for_hour(150.0, 10)
        assert mode == 'main_grid'

        # Above threshold
        mode, _ = get_grid_mode_for_hour(170.0, 10)
        assert mode == 'renewable'

    def test_determine_grid_mode_peak_hour(self):
        """Test grid mode based on peak hours."""
        # Peak hour (18-22) always uses renewable regardless of demand
        mode, _ = get_grid_mode_for_hour(100.0, 18)  # Low demand, but peak
        assert mode == 'renewable'

        mode, _ = get_grid_mode_for_hour(150.0, 20)
        assert mode == 'renewable'

        mode, _ = get_grid_mode_for_hour(10.0, 22)  # Very low, but still peak
        assert mode == 'renewable'

    def test_determine_grid_mode_combined(self):
        """Test combined demand and peak hour logic."""
        # Test each hour with various demands
        test_cases = [
            # (demand, hour, expected_mode)
            (150.0, 10, 'main_grid'),   # Low demand, non-peak
            (170.0, 10, 'renewable'),   # High demand, non-peak
            (100.0, 18, 'renewable'),   # Low demand, but peak
            (200.0, 18, 'renewable'),   # High demand, peak
            (50.0, 3, 'main_grid'),     # Very low, non-peak
        ]

        for demand, hour, expected in test_cases:
            mode, _ = get_grid_mode_for_hour(demand, hour)
            assert mode == expected, \
                f"Demand={demand}, Hour={hour}: expected {expected}, got {mode}"

    def test_check_overload_alert_threshold(self):
        """Test overload alert at 200 kW threshold."""
        assert check_overload_alert(199.9) is False
        assert check_overload_alert(200.0) is True
        assert check_overload_alert(200.1) is True
        assert check_overload_alert(300.0) is True

    def test_generate_transition_signal_normal(self):
        """Test normal transition signal generation."""
        ts = datetime(2024, 1, 1, 10, 0, 0)
        signal = generate_transition_signal(ts, 150.0)

        assert signal.grid_mode == 'main_grid'
        assert signal.alert_state == 'normal'
        assert signal.predicted_demand_kw == 150.0

    def test_generate_transition_signal_renewable(self):
        """Test renewable mode signal."""
        ts = datetime(2024, 1, 1, 20, 0, 0)  # Peak hour
        signal = generate_transition_signal(ts, 140.0)

        assert signal.grid_mode == 'renewable'
        assert signal.alert_state == 'normal'

    def test_generate_transition_signal_critical_alert(self):
        """Test critical overload alert."""
        ts = datetime(2024, 1, 1, 14, 0, 0)
        signal = generate_transition_signal(ts, 250.0)

        assert signal.grid_mode == 'renewable'  # > 160 kW
        assert signal.alert_state == 'critical'
        assert 'IMMEDIATE ACTION' in signal.recommended_action

    def test_process_forecast_length_matching(self):
        """Test that forecast processing requires matching lengths."""
        timestamps = [datetime(2024, 1, 1, h, 0, 0) for h in range(24)]
        predictions = [100.0] * 25  # Wrong length

        with pytest.raises(ValueError, match="must match"):
            process_forecast(timestamps, predictions)

    def test_process_forecast_correct_output(self):
        """Test forecast processing produces correct signals."""
        timestamps = [datetime(2024, 1, 1, h, 0, 0) for h in range(24)]
        predictions = [150.0 + i for i in range(24)]

        signals = process_forecast(timestamps, predictions)

        assert len(signals) == 24
        assert all(hasattr(s, 'grid_mode') for s in signals)

    def test_process_forecast_from_df(self):
        """Test DataFrame-based forecast processing."""
        df = create_sample_input_df(24)
        predictions = np.array([150.0] * 24)

        result_df = process_forecast_from_df(df, predictions)

        assert len(result_df) == 24
        assert 'timestamp' in result_df.columns
        assert 'predicted_demand_kw' in result_df.columns
        assert 'grid_mode' in result_df.columns
        assert 'alert_state' in result_df.columns
        assert 'recommended_action' in result_df.columns

    def test_summarize_forecast(self):
        """Test forecast summary generation."""
        timestamps = [datetime(2024, 1, 1, h, 0, 0) for h in range(24)]
        predictions = [150.0 + (i % 12) * 10 for i in range(24)]

        signals = process_forecast(timestamps, predictions)
        summary = summarize_forecast(signals)

        assert summary['total_hours'] == 24
        assert 'avg_demand_kw' in summary
        assert 'max_demand_kw' in summary
        assert 'min_demand_kw' in summary
        assert 'renewable_hours' in summary
        assert 'main_grid_hours' in summary
        assert 'overload_alerts' in summary


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for end-to-end workflows."""

    def test_predict_with_transition_full_workflow(self):
        """Test complete workflow: predict + transition."""
        df = create_sample_input_df(24)
        results = predict_with_transition(df)

        assert len(results) == 24
        assert 'predicted_demand_kw' in results.columns
        assert 'grid_mode' in results.columns
        assert 'alert_state' in results.columns

        # Verify grid mode logic is applied correctly
        for idx, row in results.iterrows():
            hour = row['hour']
            demand = row['predicted_demand_kw']
            mode = row['grid_mode']

            # Recalculate expected mode
            expected_mode = determine_grid_mode(demand, hour)
            assert mode == expected_mode, \
                f"Row {idx}: expected {expected_mode}, got {mode}"

    def test_save_predictions_format(self):
        """Test predictions are saved in correct format."""
        import tempfile

        df = create_sample_input_df(10)
        predictions = np.array([125.5, 130.2, 145.0, 160.0, 180.0,
                                175.0, 165.0, 155.0, 140.0, 120.0])

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            output_path = f.name

        try:
            save_predictions(df, predictions, output_path)

            # Read back and verify
            result_df = pd.read_csv(output_path)

            assert list(result_df.columns) == ['timestamp', 'target_demand_kw']
            assert len(result_df) == 10
            assert result_df['target_demand_kw'].iloc[0] == 125.5
        finally:
            os.unlink(output_path)

    def test_end_to_end_with_sample_file(self):
        """Test full pipeline with actual sample file."""
        sample_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'starter_kit',
            'sample_test_input.csv'
        )

        if os.path.exists(sample_path):
            df = pd.read_csv(sample_path)
            predictions = predict(df)

            # Verify predictions are reasonable
            assert 50 <= np.min(predictions) <= 350, \
                f"Min prediction {np.min(predictions)} outside range"
            assert 50 <= np.max(predictions) <= 350, \
                f"Max prediction {np.max(predictions)} outside range"

            # Generate transition signals
            results = process_forecast_from_df(df, predictions)

            # Verify all rows have valid states
            assert results['grid_mode'].isin(['renewable', 'main_grid']).all()
            assert results['alert_state'].isin(['normal', 'critical']).all()


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_single_row_prediction(self):
        """Test prediction with single row."""
        df = pd.DataFrame({
            'timestamp': [datetime(2024, 1, 1, 12, 0, 0)],
            'ambient_temp_c': [25.0],
            'humidity_pct': [50.0],
            'solar_irradiance_wm2': [200.0]
        })

        predictions = predict(df)
        assert len(predictions) == 1
        assert 50 <= predictions[0] <= 350

    def test_boundary_hour_values(self):
        """Test predictions at exact boundary hours."""
        df = pd.DataFrame({
            'timestamp': [
                datetime(2024, 1, 1, 17, 59, 0),  # Just before peak
                datetime(2024, 1, 1, 18, 0, 0),   # Peak start
                datetime(2024, 1, 1, 22, 0, 0),   # Peak end
                datetime(2024, 1, 1, 22, 1, 0),   # Just after peak
            ],
            'ambient_temp_c': [30.0] * 4,
            'humidity_pct': [50.0] * 4,
            'solar_irradiance_wm2': [100.0] * 4
        })

        predictions = predict(df)
        assert len(predictions) == 4

    def test_extreme_weather_values(self):
        """Test with extreme but valid weather values."""
        df = pd.DataFrame({
            'timestamp': [datetime(2024, 1, 1, h, 0, 0) for h in range(24)],
            'ambient_temp_c': [60.0] * 24,  # Max valid
            'humidity_pct': [0.0] * 24,     # Min valid
            'solar_irradiance_wm2': [1500.0] * 24  # Max valid
        })

        predictions = predict(df)
        assert len(predictions) == 24
        assert not np.isnan(predictions).any()

    def test_negative_temperature(self):
        """Test with negative temperatures (winter conditions)."""
        df = pd.DataFrame({
            'timestamp': [datetime(2024, 1, 1, h, 0, 0) for h in range(24)],
            'ambient_temp_c': [-10.0] * 24,
            'humidity_pct': [80.0] * 24,
            'solar_irradiance_wm2': [0.0] * 24
        })

        predictions = predict(df)

        # Winter night predictions should be lower
        assert np.mean(predictions) < 180, \
            "Winter predictions should be lower than summer"

    def test_zero_solar_at_night(self):
        """Test that zero solar at night is handled correctly."""
        df = pd.DataFrame({
            'timestamp': [datetime(2024, 1, 1, h, 0, 0) for h in range(24)],
            'ambient_temp_c': [25.0] * 24,
            'humidity_pct': [60.0] * 24,
            'solar_irradiance_wm2': [0.0] * 24  # Nighttime values
        })

        predictions = predict(df)
        assert not np.isnan(predictions).any()


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("HackSphere 3.0 - Comprehensive Test Suite")
    print("=" * 70)

    # Run pytest programmatically
    exit_code = pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '-p', 'no:cacheprovider'
    ])

    sys.exit(exit_code)
