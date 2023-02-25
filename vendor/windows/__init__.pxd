cdef extern from "<windows.h>" nogil:
    # Types defined at https://docs.microsoft.com/en-us/windows/win32/winprog/windows-data-types
    ctypedef bint BOOL
    ctypedef const Py_UNICODE* LPCWSTR
    ctypedef unsigned long DWORD
    ctypedef void* HANDLE
    ctypedef int HRESULT
    ctypedef Py_ssize_t INT_PTR

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
