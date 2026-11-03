"""Reviewed upstream production pin with real Stage 4 release-mode coverage.

The default is five modes only on the exact upstream merged commit;
flag 0 explicitly preserves the original four-mode rollback.
"""
from __future__ import annotations

import importlib.metadata as metadata
import json
import os
from pathlib import Path
import unittest

CANDIDATE_SHA = "47942ac3bd08d8cbcc615fa215c5e5eef286f486"
CANDIDATE_SHA_EXPECTED = CANDIDATE_SHA
BASELINE_SHA = "7a7d8ba1f847b2f95a620c61a0c5a94f0523e255"
RELEASE_SHA = "47942ac3bd08d8cbcc615fa215c5e5eef286f486"
ROOT = Path(__file__).resolve().parents[1]
LEGACY_MODES = (
    "network", "network-collapsed",
    "hierarchical", "hierarchical-collapsed",
)
COMMUNITY_MODE = "network-community-collapsed"


@unittest.skipUnless(
    os.environ.get("JAAL_CANDIDATE_COMPAT") == "1",
    "Release integration tests require isolated official Jaal install in CI",
)
class CandidateJaalIntegrationTests(unittest.TestCase):
    def test_provenance_and_approved_production_pin(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn(
            "jaal-topology-viewer @ git+https://github.com/"
            "hun186/jaal-topology-viewer.git@" + RELEASE_SHA,
            requirements,
        )
        self.assertNotIn(
            "jaal-topology-viewer @ git+https://github.com/"
            "hun186/jaal-topology-viewer.git@" + BASELINE_SHA,
            requirements,
        )
        dist = metadata.distribution("jaal-topology-viewer")
        source = dist.read_text("direct_url.json")
        self.assertIsNotNone(source, "This CI requires exact VCS provenance")
        self.assertEqual(
            json.loads(source)["vcs_info"]["commit_id"], CANDIDATE_SHA,
        )

    def test_upstream_fifth_mode_and_original_four_mode_contract(self):
        from jaal_topology import ASSETS_DIR
        from jaal_topology.modes import layout_options
        from BertScript.jaal_original_mount import (
            PORTABLE_JS_FILES, _jaal_layout_options,
        )

        self.assertEqual(
            PORTABLE_JS_FILES,
            ("16.jaal_visible_labels.js", "17.jaal_structural_collapse.js"),
            "The original structural assets remain available for rollback",
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


    def test_stage4_opt_in_community_context_cycles_dag_and_duplicate_pairs(self):
        from types import SimpleNamespace
        from unittest import mock
        from BertScript.jaal_original_mount import (
            _community_candidate_enabled, _community_candidate_context,
            CANDIDATE_ENV, CANDIDATE_SHA,
        )
        self.assertEqual(CANDIDATE_SHA, CANDIDATE_SHA_EXPECTED)
        with mock.patch.dict(os.environ, {CANDIDATE_ENV: "0"}):
            self.assertFalse(_community_candidate_enabled())
        with mock.patch.dict(os.environ, {CANDIDATE_ENV: "1"}):
            self.assertTrue(_community_candidate_enabled())
        with mock.patch.dict(os.environ):
            os.environ.pop(CANDIDATE_ENV, None)
            self.assertTrue(
                _community_candidate_enabled(),
                "Official upstream merge must enable Louvain by default",
            )

        def context(edges):
            ids = sorted({value for a, b in edges for value in (a, b)})
            network = SimpleNamespace(
                id="graph",
                data={"nodes": [{"id": x} for x in ids],
                      "edges": [{"from": a, "to": b} for a, b in edges]},
                children=None,
            )
            return _community_candidate_context(
                SimpleNamespace(children=[network])
            )

        cyclic = context([("A", "B"), ("B", "C"), ("C", "A"), ("A", "B")])
        self.assertFalse(cyclic["eligible"])
        self.assertEqual(cyclic["kind"], "cyclic")
        self.assertEqual(set(cyclic["membership"]), {"A", "B", "C"})

        dag = context([("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")])
        self.assertTrue(dag["eligible"])
        self.assertEqual(dag["kind"], "dag")
        self.assertEqual(dag["multi_parent"], 1)
        self.assertIsInstance(cyclic["quotient_cycle"], bool)
        self.assertIsInstance(dag["quotient_cycle"], bool)

    def test_real_original_jaal_can_mount_fifth_mode_with_exact_candidate(self):
        from unittest import mock
        import pandas as pd
        from jaal import Jaal
        from BertScript.jaal_original_mount import (
            prefix_original_jaal, CANDIDATE_ENV,
        )
        edges = pd.DataFrame({
            "from": ["A", "B", "C", "A"],
            "to": ["B", "C", "A", "B"],
            "strength": ["medium"] * 4,
        })
        nodes = pd.DataFrame({
            "id": ["A", "B", "C"],
            "Positivity": ["Pos", "Neu", "Neg"],
        })
        original = Jaal(edges, nodes).create(directed=True)
        with mock.patch.dict(os.environ, {CANDIDATE_ENV: "1"}):
            child = prefix_original_jaal(original, "/candidate-stage4/")
        client = child.server.test_client()
        body = client.get("/").get_data(as_text=True)
        self.assertIn("18.jaal_community_collapse.js", body)
        self.assertEqual(
            client.get("/assets/18.jaal_community_collapse.js").status_code,
            200,
        )
        layout = client.get("/_dash-layout")
        self.assertEqual(layout.status_code, 200)
        props = {}

        def walk(node):
            if isinstance(node, dict):
                p = node.get("props", {})
                if isinstance(p.get("id"), str):
                    props[p["id"]] = p
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(layout.get_json())
        modes = {
            opt["value"]: opt
            for opt in props["jaal-original-layout-mode"]["options"]
        }
        self.assertEqual(len(modes), 5)
        self.assertFalse(modes["network-community-collapsed"].get("disabled", False))
        self.assertTrue(modes["network-collapsed"]["disabled"])
        self.assertTrue(modes["hierarchical-collapsed"]["disabled"])
        self.assertFalse(props["jaal-structural-eligible"]["data"])
        self.assertIn(
            "社群彙總圖",
            props["jaal-original-community-cycle-hint"]["children"],
        )
        self.assertEqual(set(props["jaal-community-membership"]["data"]),
                         {"A", "B", "C"})
        deps = client.get("/_dash-dependencies").get_json()
        run = next(row for row in deps if row["output"] == "graph.run")
        self.assertEqual(
            {item["id"] for item in run["inputs"]},
            {"graph", "jaal-original-layout-mode", "jaal-original-chinese-labels",
             "jaal-original-ct-translations", "jaal-community-membership",
             "jaal-structural-eligible"},
        )

    def test_standalone_five_modes_and_release_mode(self):
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
