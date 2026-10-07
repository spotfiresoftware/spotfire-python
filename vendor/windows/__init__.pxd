cdef extern from "<windows.h>" nogil:
    # Types defined at https://docs.microsoft.com/en-us/windows/win32/winprog/windows-data-types
    ctypedef bint BOOL
    ctypedef const char* LPCSTR
    ctypedef const Py_UNICODE* LPCWSTR
    ctypedef unsigned long DWORD
    ctypedef void* HANDLE
    ctypedef int HRESULT
    ctypedef Py_ssize_t INT_PTR
    ctypedef Py_ssize_t ULONG_PTR
    ctypedef long LONG

    # Structure defined at https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-filetime
    ctypedef struct FILETIME:
        DWORD dwLowDateTime
        DWORD dwHighDateTime

    # Function defined at https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-comparefiletime
    cdef LONG CompareFileTime(const FILETIME*, const FILETIME*)

    # Preprocessor definitions defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/common-hresult-values
    cdef enum:
        S_OK

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/api/errhandlingapi/nf-errhandlingapi-getlasterror
    cdef DWORD GetLastError()

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-loadlibrarya
    cdef HANDLE LoadLibrary(char*)

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-freelibrary
    cdef void FreeLibrary(HANDLE)

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-getprocaddress
    cdef void* GetProcAddress(HANDLE, char*)
