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


if __name__ == "__main__":
    unittest.main()
