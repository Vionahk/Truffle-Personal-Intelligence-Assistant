import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.memory_manager import MemoryManager


class TestMemoryManager(unittest.TestCase):
    def test_save_and_load_profile(self):
        mm = MemoryManager(data_dir=".")
        profile = {"personal": {"full_name": "Test User"}, "emergency_contacts": []}
        mm.save_user_profile(profile)
        loaded = mm.load_user_profile()
        self.assertEqual(loaded.get("personal", {}).get("full_name"), "Test User")


if __name__ == '__main__':
    unittest.main()
