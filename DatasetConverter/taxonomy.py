"""Dependency-light taxonomy validation for DatasetConverter."""

import os
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Tuple


@dataclass(frozen=True)
class TaxonomyConfig:
    """Normalized input needed by the taxonomy file adapter."""

    source_files: Tuple[str, ...]
    source_directory: str
    record_directory: str


@dataclass(frozen=True)
class TaxonomyValidation:
    """Normalized taxonomy labels and their validation outcome."""

    labels: Tuple[str, ...]
    missing_info_score_labels: Tuple[str, ...]

    @property
    def is_binary(self) -> bool:
        return set(self.labels) == {"Negative", "Positive"}


@dataclass(frozen=True)
class LoadedTaxonomy:
    """Named result returned by the filesystem-backed taxonomy loader."""

    tree: Any
    info_score_table: Mapping[str, Any]
    validation: TaxonomyValidation


def taxonomy_config_from_namespace(args: Any) -> TaxonomyConfig:
    """Map the legacy argparse namespace to an immutable taxonomy config."""

    source_files = tuple(
        item.strip() for item in args.TopicTreeFiles.split(",") if item.strip()
    )
    return TaxonomyConfig(
        source_files=source_files,
        source_directory=args.TopicTreeDir,
        record_directory=os.path.join(args.BertDatasetSubDir, "OnlyForRecord"),
    )


def load_taxonomy(
    config: TaxonomyConfig,
    loader: Callable[..., Tuple[Any, Mapping[str, Any]]],
) -> LoadedTaxonomy:
    """Run an injected filesystem adapter and validate its taxonomy result."""

    tree, info_score_table = loader(
        TreeBaseFNList=list(config.source_files),
        OutputPath=config.record_directory,
        TreeSourceDir=config.source_directory,
    )
    return LoadedTaxonomy(
        tree=tree,
        info_score_table=info_score_table,
        validation=validate_taxonomy(tree, info_score_table),
    )


def validate_taxonomy(
    tree: Iterable[Iterable[str]], info_score_labels: Iterable[str]
) -> TaxonomyValidation:
    """Normalize tree labels and report labels absent from the score table."""

    labels = tuple(sorted({label for branch in tree for label in branch}))
    available_labels = set(info_score_labels)
    missing_labels = tuple(label for label in labels if label not in available_labels)
    return TaxonomyValidation(
        labels=labels,
        missing_info_score_labels=missing_labels,
    )
