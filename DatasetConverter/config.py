"""Dependency-light defaults used by the DatasetConverter composition root.

The wider ``TCF_Params.TCFParameters`` module parses command-line arguments and
loads multiprocessing/runtime helpers at import time.  DatasetConverter only
needs these two stable path names while it is being imported, so keep that
configuration slice independent from the application bootstrap. Mutable legacy
settings are created by a factory so callers never share nested containers.
"""

import math
import platform
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


WORK_POOL_ROOT = "WorkPool"
DATASET_CONVERTER_ROOT = "DatasetConverter"


@dataclass(frozen=True)
class SplitConfig:
    """Normalized default dataset ratios."""

    train: float = 0.7
    validation: float = 0.2
    test: float = 0.1

    def as_legacy_mapping(self) -> dict[str, float]:
        return {
            "Train": self.train,
            "Validation": self.validation,
            "Test": self.test,
        }


DEFAULT_SPLIT_CONFIG = SplitConfig()
REMOVE_DUPLICATE_FIXED_TEST_ARTICLES = False
RESTRICTED_LABEL_MODE = False
DATA_AUGMENTATION_GOAL = 3
STATISTICS_ENABLED = False


LINUX_ROOT_PATHS = (
    "News/THUCNews",
    "News/AFPBB",
    "News/HuffPost",
    "Kaggle",
    "BigDataWarehouse",
    "===DRNData",
    "Books",
    "C_GoogleSearch",
    "C_wikisourcePortal",
)


class SourceMode(str, Enum):
    """Normalized source-root selection mode."""

    TRAINING_DISABLED = "training_disabled"
    DEBUG = "debug"
    DRN_ONLY = "drn_only"
    LINUX = "linux"
    LINUX_WITH_MALICIOUS_DOMAIN = "linux_with_malicious_domain"
    NON_LINUX = "non_linux"


@dataclass(frozen=True)
class SourceConfig:
    """Immutable source routing inputs for one conversion run."""

    root_paths: tuple[str, ...]
    fixed_test_paths: tuple[str, ...]
    mode: SourceMode
    training_enabled: bool
    test_enabled: bool


class ConfigValidationError(ValueError):
    """Raised when normalized converter settings are invalid."""


def _freeze_setting(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_setting(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_setting(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_setting(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_setting(item) for item in value)
    return value


def _thaw_setting(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_setting(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_setting(item) for item in value]
    if isinstance(value, frozenset):
        return {_thaw_setting(item) for item in value}
    return value


@dataclass(frozen=True)
class ConverterConfig:
    """Immutable core reader settings with a legacy mapping adapter."""

    width: int
    mode: str
    tokenization_wrap: bool
    convert_to_spec: str
    fixed_test_file_bound: int
    reader_settings: Mapping[str, Any]

    @classmethod
    def from_legacy_settings(
        cls,
        settings: Mapping[str, Any],
        *,
        fixed_test_file_bound: int,
    ) -> "ConverterConfig":
        remaining = dict(settings)
        width = remaining.pop("WIDTH")
        mode = remaining.pop("Mode")
        tokenization_wrap = remaining.pop("tokenizationWrap")
        convert_to_spec = remaining.pop("ConvertToSpec")
        if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
            raise ConfigValidationError("WIDTH must be a positive integer")
        if not isinstance(fixed_test_file_bound, int) or isinstance(
            fixed_test_file_bound, bool
        ) or fixed_test_file_bound < 0:
            raise ConfigValidationError(
                "FixedTestFileBound must be a non-negative integer"
            )
        return cls(
            width=width,
            mode=str(mode),
            tokenization_wrap=bool(tokenization_wrap),
            convert_to_spec=str(convert_to_spec),
            fixed_test_file_bound=fixed_test_file_bound,
            reader_settings=_freeze_setting(remaining),
        )

    def as_legacy_mapping(self) -> dict[str, Any]:
        settings = _thaw_setting(self.reader_settings)
        settings.update({
            "WIDTH": self.width,
            "Mode": self.mode,
            "tokenizationWrap": self.tokenization_wrap,
            "ConvertToSpec": self.convert_to_spec,
            "FixedTestFileBound": self.fixed_test_file_bound,
        })
        return settings


def source_config_from_namespace(
    args: Any,
    *,
    fixed_test_paths: tuple[str, ...] = (),
    system_name: str | None = None,
) -> SourceConfig:
    """Normalize source routing without activating application bootstrap."""

    if not args.train:
        roots = ()
        mode = SourceMode.TRAINING_DISABLED
    elif args.debugMode:
        roots = ("TopicTextCrawler/TrainSamples",)
        mode = SourceMode.DEBUG
    elif args.TrainDRNDataOnly:
        roots = ("===DRNData",)
        mode = SourceMode.DRN_ONLY
    elif "linux" in (system_name or platform.system()).lower():
        roots_list = list(LINUX_ROOT_PATHS)
        if args.trainWithMaliciousDomainDataset:
            roots_list.append("惡意網址分析")
            mode = SourceMode.LINUX_WITH_MALICIOUS_DOMAIN
        else:
            mode = SourceMode.LINUX
        roots = tuple(roots_list)
    else:
        roots = ("TrainSamples",)
        mode = SourceMode.NON_LINUX

    return SourceConfig(
        root_paths=roots,
        fixed_test_paths=tuple(fixed_test_paths),
        mode=mode,
        training_enabled=bool(args.train),
        test_enabled=bool(getattr(args, "test", False)),
    )


def root_paths_from_namespace(
    args: Any,
    *,
    system_name: str | None = None,
) -> tuple[str, ...]:
    """Return legacy input roots without activating ``TCFParameters``.

    Platform detection is injectable so the policy can be characterized without
    mutating process-wide state.
    """

    return source_config_from_namespace(
        args,
        system_name=system_name,
    ).root_paths


def default_converter_settings() -> dict:
    """Return a fresh legacy settings mapping for one conversion run."""

    width = 256
    return {
        "WIDTH": width,
        "Mode": "FullCut",
        "tokenizationWrap": True,
        "ConvertToSpec": "tw2sp",
        "sampleMethod": {
            "nBound": {
                "default": 5000,
                "Economist": 1000,
                "Scrap": 256 * 200 // width,
            },
            "RandomSample": True,
            "LenLBD": 1,
        },
        "TreeBinaryTarget": None,
        "UniqueLabel": True,
        "UniqueSortedLabels": True,
        "OnlyLettersDigitsLabels": False,
        "RBDict": {
            (r"\w*?@.*?\.\w{2,3}", (max(width / 40, 6), math.inf)):
                "Email Header-Email Address",
            (r"\w*?@huawei.com", (max(width / 40, 6), math.inf)):
                "Huawei Email Address",
            (
                r"^\w{0,5}.{0,3}\w{12,26}\.cloudfront\.net/{0,1}$",
                (1, math.inf),
            ): "CDN Web Link-CloudFront",
        },
        "RBActive": True,
        "DataCleanerRePatternDict": {
            "EmailAddress Remover": {
                "SrcPat": [
                    r"(?:(\w{,20}\.){0,}\w{,20}@\w{1,20}?\.[^@]{2,20}){0,}(?:(\w{,20}\.){0,}\w{,20}@\w{1,20}?\.[^@]{2,3})",
                    r"(.{1}件人|抄送)(?:.{1,20}(com|;)){1,}",
                    r"From(?:.{1,30};){1,}",
                ],
                "ReplacedResult": "",
                "ExemptInLabelList": [
                    "Email Header-Email Address",
                    "Email Header",
                ],
            },
            "&nbsp Remover": {
                "SrcPat": ["&nbsp;", "&nbsp"],
                "ReplacedResult": " ",
            },
        },
    }
