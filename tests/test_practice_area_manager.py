import unittest
from law_functions.practice_area_functions import PracticeAreaManager

class TestPracticeAreaManager(unittest.TestCase):
    def setUp(self):
        self.manager = PracticeAreaManager()

    def test_get_practice_area_details(self):
        result = self.manager.get_practice_area_details()
        self.assertIsNotNone(result)
        if result:
            self.assertIn("area_code", result)
            self.assertIn("name", result)

    def test_get_practice_area_attorneys(self):
        # First get practice area
        area = self.manager.get_practice_area_details()
        if area:
            attorneys = self.manager.get_practice_area_attorneys(area["practice_area_id"])
            self.assertIsInstance(attorneys, list)

if __name__ == "__main__":
    unittest.main()