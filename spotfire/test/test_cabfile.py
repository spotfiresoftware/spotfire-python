"""Tests for verifying the creation of cabinet files."""

import platform
import tempfile
import unittest

from spotfire import cabfile
from spotfire.test import utils


class CabFileTest(unittest.TestCase):
    """Unit tests for public functions in 'spotfire.cabfile' module."""

    def _platform_requirement(self):
        """Correctly manage skipping tests on non-Windows platforms."""
        if platform.system() != "Windows":
            self.skipTest("Cabinet files not supported on non-Win32 platforms")

    def test_write(self):
        """Verify the ``write`` method."""
        self._platform_requirement()
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/qbf.txt"
            with open(filename, "w", encoding="utf-8") as file:
                file.write("The quick brown fox jumps over the lazy dog.\n")

            with cabfile.CabFile(f"{tmpdir}/write1.cab") as cab:
                cab.write(filename)
            self._assert_cabfile_equals(f"{tmpdir}/write1.cab", utils.get_test_data_file("cabfile/qbf.cab"))

            with cabfile.CabFile(f"{tmpdir}/write2.cab") as cab:
                cab.write(filename, "quick.txt")
            self._assert_cabfile_equals(f"{tmpdir}/write2.cab", utils.get_test_data_file("cabfile/qbf-quick.cab"))

            with cabfile.CabFile(f"{tmpdir}/write3.cab") as cab:
                cab.write(filename, r"qbf\quick.txt")
            self._assert_cabfile_equals(f"{tmpdir}/write3.cab", utils.get_test_data_file("cabfile/qbf-subdir.cab"))

            with self.assertRaises(ValueError):
                # This should raise an error, since `cab` (creating 'write3.cab') is closed.
                cab.write(filename, "nope.txt")

    def test_writestr(self):
        """Verify the ``writestr`` method."""
        self._platform_requirement()
        with tempfile.TemporaryDirectory() as tmpdir:
            with cabfile.CabFile(f"{tmpdir}/writestr.cab") as cab:
                cab.writestr("qbf.txt", b"The quick brown fox jumps over the lazy dog.\r\n")
            self._assert_cabfile_equals(f"{tmpdir}/writestr.cab", utils.get_test_data_file("cabfile/qbf.cab"))

            with self.assertRaises(ValueError):
                cab.writestr("nope.txt",
                             b"This should raise an error, since `cab` (creating 'writestr.cab') is closed.")

    def test_platform_exceptions(self):
        """Verify non-Windows systems raise an exception."""
        if platform.system() == "Windows":
            self.skipTest("Not testing non-Windows behavior on Windows")
        else:
            with self.assertRaises(OSError):
                with tempfile.TemporaryDirectory() as tmpdir:
                    cabfile.CabFile(f"{tmpdir}/exception.cab")

    def _assert_cabfile_equals(self, first, second):
        """Test that two cabinet files are equivalent, except for timestamps."""
        with open(first, "rb") as first_file:
            first_bytes = self._sanitize_cabfile(first_file.read())
        with open(second, "rb") as second_file:
            second_bytes = self._sanitize_cabfile(second_file.read())
        self.assertEqual(first_bytes, second_bytes)

    def _sanitize_cabfile(self, cab_bytes):
        """Remove timestamps from the contents of an in-memory cabinet file."""
        # Format information at https://learn.microsoft.com/en-us/previous-versions/bb417343(v=msdn.10)
        barr = bytearray(cab_bytes)

        # The 4-byte offset to the first CFFILE record is at offset 0x10
        cffile_offset = self._little_endian_uint(barr[16:20])

        # Set the date and time members of the first CFFILE record to known values
        barr[cffile_offset + 10 : cffile_offset + 14] = b'\x0b\xad\xbe\xef'

        return barr

    @staticmethod
    def _little_endian_uint(le_bytes):
        val = 0
        for byte in reversed(le_bytes):
            val <<= 8
            val |= byte
        return val
