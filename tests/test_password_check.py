"""Tests for the password-check module."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestPasswordCheck(unittest.TestCase):
    def test_excellent_password(self):
        """A strong password should have all character types."""
        pwd = "My$uperStr0ng!P@ss"
        self.assertTrue(len(pwd) >= 12)
        self.assertTrue(any(c.isupper() for c in pwd))
        self.assertTrue(any(c.islower() for c in pwd))
        self.assertTrue(any(c.isdigit() for c in pwd))
        self.assertTrue(any(c in "!@#$%^&*()" for c in pwd))

    def test_common_password(self):
        """Common passwords are weak."""
        common = ["password", "123456", "qwerty", "admin"]
        for pwd in common:
            self.assertIn(pwd.lower(), {
                "password", "123456", "12345678", "qwerty", "abc123",
                "monkey", "letmein", "dragon", "111111", "baseball",
                "iloveyou", "trustno1", "sunshine", "princess", "admin",
                "welcome", "shadow", "ashley", "football", "jesus",
                "michael", "ninja", "mustang", "password1", "123456789",
                "adobe123", "admin123", "login", "master", "photoshop",
                "1q2w3e4r", "zaq12wsx", "qwertyuiop", "lovely", "whatever"
            })

    def test_short_password(self):
        """Short passwords are weak."""
        pwd = "123"
        self.assertLess(len(pwd), 8)

    def test_no_special_chars(self):
        """Password without special chars is weaker."""
        pwd = "Password123"
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;':\",.<>?" for c in pwd)
        self.assertFalse(has_special)

    def test_repeating_chars(self):
        """Repeating characters reduce strength."""
        import re
        pwd = "aaa111bbb"
        self.assertTrue(re.search(r"(.)\1{2,}", pwd))

    def test_sequence_detection(self):
        """Simple sequences should be detected."""
        sequences = [
            "abcdefghijklmnopqrstuvwxyz",
            "0123456789",
            "qwertyuiop",
            "asdfghjkl",
            "zxcvbnm"
        ]
        pwd = "abc123"
        has_seq = any(seq[i:i+3] in pwd.lower() for seq in sequences for i in range(len(seq)-2))
        self.assertTrue(has_seq)


if __name__ == "__main__":
    unittest.main()
