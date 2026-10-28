"""Legacy Elasticsearch job-template module.

Re-evaluate the canonical dictionary for each module execution, matching
the historical import/reload/runpy behavior: TCP_ELASTIC_PASSWORD is read at
that execution's environment snapshot. No Elasticsearch client is initialized.
"""
from pathlib import Path
from runpy import run_path

_CONFIG_PATH = Path(__file__).resolve().parent / "integrations" / "es_job_template.py"
esJobTemplate = run_path(str(_CONFIG_PATH))["esJobTemplate"]

__all__ = ["esJobTemplate"]
