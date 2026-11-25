"""Characterize active Stage 4 scoring policies without importing Dash."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from BertScript.visualization_scoring import (
    rating_stars, score_sum_interval, score_mean_interval,
)


class Stage4ScoringTests(unittest.TestCase):
    def test_sum_thresholds_and_exact_legacy_labels(self):
        cases = [
            (-2001, "B1. <-2000"), (-2000, "B2. -2000~-501"),
            (-501, "B2. -2000~-501"), (-500, "B3. -500~-1"),
            (-1, "B3. -500~-1"), (0, "G1. 0~499"),
            (499, "G1. 0~499"), (500, "G2. 500~999"),
            (999, "G2. 500~999"), (1000, "G3. 1000~1999"),
            (1999, "G3. 1000~1999"), (2000, "G4. 2000~2999"),
            (2999, "G4. 2000~2999"), (3000, "G5. 3000~3999"),
            (3999, "G5. 3000~3999"), (4000, "G6. 4000~5000"),
            (4999, "G6. 4000~5000"), (5000, "G7. 5000+"),
        ]
        for score, expected in cases:
            with self.subTest(score=score):
                self.assertEqual(score_sum_interval(score), expected)

    def test_mean_thresholds_and_exact_legacy_labels(self):
        bands = [
            (-200, "B2. -200~-100"), (-100, "B3. -100~-50"),
            (-50, "B4. -50~0"), (0, "G1. 0~40"),
            (40, "G2. 40~70"), (70, "G3. 70~100"),
            (100, "G4. 100~130"), (130, "G5. 130~170"),
            (170, "G6. 170~200"), (200, "G7. 200~299"),
            (300, "G8. 300~499"), (500, "G9. 500+"),
        ]
        previous = "B1. <-200"
        for lower, expected in bands:
            with self.subTest(lower=lower):
                self.assertEqual(score_mean_interval(lower - 1), previous)
                self.assertEqual(score_mean_interval(lower), expected)
            previous = expected

    def test_rating_arithmetic_and_caps(self):
        for total, mean, stars in [(0, 100, 0), (999, 149, 0),
                                   (1000, 150, 3), (5000, 250, 11),
                                   (10000, 1000, 11), (-1000, 50, 0),
                                   (5000, 50, 3), (0, 99, 0)]:
            with self.subTest(total=total, mean=mean):
                self.assertEqual(rating_stars(total, mean), "⭐" * stars)

    def test_nan_intervals_keep_legacy_fallthrough(self):
        self.assertEqual(score_sum_interval(float("nan")), "B1. <-2000")
        self.assertEqual(score_mean_interval(float("nan")), "B1. <-200")

    def test_active_dataframe_wrappers_preserve_columns_and_worker_names(self):
        class Frame(dict):
            def apply(self, fn, axis):
                self.assert_axis = axis
                return fn(SimpleNamespace(InfoScoreSum=1000, InfoScoreMean=150,
                                          Selected="S", Target="T"))

        source = (Path(__file__).resolve().parents[1] /
                  "BertScript/Test_result_Vis.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {"CountRating", "PerformanceColExt"}
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in names]
        self.assertEqual({node.name for node in functions}, names)
        pd = SimpleNamespace(options=SimpleNamespace(
            mode=SimpleNamespace(chained_assignment="warn")))
        namespace = dict(pd=pd, rating_stars=rating_stars,
                         score_sum_interval=score_sum_interval,
                         score_mean_interval=score_mean_interval)
        exec(compile(ast.Module(body=functions, type_ignores=[]),
                     "<scoring-wrappers>", "exec"), namespace)
        frame = Frame()
        self.assertIs(namespace["CountRating"](frame), frame)
        self.assertIs(namespace["PerformanceColExt"](frame), frame)
        self.assertEqual(frame, {
            "Rating": "⭐⭐⭐", "InfoScoreSumInterval": "G3. 1000~1999",
            "InfoScoreMeanInterval": "G5. 130~170", "Recommanded": "推",
            "Selected": "送編", "Target": "目標",
        })
        self.assertEqual(frame.assert_axis, 1)
        self.assertEqual(pd.options.mode.chained_assignment, "warn")


if __name__ == "__main__":
    unittest.main()
