import unittest
from parser import matches

class ParserTests(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(matches('ok', 'ok'))

    def test_strip_regression(self):
        self.assertTrue(matches(' ok ', 'ok'))

if __name__ == '__main__':
    unittest.main()
