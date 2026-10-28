"""Legacy import alias for the Elasticsearch job template.

Authoritative settings: text_category_profiler.integrations.es_job_template.
Import preserves the original environment snapshot and mutable dictionary API.
No Elasticsearch client is initialized here.
"""
from text_category_profiler.integrations.es_job_template import esJobTemplate

__all__ = ["esJobTemplate"]
