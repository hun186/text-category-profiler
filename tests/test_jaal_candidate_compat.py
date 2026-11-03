"""Isolated Stage 4 compatibility characterization of exact PR #5 candidate.

Production requirements retain their separately reviewed older pin. This is
not a downstream upgrade or proof of human Windows browser acceptance.
"""
from __future__ import annotations

import importlib.metadata as metadata
import json
import os
from pathlib import Path
import unittest

CANDIDATE_SHA = "3e9355851357326ac0e47848b8cef64b50bf1b83"
BASELINE_SHA = "7a7d8ba1f847b2f95a620c61a0c5a94f0523e255"
ROOT = Path(__file__).resolve().parents[1]
LEGACY_MODES = (
    "network", "network-collapsed",
    "hierarchical", "hierarchical-collapsed",
)
COMMUNITY_MODE = "network-community-collapsed"


@unittest.skipUnless(
    os.environ.get("JAAL_CANDIDATE_COMPAT") == "1",
    "Candidate-only check: keep normal lightweight discovery and production pin intact",
)
class CandidateJaalIntegrationTests(unittest.TestCase):
    def test_provenance_and_no_production_pin_change(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn(
            "jaal-topology-viewer @ git+https://github.com/"
            "hun186/jaal-topology-viewer.git@" + BASELINE_SHA,
            requirements,
        )
        self.assertNotIn(
            "jaal-topology-viewer @ git+https://github.com/"
            "hun186/jaal-topology-viewer.git@" + CANDIDATE_SHA,
            requirements,
        )
        dist = metadata.distribution("jaal-topology-viewer")
        source = dist.read_text("direct_url.json")
        self.assertIsNotNone(source, "This CI requires exact VCS provenance")
        self.assertEqual(
            json.loads(source)["vcs_info"]["commit_id"], CANDIDATE_SHA,
        )

    def test_upstream_fifth_mode_and_existing_stage4_remain_separate(self):
        from jaal_topology import ASSETS_DIR
        from jaal_topology.modes import layout_options
        from BertScript.jaal_original_mount import (
            PORTABLE_JS_FILES, _jaal_layout_options,
        )

        self.assertEqual(
            PORTABLE_JS_FILES,
            ("16.jaal_visible_labels.js", "17.jaal_structural_collapse.js"),
            "The existing Stage 4 still intentionally exposes its four modes",
        )
        for filename in (*PORTABLE_JS_FILES, "18.jaal_community_collapse.js"):
            self.assertTrue((ASSETS_DIR / filename).is_file(), filename)
        base = {"physics": {"enabled": True}, "edges": {"arrows": {"to": True}}}
        for mode in LEGACY_MODES:
            self.assertEqual(_jaal_layout_options(base, mode),
                             layout_options(base, mode), mode)
        new = layout_options(base, COMMUNITY_MODE)
        self.assertFalse(new["layout"]["hierarchical"]["enabled"])
        self.assertTrue(new["physics"]["enabled"])
        self.assertNotIn("layout", base, "Upstream must not mutate caller config")

    def test_graph_type_detection_and_cyclic_safety_on_current_candidate(self):
        from jaal_topology.data import Graph, assess_structural_collapse
        from jaal_topology.viewer import build_app

        tree = Graph((("A", "B"),), ("A", "B"))
        forest = Graph((("A", "B"), ("C", "D")), ("A", "B", "C", "D"))
        dag = Graph(
            (("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")),
            ("A", "B", "C", "D"),
        )
        cyclic = Graph((("A", "B"), ("B", "A")), ("A", "B"))
        self.assertEqual(
            [assess_structural_collapse(x).graph_kind
             for x in (tree, forest, dag, cyclic)],
            ["tree", "forest", "dag", "cyclic"],
        )
        app = build_app(cyclic)
        response = app.server.test_client().get("/_dash-layout")
        self.assertEqual(response.status_code, 200)
        found = {}

        def collect(item):
            if isinstance(item, dict):
                props = item.get("props", {})
                if isinstance(props.get("id"), str):
                    found[props["id"]] = props
                for child in item.values():
                    collect(child)
            elif isinstance(item, list):
                for child in item:
                    collect(child)

        collect(response.get_json())
        options = {
            option["value"]: option
            for option in found["jaal-original-layout-mode"]["options"]
        }
        self.assertTrue(options["network-collapsed"]["disabled"])
        self.assertTrue(options["hierarchical-collapsed"]["disabled"])
        self.assertFalse(options[COMMUNITY_MODE].get("disabled", False))
        self.assertEqual(found["jaal-structural-eligible"]["data"], False)
        self.assertIn(
            "一般有環網路", found["jaal-original-graph-profile"]["children"],
        )

    def test_standalone_five_modes_and_original_stage4_four_modes(self):
        from jaal_topology.data import Graph
        from jaal_topology.viewer import build_app
        graph = Graph(
            (("Root", "Child"), ("Child", "Another")),
            ("Another", "Child", "Root"),
            {"Root": "根"},
        )
        app = build_app(graph)
        response = app.server.test_client().get("/_dash-layout")
        self.assertEqual(response.status_code, 200)
        found = {}

        def walk(value):
            if isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, dict):
                props = value.get("props", {})
                if isinstance(props.get("id"), str):
                    found[props["id"]] = props
                for nested in value.values():
                    walk(nested)

        walk(response.get_json())
        options = found["jaal-original-layout-mode"]["options"]
        self.assertEqual(
            [opt["value"] for opt in options],
            [LEGACY_MODES[0], LEGACY_MODES[1], COMMUNITY_MODE,
             LEGACY_MODES[2], LEGACY_MODES[3]],
        )
        self.assertIn("jaal-community-membership", found)
        self.assertIn("Root", found["jaal-community-membership"]["data"])
        self.assertEqual(
            app.server.test_client().get(
                "/assets/18.jaal_community_collapse.js"
            ).status_code, 200,
        )


if __name__ == "__main__":
    unittest.main()
