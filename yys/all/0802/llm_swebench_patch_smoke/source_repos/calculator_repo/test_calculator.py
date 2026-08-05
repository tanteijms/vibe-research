import unittest
from calculator import add

class CalculatorTests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(add(2, 0), 2)

if __name__ == '__main__':
    unittest.main()
