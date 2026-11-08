import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RuntimeDependencyContractTests(unittest.TestCase):
    def test_hugging_face_trainer_declares_accelerate_lower_bound(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        declarations = {
            line.split("#", 1)[0].strip().replace(" ", "").lower()
            for line in requirements.splitlines()
            if line.split("#", 1)[0].strip()
        }

        self.assertIn("accelerate>=0.26.0", declarations)

    def test_database_datezone_legacy_import_is_explicit_dependency(self):
        # DB_utils imports pytz at module scope; it is not consistently
        # installed by recent pandas versions.
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        declarations = {
            line.split("#", 1)[0].strip().replace(" ", "").lower()
            for line in requirements.splitlines()
            if line.split("#", 1)[0].strip()
        }
        self.assertIn("pytz", declarations)

    def test_stage4_pins_dash3_compatible_visdcc(self):
        # visdcc 0.0.50 imports a Dash 3-removed component loader.
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        declarations = {
            line.split("#", 1)[0].strip().replace(" ", "").lower()
            for line in requirements.splitlines()
            if line.split("#", 1)[0].strip()
        }
        self.assertIn("visdcc==0.0.63", declarations)
        self.assertIn("comm>=0.2.3", declarations)
        self.assertIn("jaal", declarations)

    def test_gpu_utility_dependency_declared_for_shared_utilities(self):
        # df_utils imports shared utilities, which unconditionally imports GPUtil.
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        declarations = {
            line.split("#", 1)[0].strip().replace(" ", "").lower()
            for line in requirements.splitlines()
            if line.split("#", 1)[0].strip()
        }
        self.assertIn("gputil", declarations)


if __name__ == "__main__":
    unittest.main()
