from vendor cimport windows

cdef extern from "<fci.h>" nogil:
    # Enumeration for FCI errors
    cdef enum FCIERROR:
        FCIERR_NONE
        FCIERR_OPEN_SRC
        FCIERR_READ_SRC
        FCIERR_ALLOC_FAIL
        FCIERR_TEMP_FILE
        FCIERR_BAD_COMPR_TYPE
        FCIERR_CAB_FILE
        FCIERR_USER_ABORT
        FCIERR_MCI_FAIL
        FCIERR_CAB_FORMAT_LIMIT

    # Type for FCI context
    ctypedef void* HFCI

    # Structure defined at https://learn.microsoft.com/en-us/windows/win32/api/fdi_fci_types/ns-fdi_fci_types-erf
    ctypedef struct ERF:
        int erfOper
        int erfType
        windows.BOOL fError

    # Preprocessor definitions for CCAB type
    cdef enum:
        CB_MAX_DISK_NAME
        CB_MAX_CABINET_NAME
        CB_MAX_CAB_PATH

    # Structure defined at https://learn.microsoft.com/en-us/windows/win32/api/fci/ns-fci-ccab
    ctypedef struct CCAB:
        unsigned long cb
        unsigned long cbFolderThresh
        unsigned int cbReserveCFHeader
        unsigned int cbReserveCFFolder
        unsigned int cbReserveCFData
        int iCab
        int iDisk
        bint fFailOnIncompressible
        unsigned short setID
        char szDisk[CB_MAX_DISK_NAME]
        char szCab[CB_MAX_CABINET_NAME]
        char szCabPath[CB_MAX_CAB_PATH]

    # Types for FCI callbacks
    ctypedef void* (*PFNFCIALLOC)(unsigned long)
    ctypedef void (*PFNFCIFREE)(void*)
    ctypedef windows.INT_PTR (*PFNFCIOPEN)(char*, int, int, int*, void*)
    ctypedef unsigned int (*PFNFCIREAD)(windows.INT_PTR, void*, unsigned int, int*, void*)
    ctypedef unsigned int (*PFNFCIWRITE)(windows.INT_PTR, void*, unsigned int, int *, void*)
    ctypedef int (*PFNFCICLOSE)(windows.INT_PTR, int*, void*)
    ctypedef long (*PFNFCISEEK)(windows.INT_PTR, long, int, int*, void*)
    ctypedef int (*PFNFCIDELETE)(char*, int*, void*)
    ctypedef windows.BOOL (*PFNFCIGETNEXTCABINET)(CCAB*, unsigned long, void*)
    ctypedef int (*PFNFCIFILEPLACED)(CCAB*, char*, long, windows.BOOL, void*)
    ctypedef windows.INT_PTR (*PFNFCIGETOPENINFO)(char*, unsigned short*, unsigned short*, unsigned short*, int*, void*)
    ctypedef long (*PFNFCISTATUS)(unsigned int, unsigned long, unsigned long, void*)
    ctypedef windows.BOOL (*PFNFCIGETTEMPFILE)(char*, int, void*)

    # Function defined at https://learn.microsoft.com/en-us/windows/win32/api/fci/nf-fci-fcicreate
    cdef HFCI FCICreate(ERF*, PFNFCIFILEPLACED, PFNFCIALLOC, PFNFCIFREE, PFNFCIOPEN, PFNFCIREAD, PFNFCIWRITE, PFNFCICLOSE, PFNFCISEEK, PFNFCIDELETE, PFNFCIGETTEMPFILE, CCAB*, void*)

    # Type for FCI compression types
    ctypedef unsigned short TCOMP

    # Preprocessor definitions for FCI compression types
    cdef enum:
        tcompTYPE_NONE
        tcompTYPE_MSZIP

    # Function defined at https://learn.microsoft.com/en-us/windows/win32/api/fci/nf-fci-fciaddfile
    cdef windows.BOOL FCIAddFile(HFCI, char*, char*, windows.BOOL, PFNFCIGETNEXTCABINET, PFNFCISTATUS, PFNFCIGETOPENINFO, TCOMP)

    # Function defined at https://learn.microsoft.com/en-us/windows/win32/api/fci/nf-fci-fciflushcabinet
    cdef windows.BOOL FCIFlushCabinet(HFCI, windows.BOOL, PFNFCIGETNEXTCABINET, PFNFCISTATUS)

    # Function defined at https://learn.microsoft.com/en-us/windows/win32/api/fci/nf-fci-fciflushfolder
    cdef windows.BOOL FCIFlushFolder(HFCI, PFNFCIGETNEXTCABINET, PFNFCISTATUS)

    # Function defined at https://learn.microsoft.com/en-us/windows/win32/api/fci/nf-fci-fcidestroy
    cdef windows.BOOL FCIDestroy(HFCI)
