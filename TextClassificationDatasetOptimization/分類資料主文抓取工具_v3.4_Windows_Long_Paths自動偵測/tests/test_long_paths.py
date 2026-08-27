import unittest

import scrape_articles


class FakeWinreg:
    HKEY_LOCAL_MACHINE = object()
    KEY_READ = 0x20019

    def __init__(self, value=1, fail=False):
        self.value = value
        self.fail = fail
        self.opened = []

    class _Key:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    def OpenKey(self, root, path, reserved=0, access=0):
        if self.fail:
            raise OSError('registry unavailable')
        self.opened.append((root, path, reserved, access))
        return self._Key()

    def QueryValueEx(self, key, name):
        if self.fail:
            raise OSError('registry unavailable')
        if name != 'LongPathsEnabled':
            raise FileNotFoundError(name)
        return self.value, 4


class LongPathDetectionTests(unittest.TestCase):
    def test_detects_enabled_windows_long_paths(self):
        fake = FakeWinreg(value=1)
        self.assertTrue(
            scrape_articles.windows_long_paths_enabled(
                os_name='nt', winreg_module=fake
            )
        )

    def test_detects_disabled_windows_long_paths(self):
        fake = FakeWinreg(value=0)
        self.assertFalse(
            scrape_articles.windows_long_paths_enabled(
                os_name='nt', winreg_module=fake
            )
        )

    def test_non_windows_is_not_treated_as_windows_long_paths(self):
        self.assertFalse(
            scrape_articles.windows_long_paths_enabled(
                os_name='posix', winreg_module=FakeWinreg(value=1)
            )
        )

    def test_registry_error_falls_back_to_disabled(self):
        self.assertFalse(
            scrape_articles.windows_long_paths_enabled(
                os_name='nt', winreg_module=FakeWinreg(fail=True)
            )
        )


class MaxPathResolutionTests(unittest.TestCase):
    def test_auto_uses_zero_when_long_paths_enabled(self):
        self.assertEqual(
            scrape_articles.resolve_max_path_chars(None, long_paths_enabled=True),
            0,
        )

    def test_auto_uses_240_when_long_paths_disabled(self):
        self.assertEqual(
            scrape_articles.resolve_max_path_chars(None, long_paths_enabled=False),
            240,
        )

    def test_explicit_value_overrides_detection(self):
        self.assertEqual(
            scrape_articles.resolve_max_path_chars(220, long_paths_enabled=True),
            220,
        )
        self.assertEqual(
            scrape_articles.resolve_max_path_chars(0, long_paths_enabled=False),
            0,
        )


if __name__ == '__main__':
    unittest.main()
