"""Dependency-light defaults used by the DatasetConverter composition root.

The wider ``TCF_Params.TCFParameters`` module parses command-line arguments and
loads multiprocessing/runtime helpers at import time.  DatasetConverter only
needs these two stable path names while it is being imported, so keep that
configuration slice independent from the application bootstrap. Mutable legacy
settings are created by a factory so callers never share nested containers.
"""

import math
from dataclasses import dataclass


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
