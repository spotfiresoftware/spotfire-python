# Copyright © 2021. TIBCO Software Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Tools to create Microsoft cabinet files.  Only defined on Windows platforms."""

import sys

if sys.platform == "win32":
    import msilib
    import os
    import typing
    from spotfire import _utils

    class CabFile:
        """Class with methods to open, write, and close Microsoft cabinet files."""
        def __init__(self, file: str) -> None:
            """Open the cabinet file.

            :param file: filename of the cabinet file
            """
            self.filename = file
            self._contents = []
            self._temp_files = _utils.TempFiles()
            self._opened = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self.close()

        def __repr__(self) -> str:
            result = [f"<{self.__class__.__module__}.{self.__class__.__qualname__}"]
            if not self._opened:
                result.append(" [closed]")
            elif self.filename is not None:
                result.append(f" filename={self.filename!r}")
            result.append(">")
            return "".join(result)

        def write(self, filename: str, arcname=None) -> None:
            """Put a file into the cabinet.

            :param filename: the filename of the file to put in the cabinet
            :param arcname: the name in the cabinet the file should be placed under.  If ``None``, use the basename
             (without path information) of filename.
            """
            if not self._opened:
                raise ValueError("Attempt to write to cabinet that was already closed")

            if arcname is None:
                arcname = os.path.basename(filename)
            self._contents.append((filename, arcname))

        def writestr(self, arcname: str, data: typing.Union[str, bytes]) -> None:
            """Write arbitrary data into the cabinet.

            :param arcname: the name in the cabinet the data should be placed under
            :param data: the data to place in the cabinet
            """
            if not self._opened:
                raise ValueError("Attempt to write to cabinet that was already closed")

            # write the data out to a temp file
            temp = self._temp_files.new_file()
            temp.file.write(data)
            temp.close()
            self._contents.append((temp.name, arcname))

        def close(self) -> None:
            """Close the cabinet and write the contents to disk."""
            if self._opened:
                msilib.FCICreate(self.filename, self._contents)
                self._temp_files.cleanup()
                self._opened = False
