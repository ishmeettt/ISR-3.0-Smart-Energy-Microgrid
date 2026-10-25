#!/usr/bin/env python3
"""
HackSphere 3.0 - Main Entry Point for Prediction Module

This is the main predict.py that should be used for submission.
It imports from the src package and provides the same interface
as required by test_eval.py.

Usage:
    python predict.py --input sample_test_input.csv --output predictions.csv
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.predict import (
    predict,
    predict_with_transition,
    save_predictions,
    main as cli_main,
    QUICKML_ENDPOINT_URL
)

# Re-export for test_eval.py compatibility
__all__ = ['predict', 'predict_with_transition', 'save_predictions']

if __name__ == "__main__":
    cli_main()
