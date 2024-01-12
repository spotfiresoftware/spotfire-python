# Copyright © 2023. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

cdef extern from "cabfile_helpers.h":
    # FCI callback functions
    fci.PFNFCIALLOC _fci_cb_alloc
    fci.PFNFCIFREE _fci_cb_free
    fci.PFNFCIOPEN _fci_cb_open
    fci.PFNFCIREAD _fci_cb_read
    fci.PFNFCIWRITE _fci_cb_write
    fci.PFNFCICLOSE _fci_cb_close
    fci.PFNFCISEEK _fci_cb_seek
    fci.PFNFCIDELETE _fci_cb_delete
    fci.PFNFCIFILEPLACED _fci_cb_file_placed
    fci.PFNFCIGETTEMPFILE _fci_cb_get_temp_file
    fci.PFNFCISTATUS _fci_cb_status
    fci.PFNFCIGETNEXTCABINET _fci_cb_get_next_cabinet
    fci.PFNFCIGETOPENINFO _fci_cb_get_open_info
