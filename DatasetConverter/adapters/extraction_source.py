"""Feature-activated adapters for legacy extraction and corpus conversion."""

from collections.abc import MutableMapping
from typing import Any


def get_extraction_rule(task: str) -> MutableMapping[str, Any]:
    """Return the legacy mutable rule selected for ``task``.

    Identity is intentionally preserved because the canonical stage adds its
    working directory to the selected rule before invoking the extractor.
    """

    from DatasetConverter.EXTConverter.ExtractionRule import ExtractionRuleDict

    return ExtractionRuleDict[task]


def run_extraction(task: str, *, job_info: MutableMapping[str, Any]) -> Any:
    """Invoke the legacy extractor only when an extraction task is enabled."""

    from DatasetConverter.EXTConverter.ExtractionConverter import Extractor

    return Extractor(task=task, FileNameInSQL3=False, JobInfo=job_info)


def build_czj_corpus(*, source_path: str, output_path: str) -> Any:
    """Convert a WeiTech sample database through the legacy corpus builder."""

    from DatasetConverter.EXTConverter.Combiner import CZJCorpusFileBuilder

    return CZJCorpusFileBuilder(
        SourceCZJSampleFN=source_path,
        OutputCZJCorpusFN=output_path,
    ).Transformer()
