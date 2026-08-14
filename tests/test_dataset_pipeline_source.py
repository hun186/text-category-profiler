import sys
import types
import unittest
from unittest.mock import patch

from DatasetConverter.adapters.pipeline_source import connect_task
from DatasetConverter.adapters.pipeline_source import fixed_test_paths
from DatasetConverter.adapters.pipeline_source import parse_converter_options
from DatasetConverter.adapters.pipeline_source import pick_dataset_directories
from DatasetConverter.adapters.pipeline_source import resolve_base_model_checkpoint
from DatasetConverter.adapters.pipeline_source import restricted_labels


class DatasetPipelineSourceTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        calls = self.calls

        class Picker:
            def __init__(self, **kwargs):
                calls.append(("picker-init", kwargs))

            def proc(self):
                calls.append(("picker-proc",))
                return ("dataset", "model")

        class Connector:
            def __init__(self, **kwargs):
                calls.append(("connector-init", kwargs))

            def proc(self):
                calls.append(("connector-proc",))
                return "connected"

        self.module = types.ModuleType("text_category_profiler.pipeline.TCF_utils")
        self.module.ClassfierOptionParser = (
            lambda argv=None: calls.append(("parse", argv)) or "args"
        )
        self.module.datasetDirOutputDirPickers = Picker
        self.module.get_base_model_checkpoint = (
            lambda model_type: calls.append(("model", model_type)) or "checkpoint"
        )
        self.module.GetRSTRLabelList = (
            lambda enabled: calls.append(("restricted", enabled)) or ["label"]
        )
        self.module.TaskConnector = Connector
        self.data_converter_module = types.ModuleType(
            "text_category_profiler.pipeline.DataConverter_utils"
        )
        self.data_converter_module.GetFixedTestPATH = (
            lambda args: calls.append(("fixed-test", args)) or ["fixed"]
        )

    def test_parser_model_and_restricted_label_forwarding(self):
        with patch.dict(sys.modules, {self.module.__name__: self.module}):
            self.assertEqual(parse_converter_options(["--test", "true"]), "args")
            self.assertEqual(resolve_base_model_checkpoint("PytorchXLM"), "checkpoint")
            self.assertEqual(restricted_labels(False), ["label"])

        self.assertEqual(
            self.calls,
            [
                ("parse", ["--test", "true"]),
                ("model", "PytorchXLM"),
                ("restricted", False),
            ],
        )

    def test_directory_picker_preserves_constructor_and_proc_contract(self):
        args = object()
        with patch.dict(sys.modules, {self.module.__name__: self.module}):
            result = pick_dataset_directories(
                args=args,
                ready_for_stage="DataConverter",
            )

        self.assertEqual(result, ("dataset", "model"))
        self.assertEqual(
            self.calls,
            [
                (
                    "picker-init",
                    {"args": args, "rdy_for_stage": "DataConverter"},
                ),
                ("picker-proc",),
            ],
        )

    def test_task_connector_preserves_handoff_keywords_and_proc(self):
        with patch.dict(sys.modules, {self.module.__name__: self.module}):
            result = connect_task(
                source_task="DataConverter",
                destination_task="RunClassfier",
                working_directory="dataset",
                log_file="TCFMain.log",
            )

        self.assertEqual(result, "connected")
        self.assertEqual(
            self.calls,
            [
                (
                    "connector-init",
                    {
                        "SrcTask": "DataConverter",
                        "DesTask": "RunClassfier",
                        "WorkingDir": "dataset",
                        "logFile": "TCFMain.log",
                    },
                ),
                ("connector-proc",),
            ],
        )

    def test_fixed_test_discovery_is_forwarded_at_runtime(self):
        args = object()
        with patch.dict(
            sys.modules,
            {self.data_converter_module.__name__: self.data_converter_module},
        ):
            self.assertEqual(fixed_test_paths(args), ["fixed"])
        self.assertEqual(self.calls, [("fixed-test", args)])


if __name__ == "__main__":
    unittest.main()
