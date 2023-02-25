# cython: language_level=3

# Copyright © 2023. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Tools to create Microsoft cabinet files.  Only defined on Windows platforms."""

cimport cython

IF UNAME_SYSNAME == "Windows":

    import os
    import tempfile

    from libc cimport limits, string
    from vendor.windows cimport fci

    include "cabfile_helpers.pxi"

    @cython.auto_pickle(False)
    cdef class CabFile:
        """Class with methods to open, write, and close Microsoft cabinet files."""
        cdef readonly str filename
        cdef fci.HFCI _hfci
        cdef fci.CCAB _ccab
        cdef fci.ERF _erf
        cdef bint _opened

        def __init__(self, file):
            """Open the cabinet file.

            :param file: filename of the cabinet file
            """
            self.filename = str(file)

            # Start filling in the CCAB structure
            self._ccab.cb = limits.INT_MAX
            self._ccab.cbFolderThresh = 1000000
            self._ccab.cbReserveCFData = 0
            self._ccab.cbReserveCFFolder = 0
            self._ccab.cbReserveCFHeader = 0
            self._ccab.iCab = 1
            self._ccab.iDisk = 1
            self._ccab.setID = 0
            self._ccab.szDisk[0] = 0
            split_filename = self.filename.replace("/", "\\").rsplit("\\", 1)
            if len(split_filename) == 1:
                split_filename.insert(0, '.')
            split_filename[0] += '\\'
            string.strcpy(<char*>self._ccab.szCabPath, split_filename[0].encode('utf-8'))
            string.strcpy(<char*>self._ccab.szCab, split_filename[1].encode('utf-8'))

            # Create the FCI context
            self._hfci = fci.FCICreate(&self._erf, _fci_cb_file_placed, _fci_cb_alloc, _fci_cb_free, _fci_cb_open,
                                       _fci_cb_read, _fci_cb_write, _fci_cb_close, _fci_cb_seek, _fci_cb_delete,
                                       _fci_cb_get_temp_file, &self._ccab, NULL)
            if self._hfci == NULL:
                raise ValueError(_fci_error_to_string(&self._erf))

            self._opened = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self.close()

        def __repr__(self):
            result = [f"<{self.__class__.__module__}.{self.__class__.__qualname__}"]
            if not self._opened:
                result.append(" [closed]")
            elif self.filename is not None:
                result.append(f" filename={self.filename!r}")
            result.append(">")
            return "".join(result)

        def write(self, filename, arcname=None):
            """Put a file into the cabinet.

            :param filename: the filename of the file to put in the cabinet
            :param arcname: the name in the cabinet the file should be placed under.  If ``None``, use the basename
             (without path information) of filename.
            """
            if not self._opened:
                raise ValueError("Attempt to write to cabinet that was already closed")

            if arcname is None:
                arcname = os.path.basename(filename)
            if not fci.FCIAddFile(self._hfci, filename.encode('utf-8'), arcname.encode('utf-8'), False,
                                  _fci_cb_get_next_cabinet, _fci_cb_status, _fci_cb_get_open_info, fci.tcompTYPE_MSZIP):
                raise ValueError(_fci_error_to_string(&self._erf))

        def writestr(self, arcname, data):
            """Write arbitrary data into the cabinet.

            :param arcname: the name in the cabinet the data should be placed under
            :param data: the data to place in the cabinet
            """
            if not self._opened:
                raise ValueError("Attempt to write to cabinet that was already closed")

            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(data)
                f.close()
                if not fci.FCIAddFile(self._hfci, f.name.encode('utf-8'), arcname.encode('utf-8'), False,
                                      _fci_cb_get_next_cabinet, _fci_cb_status, _fci_cb_get_open_info,
                                      fci.tcompTYPE_MSZIP):
                    os.unlink(f.name)
                    raise ValueError(_fci_error_to_string(&self._erf))
                os.unlink(f.name)

        def close(self):
            """Close the cabinet and write the contents to disk."""
            if self._opened:
                # Flush the cabinet
                if not fci.FCIFlushCabinet(self._hfci, False, _fci_cb_get_next_cabinet, _fci_cb_status):
                    raise ValueError(_fci_error_to_string(&self._erf))

                # Destroy the FCI context
                if self._hfci != NULL:
                    if not fci.FCIDestroy(self._hfci):
                        raise ValueError(_fci_error_to_string(&self._erf))
                self._opened = False

    cdef str _fci_error_to_string(fci.ERF* erf):
        if erf.fError:
            if erf.erfOper == fci.FCIERR_NONE:
                return "No error"
            elif erf.erfOper == fci.FCIERR_OPEN_SRC:
                return "Failure opening file to be stored in cabinet"
            elif erf.erfOper == fci.FCIERR_READ_SRC:
                return "Failure reading file to be stored in cabinet"
            elif erf.erfOper == fci.FCIERR_ALLOC_FAIL:
                return "Insufficient memory in FCI"
            elif erf.erfOper == fci.FCIERR_TEMP_FILE:
                return "Could not create temporary file"
            elif erf.erfOper == fci.FCIERR_BAD_COMPR_TYPE:
                return "Unknown compression type"
            elif erf.erfOper == fci.FCIERR_CAB_FILE:
                return "Could not create cabinet file"
            elif erf.erfOper == fci.FCIERR_USER_ABORT:
                return "Client requested abort"
            elif erf.erfOper == fci.FCIERR_MCI_FAIL:
                return "Failure compressing data"
            elif erf.erfOper == fci.FCIERR_CAB_FORMAT_LIMIT:
                return "Cabinet format limits (either data size or file count) exceeded"
            else:
                return f"Unknown FCI error ({erf.erfOper})"
        else:
            return "General FCI error"

ELSE:

    class CabFile:
        """Class with methods to open, write, and close Microsoft cabinet files."""
        def __init__(self, file: str) -> None:
            """Open the cabinet file.

            :param file: filename of the cabinet file
            """
            raise OSError("Cabinet files not supported on non-Win32 platforms")
