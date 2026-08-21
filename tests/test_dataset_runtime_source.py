import sys
import types
import unittest
from unittest.mock import patch

from DatasetConverter.adapters import runtime_source


class RuntimeSourceTests(unittest.TestCase):
    def test_runtime_contracts_are_forwarded_lazily(self):
        calls = []

        def constructor(name):
            def invoke(*args, **kwargs):
                calls.append((name, args, kwargs))
                return name
            return invoke

        concurrency = types.ModuleType("text_category_profiler.concurrency.MP_utils")
        concurrency.MPlogger = constructor("logger")
        concurrency.multicoreJob = constructor("multicore")
        dataframe = types.ModuleType("text_category_profiler.data.df_utils")
        dataframe.dfOutputer = constructor("output")
        dataframe.DictRowsListToDF = constructor("rows")
        database = types.ModuleType("text_category_profiler.data.DB_utils")
        database.getESData = constructor("es")

        modules = {
            concurrency.__name__: concurrency,
            dataframe.__name__: dataframe,
            database.__name__: database,
        }
        with patch.dict(sys.modules, modules):
            self.assertEqual(runtime_source.create_logger("log", quiet=True), "logger")
            self.assertEqual(runtime_source.create_multicore_job([1], nProcess=2), "multicore")
            self.assertEqual(runtime_source.create_dataframe_output("df", OMFN="out"), "output")
            self.assertEqual(runtime_source.dataframe_from_rows([{"a": 1}]), "rows")
            self.assertEqual(runtime_source.fetch_elasticsearch_data({"index": "x"}), "es")

        self.assertEqual([call[0] for call in calls], ["logger", "multicore", "output", "rows", "es"])
        self.assertEqual(calls[0][1], ("log",))
        self.assertEqual(calls[0][2], {"quiet": True})
        self.assertEqual(calls[-1][1], ({"index": "x"},))


if __name__ == "__main__":
    unittest.main()
