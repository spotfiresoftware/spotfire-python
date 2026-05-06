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
report_suffix = ""
report_name = f"{platform.system().lower()}-{PYTHON_VERSION}"
if TEST_ENVIRONMENT:
    report_suffix = f" ({TEST_ENVIRONMENT} test environment)"
    report_name += f"-{TEST_ENVIRONMENT}"
runner = HtmlTestRunner.HTMLTestRunner(combine_reports=True,
                                       output="build/test-results/",
                                       template=utils.get_test_data_file("template.html.in"),
                                       report_title=f"Python {PYTHON_VERSION} on {platform.system()}{report_suffix}",
                                       report_name=report_name,
                                       add_timestamp=False)
unittest.main(testRunner=runner, failfast=False, buffer=False, catchbreak=False)
