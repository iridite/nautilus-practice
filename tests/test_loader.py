"""
Tests for Config Loader
"""

import unittest

from core.loader import ConfigLoader


class TestConfigLoader(unittest.TestCase):
    def setUp(self):
        self.loader = ConfigLoader()

    def test_initialization(self):
        self.assertIsNotNone(self.loader.paths)

    def test_env_var_pattern(self):
        pattern = self.loader._env_var_pattern
        match = pattern.search("${TEST_VAR}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "TEST_VAR")


if __name__ == "__main__":
    unittest.main()
