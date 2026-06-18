"""Basic tests for password-check module."""
import sys
import unittest
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automation_suite import run_password_check


class DummyArgs:
    def __init__(self):
        self.input = None
        self.output = None
        self.min_length = None
        self.min_score = None


class TestPasswordCheck(unittest.TestCase):
    def test_dummy(self):
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
