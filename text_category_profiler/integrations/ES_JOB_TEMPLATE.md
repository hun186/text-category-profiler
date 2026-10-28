# Elasticsearch job-template configuration

`es_job_template.py` is the canonical location for the legacy ArtClu
Elasticsearch job-template dictionary. The source is copied byte-for-byte
from `text_category_profiler/ArtCluESJobTemplate.py` to preserve the existing
keys, default values, and import-time environment-variable snapshot:

- `esJobTemplate["es_tokens"]["password"]` reads `TCP_ELASTIC_PASSWORD`
  when first imported (and remains `None` if unset).
- `es_tokens.host` defaults to `https://localhost:9200`; the historical
  `user` and all other template fields remain unchanged.
- No HTTP client is created and no ES connection is made by importing either
  the canonical or old module.
- The old module path re-exports the **same mutable dictionary instance**,
  not a separately reloaded configuration.

Treat the template as *legacy optional configuration*, not a verified
production Elasticsearch service or credentials provider. Never commit real
password values; use the environment variable at the caller's runtime. The
original behavior is intentionally unchanged, including its import-time
snapshot semantics. This move does not validate an ES server or rotate any
previously exposed credentials.

Targeted no-service tests:
`python -m unittest -v tests.test_es_job_template_boundary`.
