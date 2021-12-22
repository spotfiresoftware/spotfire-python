"""Run unit tests from the command line and output a JUnit-compatible result file.

$ python -m spotfire.test
"""

import sys
import unittest
import xmlrunner

from spotfire.test import utils

TEST_MODULES = ['spotfire.test.test_sbdf', 'spotfire.test.test_data_function']


# noinspection PyUnusedLocal
def load_tests(loader, tests, pattern):  # pylint: disable=unused-argument
    """Create a test suite containing all known modules in the 'spotfire.test' package."""
    test_suite = unittest.TestSuite()
    for module in TEST_MODULES:
        test_suite.addTests(loader.loadTestsFromName(module))
    return test_suite


if len(sys.argv) > 1:
    name = sys.argv[1]
else:
    name = utils.PYTHON_VERSION
with open(f"results-{name}.xml", "wb") as output:
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output=output, resultclass=utils.PythonVersionModifiedResult),
                  failfast=False, buffer=False, catchbreak=False)
