import unittest
from calculator import add

class CalculatorTests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(add(2, 0), 2)

    def test_add_regression(self):
        self.assertEqual(add(1, 2), 3)

if __name__ == '__main__':
    unittest.main()
