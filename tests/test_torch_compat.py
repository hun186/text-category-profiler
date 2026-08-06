import unittest

from text_category_profiler.core.torch_compat import disable_unsupported_windows_compile


class FakeTorch:
    @staticmethod
    def compile(model=None, **kwargs):
        raise RuntimeError("Windows not yet supported for torch.compile")


class TorchCompatibilityTests(unittest.TestCase):
    def test_windows_compile_decorator_falls_back_to_eager_function(self):
        torch_module = FakeTorch()

        changed = disable_unsupported_windows_compile(torch_module, system="Windows")

        self.assertTrue(changed)

        @torch_module.compile(dynamic=True)
        def model(value):
            return value + 1

        self.assertEqual(model(2), 3)

    def test_windows_direct_compile_falls_back_to_original_model(self):
        torch_module = FakeTorch()
        disable_unsupported_windows_compile(torch_module, system="Windows")
        model = object()

        self.assertIs(torch_module.compile(model, backend="inductor"), model)

    def test_non_windows_compile_is_unchanged(self):
        torch_module = FakeTorch()
        original_compile = torch_module.compile

        changed = disable_unsupported_windows_compile(torch_module, system="Linux")

        self.assertFalse(changed)
        self.assertIs(torch_module.compile, original_compile)


if __name__ == "__main__":
    unittest.main()
