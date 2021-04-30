# Copyright © 2021. TIBCO Software Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Utilities used by multiple submodules."""
import os
import tempfile


def type_name(type_: type) -> str:
    """Convert a type object to a string in a consistent manner.

    :param type_: the type object to convert
    :return: a string with the type name
    """
    type_qualname = type_.__qualname__
    type_module = type_.__module__
    if type_module not in ("__main__", "builtins"):
        type_qualname = type_module + '.' + type_qualname
    return type_qualname


class TempFiles:
    """Utility class that manages the lifecycle of multiple temporary files."""
    def __init__(self) -> None:
        self._files = []

    def new_file(self, **kwargs) -> tempfile.NamedTemporaryFile:
        """Create a temporary file object that will be tracked by this manager.

        :param kwargs: NamedTemporaryFile arguments
        :return: a new NamedTemporaryFile object
        """
        # pylint: disable=consider-using-with
        temp_file = tempfile.NamedTemporaryFile(delete=False, **kwargs)
        self._files.append(temp_file)
        return temp_file

    def cleanup(self) -> None:
        """Clean up all managed temporary files by deleting them."""
        for temp_file in self._files:
            os.unlink(temp_file.name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.cleanup()
