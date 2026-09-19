"""Compatibility exports for the production-owned full-pipeline diagnostics."""
from text_category_profiler.diagnostics.full_pipeline import *  # noqa: F401,F403
from text_category_profiler.diagnostics.full_pipeline import (  # noqa: F401
    _discover_fixed_test_dirs,
    _discover_model_dir,
)
