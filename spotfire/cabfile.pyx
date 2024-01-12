# cython: language_level=3

# Copyright © 2023. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Tools to create Microsoft cabinet files.  Only defined on Windows platforms."""


class CabFile:
    """Class with methods to open, write, and close Microsoft cabinet files."""
    def __init__(self, file: str) -> None:
        """Open the cabinet file.

        :param file: filename of the cabinet file
        """
        raise OSError("Cabinet files not supported on non-Win32 platforms")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
