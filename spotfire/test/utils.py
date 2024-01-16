"""Utility classes for integrating unit test results into Jenkins."""


import inspect
import os


def get_test_data_file(name: str) -> str:
    """Determine the filename of a test data file.  It is possible for the data files to be separated from the
    ``spotfire.test.files`` package, especially for testing binary wheels in the CI environment; to look in an
    alternate location, set the ``TEST_FILES_DIR`` environment variable.

    :param name: the basename of the test file
    :return: the full filename of the test file
    """
    test_dir, _ = os.path.split(inspect.stack()[1].filename)
    files_dir = os.getenv("TEST_FILES_DIR", os.path.join(test_dir, "files"))
    return os.path.join(files_dir, name)
