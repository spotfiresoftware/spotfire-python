from vendor cimport windows

# Definitions for crypt32.dll
cdef extern from "<wincrypt.h>" nogil:
    # Preprocessor definitions for certificate encoding types
    cdef enum:
        X509_ASN_ENCODING
        PKCS_7_ASN_ENCODING

    # Structure defined at https://docs.microsoft.com/en-us/windows/win32/api/wincrypt/ns-wincrypt-cert_context
    ctypedef struct CERT_CONTEXT:
        pass

    # Preprocessor definitions for CertGetCertificateContextProperty function
    cdef enum:
        CERT_KEY_SPEC_PROP_ID

    # Type defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/alg-id
    ctypedef unsigned int ALG_ID

    # Preprocessor definitions for ALG_ID type
    cdef enum:
        CALG_SHA1
        CALG_SHA_256

    # Structure defined at https://docs.microsoft.com/en-us/windows/win32/api/Wincrypt/ns-wincrypt-crypt_attributes
    ctypedef struct CRYPT_ATTRIBUTES:
        pass

    # Structure defined at https://docs.microsoft.com/en-us/previous-versions/windows/desktop/legacy/aa381414(v=vs.85)
    ctypedef struct CRYPT_DATA_BLOB:
        windows.DWORD cbData
        char* pbData

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/api/wincrypt/nf-wincrypt-pfximportcertstore
    windows.HANDLE PFXImportCertStore(CRYPT_DATA_BLOB*, windows.LPCWSTR, windows.DWORD)

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/api/wincrypt/nf-wincrypt-certclosestore
    windows.BOOL CertCloseStore(windows.HANDLE, windows.DWORD)

    # Preprocessor definitions for CertCloseStore function
    cdef enum:
        CERT_CLOSE_STORE_CHECK_FLAG

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/api/wincrypt/nf-wincrypt-certfindcertificateinstore
    const CERT_CONTEXT* CertFindCertificateInStore(windows.HANDLE, windows.DWORD, windows.DWORD, windows.DWORD, void*,
                                                   CERT_CONTEXT*)

    # Preprocessor definitions for CertFindCertificateInStore
    cdef enum:
        CERT_FIND_ANY

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/api/wincrypt/nf-wincrypt-certgetcertificatecontextproperty
    windows.BOOL CertGetCertificateContextProperty(CERT_CONTEXT*, windows.DWORD, void*, windows.DWORD*)

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/api/wincrypt/nf-wincrypt-certfreecertificatecontext
    windows.BOOL CertFreeCertificateContext(CERT_CONTEXT*)
