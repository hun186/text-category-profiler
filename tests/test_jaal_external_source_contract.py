"""Guard source-of-truth boundary after migration to external Jaal package.

No runtime dependency is needed to statically inspect the manifest. The
focused Jaal CI always installs the pinned distribution and runs live checks.
"""
from __future__ import annotations

import importlib.metadata as metadata
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JAAL_SHA = "7a7d8ba1f847b2f95a620c61a0c5a94f0523e255"
JAAL_URL = "git+https://github.com/hun186/jaal-topology-viewer.git@" + JAAL_SHA


class ExternalJaalSourceTests(unittest.TestCase):
    def test_requirements_pin_exact_released_repository_commit(self):
        reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        entries = [
            line.strip()
            for line in reqs.splitlines()
            if line.strip().startswith("jaal-topology-viewer @ ")
        ]
        self.assertEqual(
            entries, ["jaal-topology-viewer @ " + JAAL_URL]
        )
        self.assertNotIn("jaal-topology-viewer @ git+https://github.com/"
                         "hun186/jaal-topology-viewer.git@main", reqs)

    def test_original_stage4_does_not_load_or_reference_source_checkout(self):
        source = (ROOT / "BertScript/jaal_original_mount.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("run_path(", source)
        self.assertNotIn("PORTABLE_JAAL_DIR", source)
        self.assertNotIn("packages/jaal-topology", source)
        self.assertIn("from jaal_topology.modes import layout_options", source)
        self.assertIn("from jaal_topology import ASSETS_DIR", source)
        self.assertFalse((ROOT / "packages" / "jaal-topology").exists())

    def test_installed_distribution_provenance_if_available(self):
        if importlib.util.find_spec("jaal_topology") is None:
            self.skipTest("External Jaal package not installed: focused CI installs pin")
        import jaal_topology
        import jaal_topology.modes
        installed = Path(jaal_topology.__file__).resolve()
        self.assertFalse(installed.is_relative_to(ROOT / "packages"))
        self.assertTrue(jaal_topology.ASSETS_DIR.is_dir())
        self.assertTrue(callable(jaal_topology.modes.layout_options))
        for name in ("16.jaal_visible_labels.js",
                     "17.jaal_structural_collapse.js", "bootstrap.min.css"):
            self.assertTrue((jaal_topology.ASSETS_DIR / name).is_file())
        dist = metadata.distribution("jaal-topology-viewer")
        self.assertEqual(dist.version, "0.1.0")
        direct_url = dist.read_text("direct_url.json")
        self.assertIsNotNone(
            direct_url, "Must use fixed Git VCS package, not an unpinned wheel"
        )
        provenance = json.loads(direct_url)
        self.assertEqual(
            provenance.get("vcs_info", {}).get("commit_id"), JAAL_SHA
        )


if __name__ == "__main__":
    unittest.main()
