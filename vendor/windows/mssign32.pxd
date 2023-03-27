from vendor cimport windows
from vendor.windows cimport wincrypt

# Definitions for mssign32.dll
cdef extern from "mssign32.h" nogil:
    # Structure defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signer-file-info
    ctypedef struct SIGNER_FILE_INFO:
        windows.DWORD cbSize
        windows.LPCWSTR pwszFileName
        windows.HANDLE hFile

    # Structure defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signer-subject-info
    ctypedef struct SIGNER_SUBJECT_INFO:
        windows.DWORD cbSize
        windows.DWORD* pdwIndex
        windows.DWORD dwSubjectChoice
        SIGNER_FILE_INFO* pSignerFileInfo

    # Preprocessor defines for SIGNER_SUBJECT_INFO structure
    cdef enum:
        SIGNER_SUBJECT_FILE

    # Structure defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signer-cert-store-info
    ctypedef struct SIGNER_CERT_STORE_INFO:
        windows.DWORD cbSize
        wincrypt.CERT_CONTEXT* pSigningCert
        windows.DWORD dwCertPolicy
        windows.HANDLE hCertStore

    # Preprocessor defines for SIGNER_CERT_STORE_INFO structure
    cdef enum:
        SIGNER_CERT_POLICY_CHAIN

    # Structure defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signer-cert
    ctypedef struct SIGNER_CERT:
        windows.DWORD cbSize
        windows.DWORD dwCertChoice
        SIGNER_CERT_STORE_INFO* pCertStoreInfo
        windows.HANDLE hwnd

    # Preprocessor defines for SIGNER_CERT structure
    cdef enum:
        SIGNER_CERT_STORE

    # Structure defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signer-attr-authcode
    ctypedef struct SIGNER_ATTR_AUTHCODE:
        windows.DWORD cbSize
        windows.BOOL fCommercial
        windows.BOOL fIndividual
        windows.LPCWSTR pwszName
        windows.LPCWSTR pwszInfo

    # Structure defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signer-signature-info
    ctypedef struct SIGNER_SIGNATURE_INFO:
        windows.DWORD cbSize
        wincrypt.ALG_ID algidHash
        windows.DWORD dwAttrChoice
        SIGNER_ATTR_AUTHCODE* pAttrAuthcode
        wincrypt.CRYPT_ATTRIBUTES* psAuthenticated
        wincrypt.CRYPT_ATTRIBUTES* psUnauthenticated

    # Preprocessor defines for SIGNER_SIGNATURE_INFO structure
    cdef enum:
        SIGNER_AUTHCODE_ATTR

    # Structure defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signer-provider-info
    ctypedef struct SIGNER_PROVIDER_INFO:
        pass

    # Structure defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signer-context
    ctypedef struct SIGNER_CONTEXT:
        pass

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signersignex
    ctypedef windows.HRESULT (*SignerSignExType)(windows.DWORD, SIGNER_SUBJECT_INFO*, SIGNER_CERT*,
                                                 SIGNER_SIGNATURE_INFO*, SIGNER_PROVIDER_INFO*, windows.LPCWSTR,
                                                 wincrypt.CRYPT_ATTRIBUTES*, void*, SIGNER_CONTEXT**)

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signertimestamp
    ctypedef windows.HRESULT (*SignerTimeStampType)(SIGNER_SUBJECT_INFO*, windows.LPCWSTR, wincrypt.CRYPT_ATTRIBUTES*,
                                                    void*)

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signertimestampex2
    ctypedef windows.HRESULT (*SignerTimeStampEx2Type)(windows.DWORD, SIGNER_SUBJECT_INFO*, windows.LPCWSTR, char*,
                                                       wincrypt.CRYPT_ATTRIBUTES*, void*, SIGNER_CONTEXT**)

    # Preprocessor defines for SignerTimeStampEx2 function arguments
    cdef enum:
        SIGNER_TIMESTAMP_AUTHENTICODE
        SIGNER_TIMESTAMP_RFC3161

    # Preprocessor defines for hash algorithm OID strings
    char* OID_SHA1
    char* OID_SHA256

    # Function defined at https://docs.microsoft.com/en-us/windows/win32/seccrypto/signerfreesignercontext
    ctypedef windows.HRESULT (*SignerFreeSignerContextType)(SIGNER_CONTEXT*)
