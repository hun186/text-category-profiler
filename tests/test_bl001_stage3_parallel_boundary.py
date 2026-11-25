"""Isolated Stage 3 parallel pool ownership and compatibility contracts."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock

from BertScript.result_combination_parallel import parallelize_chunks


class Stage3ParallelBoundaryTests(unittest.TestCase):
    def fixture(self):
        events = []
        pool = Mock()
        pool.map.side_effect = lambda fn, chunks: events.append("map") or [fn(x) for x in chunks]
        pool.close.side_effect = lambda: events.append("close")
        pool.join.side_effect = lambda: events.append("join")
        pool.terminate.side_effect = lambda: events.append("terminate")
        split = Mock(side_effect=lambda data, count: events.append("split") or list(data))
        factory = Mock(side_effect=lambda count: events.append("pool") or pool)
        concat = Mock(side_effect=lambda rows: events.append("concat") or tuple(rows))
        return events, pool, split, factory, concat

    def invoke(self, split, factory, concat):
        return parallelize_chunks([2, 1, 2], lambda x: x * 2, 3,
                                  split=split, pool_factory=factory,
                                  concatenate=concat)

    def test_success_preserves_order_and_graceful_shutdown(self):
        events, pool, split, factory, concat = self.fixture()
        self.assertEqual(self.invoke(split, factory, concat), (4, 2, 4))
        self.assertEqual(events, ["split", "pool", "map", "concat", "close", "join"])
        factory.assert_called_once_with(3)
        split.assert_called_once_with([2, 1, 2], 3)
        pool.terminate.assert_not_called()

    def test_failures_reap_pool_and_preserve_original_exception(self):
        for failing in ("map", "concat", "close", "join"):
            with self.subTest(failing=failing):
                _, pool, split, factory, concat = self.fixture()
                error = RuntimeError(failing)
                target = concat if failing == "concat" else getattr(pool, failing)
                target.side_effect = error
                with self.assertRaises(RuntimeError) as raised:
                    self.invoke(split, factory, concat)
                self.assertIs(raised.exception, error)
                pool.terminate.assert_called_once_with()
                self.assertGreaterEqual(pool.join.call_count, 1)

    def test_interrupt_and_cleanup_errors_keep_primary(self):
        _, pool, split, factory, concat = self.fixture()
        interrupt = KeyboardInterrupt()
        pool.map.side_effect = interrupt
        pool.terminate.side_effect = OSError("cleanup")
        pool.join.side_effect = OSError("cleanup")
        with self.assertRaises(KeyboardInterrupt) as raised:
            self.invoke(split, factory, concat)
        self.assertIs(raised.exception, interrupt)
        pool.terminate.assert_called_once_with()
        pool.join.assert_called_once_with()

    def test_split_failure_does_not_acquire_pool(self):
        _, pool, split, factory, concat = self.fixture()
        split.side_effect = ValueError("split")
        with self.assertRaises(ValueError):
            self.invoke(split, factory, concat)
        factory.assert_not_called()

    def test_legacy_wrapper_passes_original_dependencies(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] /
                          "BertScript/CombineTestResult.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "parallelize")
        helper = Mock(return_value="result")
        np, pd, pool = Mock(), Mock(), Mock()
        namespace = {"parallelize_chunks": helper, "np": np, "pd": pd, "Pool": pool}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<wrapper>", "exec"),
             namespace)
        function = lambda x: x
        self.assertEqual(namespace["parallelize"]("data", function), "result")
        helper.assert_called_once_with("data", function, 8, split=np.array_split,
                                       pool_factory=pool, concatenate=pd.concat)


if __name__ == "__main__":
    unittest.main()
