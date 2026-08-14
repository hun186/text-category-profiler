"""Elasticsearch integration adapters for DatasetConverter sources."""

from collections.abc import Mapping
from typing import Any


def create_elasticsearch_client(tokens: Mapping[str, Any]):
    """Create the legacy ES client only when an ES source is activated.

    Keeping the third-party import inside this integration factory allows
    filesystem and SQLite readers to load without requiring Elasticsearch.
    The caller remains responsible for closing the returned client.
    """

    from elasticsearch import Elasticsearch

    return Elasticsearch(
        tokens["host"],
        http_auth=(tokens["user"], tokens["password"]),
        verify_certs=False,
    )
