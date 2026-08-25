"""Dependency-light defaults used by the DatasetConverter composition root.

The wider ``TCF_Params.TCFParameters`` module parses command-line arguments and
loads multiprocessing/runtime helpers at import time.  DatasetConverter only
needs these two stable path names while it is being imported, so keep that
configuration slice independent from the application bootstrap. Mutable legacy
settings are created by a factory so callers never share nested containers.
"""

import math
import os
import platform
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


WORK_POOL_ROOT = "WorkPool"
DATASET_CONVERTER_ROOT = "DatasetConverter"


class ConfigValidationError(ValueError):
    """Raised when normalized converter settings are invalid."""


@dataclass(frozen=True)
class SplitConfig:
    """Normalized default dataset ratios."""

    train: float = 0.7
    validation: float = 0.2
    test: float = 0.1

    def __post_init__(self) -> None:
        ratios = {
            "Train": self.train,
            "Validation": self.validation,
            "Test": self.test,
        }
        for name, value in ratios.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ConfigValidationError(
                    f"{name} split ratio must be a finite non-negative number"
                )
        if not math.isclose(sum(ratios.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ConfigValidationError("split ratios must sum to 1.0")

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


class WorkMode(str, Enum):
    """Normalized optional workspace mode selected for this conversion."""

    STANDARD = "standard"
    WEITECH = "weitech"
    WEITECH_EXTRACTION = "weitech_extraction"


@dataclass(frozen=True)
class SourceConfig:
    """Immutable source routing inputs for one conversion run."""

    root_paths: tuple[str, ...]
    fixed_test_paths: tuple[str, ...]
    mode: SourceMode
    training_enabled: bool
    test_enabled: bool


@dataclass(frozen=True)
class ModeConfig:
    """Normalized CLI mode selection without retaining the argparse namespace."""

    source_mode: SourceMode
    work_mode: WorkMode
    wei_tech_work_id: str
    extraction_task: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_mode, SourceMode):
            raise ConfigValidationError("source_mode must be a SourceMode")
        if not isinstance(self.work_mode, WorkMode):
            raise ConfigValidationError("work_mode must be a WorkMode")
        if self.work_mode is WorkMode.STANDARD and self.wei_tech_work_id:
            raise ConfigValidationError("standard mode must not have a WeiTech work ID")
        if self.work_mode is not WorkMode.STANDARD and not self.wei_tech_work_id:
            raise ConfigValidationError("WeiTech mode requires a work ID")
        if (
            self.work_mode is WorkMode.WEITECH_EXTRACTION
            and not self.extraction_task
        ):
            raise ConfigValidationError("WeiTech extraction mode requires a task")
        if self.work_mode is WorkMode.WEITECH and self.extraction_task:
            raise ConfigValidationError("WeiTech mode with a task must enable extraction")

    @property
    def extraction_enabled(self) -> bool:
        return self.work_mode is WorkMode.WEITECH_EXTRACTION


def mode_config_from_namespace(args: Any, source_config: SourceConfig) -> ModeConfig:
    """Preserve legacy source precedence and WeiTech extraction activation."""

    if not isinstance(source_config, SourceConfig):
        raise ConfigValidationError("source_config must be a SourceConfig")
    work_id = args.WeiTechworkID
    extraction_task = args.ExtractionConverterTask
    for name, value in {
        "WeiTechworkID": work_id,
        "ExtractionConverterTask": extraction_task,
    }.items():
        if not isinstance(value, str):
            raise ConfigValidationError(f"{name} must be a string")
        if "\0" in value:
            raise ConfigValidationError(f"{name} must not contain a null byte")

    if not work_id:
        work_mode = WorkMode.STANDARD
    elif extraction_task:
        work_mode = WorkMode.WEITECH_EXTRACTION
    else:
        work_mode = WorkMode.WEITECH

    return ModeConfig(
        source_mode=source_config.mode,
        work_mode=work_mode,
        wei_tech_work_id=work_id,
        extraction_task=extraction_task,
    )


@dataclass(frozen=True)
class WorkspaceConfig:
    """Validated WeiTech workspace path slice for an optional work item."""

    work_pool_directory: str
    work_id: str

    def __post_init__(self) -> None:
        for name, value in {
            "WeiTechWorkPoolPATH": self.work_pool_directory,
            "WeiTechworkID": self.work_id,
        }.items():
            if not isinstance(value, str):
                raise ConfigValidationError(f"{name} must be a string")
            if "\0" in value:
                raise ConfigValidationError(f"{name} must not contain a null byte")
        if self.work_id:
            if not self.work_pool_directory:
                raise ConfigValidationError(
                    "WeiTechWorkPoolPATH is required when WeiTechworkID is set"
                )
            if self.work_id in {".", ".."} or "/" in self.work_id or "\\" in self.work_id:
                raise ConfigValidationError(
                    "WeiTechworkID must be a single path component"
                )

    @property
    def work_item_directory(self) -> str | None:
        if not self.work_id:
            return None
        return os.path.join(self.work_pool_directory, self.work_id)


def workspace_config_from_namespace(
    args: Any,
    mode_config: ModeConfig,
) -> WorkspaceConfig:
    """Normalize the WeiTech workspace slice and verify mode consistency."""

    if not isinstance(mode_config, ModeConfig):
        raise ConfigValidationError("mode_config must be a ModeConfig")
    config = WorkspaceConfig(
        work_pool_directory=args.WeiTechWorkPoolPATH,
        work_id=mode_config.wei_tech_work_id,
    )
    if (config.work_id != "") != (mode_config.work_mode is not WorkMode.STANDARD):
        raise ConfigValidationError("workspace and mode config must select the same work mode")
    return config


@dataclass(frozen=True)
class OutputConfig:
    """Normalized stage directories and canonical dataset artifact stems."""

    dataset_directory: str
    database_subdirectory: str
    dataset_stem: str = field(default="dataset_total_with_filename", init=False)

    def __post_init__(self) -> None:
        values = {
            "dataset directory": self.dataset_directory,
            "database subdirectory": self.database_subdirectory,
            "dataset stem": self.dataset_stem,
        }
        for name, value in values.items():
            if not isinstance(value, str):
                raise ConfigValidationError(f"{name} must be a string")
            if "\0" in value:
                raise ConfigValidationError(f"{name} must not contain a null byte")
        if not self.dataset_directory:
            raise ConfigValidationError("dataset directory must not be empty")
        if not self.dataset_stem:
            raise ConfigValidationError("dataset stem must not be empty")

    @property
    def database_directory(self) -> str:
        return os.path.join(self.dataset_directory, self.database_subdirectory)

    @property
    def output_main(self) -> str:
        return os.path.join(self.database_directory, self.dataset_stem)

    @property
    def labels_count_output(self) -> str:
        return self.output_main.replace("_with_filename", "") + "_labels_count"

    @property
    def fixed_test_output(self) -> str:
        return self.output_main + "_FixedTest"


@dataclass(frozen=True)
class RuntimeConfig:
    """Validated process counts discovered by the activated runtime adapter."""

    worker_processes: int
    large_output_processes: int

    def __post_init__(self) -> None:
        values = {
            "worker process count": self.worker_processes,
            "large-output process count": self.large_output_processes,
        }
        for name, value in values.items():
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ConfigValidationError(f"{name} must be a positive integer")


DEFAULT_RUNTIME_CONFIG = RuntimeConfig(
    worker_processes=1,
    large_output_processes=1,
)


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
    split: SplitConfig
    reader_settings: Mapping[str, Any]

    @classmethod
    def from_legacy_settings(
        cls,
        settings: Mapping[str, Any],
        *,
        fixed_test_file_bound: int,
        split: SplitConfig = DEFAULT_SPLIT_CONFIG,
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
        if not isinstance(split, SplitConfig):
            raise ConfigValidationError("split must be a SplitConfig")
        return cls(
            width=width,
            mode=str(mode),
            tokenization_wrap=bool(tokenization_wrap),
            convert_to_spec=str(convert_to_spec),
            fixed_test_file_bound=fixed_test_file_bound,
            split=split,
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
