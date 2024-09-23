"""Run unit tests from the command line and output an HTML result file.

$ python -m spotfire.test
"""

import os
import platform
import sys
import unittest

import HtmlTestRunner

from spotfire.test import utils

TEST_MODULES = ['spotfire.test.test_cabfile',
                'spotfire.test.test_data_function',
                'spotfire.test.test_sbdf']


# noinspection PyUnusedLocal
def load_tests(loader, tests, pattern):  # pylint: disable=unused-argument
    """Create a test suite containing all known modules in the 'spotfire.test' package."""
    test_suite = unittest.TestSuite()
    for module in TEST_MODULES:
        test_suite.addTests(loader.loadTestsFromName(module))
    return test_suite


PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"
TEST_ENVIRONMENT = os.getenv("TEST_ENVIRONMENT")
REPORT_SUFFIX = ""
REPORT_NAME = f"{platform.system().lower()}-{PYTHON_VERSION}"
if TEST_ENVIRONMENT:
    REPORT_SUFFIX = f" ({TEST_ENVIRONMENT} test environment)"
    REPORT_NAME += f"-{TEST_ENVIRONMENT}"
runner = HtmlTestRunner.HTMLTestRunner(combine_reports=True,
                                       output="build/test-results/",
                                       template=utils.get_test_data_file("template.html.in"),
                                       report_title=f"Python {PYTHON_VERSION} on {platform.system()}{REPORT_SUFFIX}",
                                       report_name=REPORT_NAME,
                                       add_timestamp=False)
unittest.main(testRunner=runner, failfast=False, buffer=False, catchbreak=False)
