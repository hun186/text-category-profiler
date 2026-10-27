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
