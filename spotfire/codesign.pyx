# cython: language_level=3

# Copyright © 2021. TIBCO Software Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Tools to apply Authenticode code signing signatures and timestamps to files using the native Microsoft APIs.
Only runs on Windows platforms."""

IF UNAME_SYSNAME == "Windows":

    import os

    # Windows typedefs
    cdef extern from "windows.h":
        ctypedef bint BOOL
        ctypedef const Py_UNICODE* LPCWSTR
        ctypedef unsigned long DWORD
        ctypedef void* HANDLE
        ctypedef int HRESULT
        cdef enum:
            S_OK
        cdef DWORD GetLastError()
        cdef HANDLE LoadLibrary(char*)
        cdef void FreeLibrary(HANDLE)
        cdef void* GetProcAddress(HANDLE, char*)

    # Definitions for crypt32.dll
    cdef extern from "wincrypt.h":
        cdef enum:
            X509_ASN_ENCODING
            PKCS_7_ASN_ENCODING
        ctypedef struct CERT_CONTEXT:
            pass
        cdef enum:
            CERT_KEY_SPEC_PROP_ID
        ctypedef unsigned int ALG_ID
        cdef enum:
            CALG_SHA1
            CALG_SHA_256
        ctypedef struct CRYPT_ATTRIBUTES:
            pass
        ctypedef struct CRYPT_DATA_BLOB:
            DWORD cbData
            char* pbData
        HANDLE PFXImportCertStore(CRYPT_DATA_BLOB*, LPCWSTR, DWORD)
        BOOL CertCloseStore(HANDLE, DWORD)
        cdef enum:
            CERT_CLOSE_STORE_CHECK_FLAG
        const CERT_CONTEXT* CertFindCertificateInStore(HANDLE, DWORD, DWORD, DWORD, void*, CERT_CONTEXT *)
        cdef enum:
            CERT_FIND_ANY
        BOOL CertGetCertificateContextProperty(CERT_CONTEXT*, DWORD, void*, DWORD*)
        BOOL CertFreeCertificateContext(CERT_CONTEXT*)

    # Definitions for mssign32.dll
    cdef extern from "mssign32.h":
        ctypedef struct SIGNER_FILE_INFO:
            DWORD cbSize
            LPCWSTR pwszFileName
            HANDLE hFile
        ctypedef struct SIGNER_SUBJECT_INFO:
            DWORD cbSize
            DWORD* pdwIndex
            DWORD dwSubjectChoice
            SIGNER_FILE_INFO* pSignerFileInfo
        cdef enum:
            SIGNER_SUBJECT_FILE
        ctypedef struct SIGNER_CERT_STORE_INFO:
            DWORD cbSize
            CERT_CONTEXT* pSigningCert
            DWORD dwCertPolicy
            HANDLE hCertStore
        cdef enum:
            SIGNER_CERT_POLICY_CHAIN
        ctypedef struct SIGNER_CERT:
            DWORD cbSize
            DWORD dwCertChoice
            SIGNER_CERT_STORE_INFO* pCertStoreInfo
            HANDLE hwnd
        cdef enum:
            SIGNER_CERT_STORE
        ctypedef struct SIGNER_ATTR_AUTHCODE:
            DWORD cbSize
            BOOL fCommercial
            BOOL fIndividual
            LPCWSTR pwszName
            LPCWSTR pwszInfo
        ctypedef struct SIGNER_SIGNATURE_INFO:
            DWORD cbSize
            ALG_ID algidHash
            DWORD dwAttrChoice
            SIGNER_ATTR_AUTHCODE* pAttrAuthcode
            CRYPT_ATTRIBUTES* psAuthenticated
            CRYPT_ATTRIBUTES* psUnauthenticated
        cdef enum:
            SIGNER_AUTHCODE_ATTR
        ctypedef struct SIGNER_PROVIDER_INFO:
            pass
        ctypedef struct SIGNER_CONTEXT:
            pass
        ctypedef HRESULT (*SignerSignExType)(DWORD, SIGNER_SUBJECT_INFO*, SIGNER_CERT*, SIGNER_SIGNATURE_INFO*, SIGNER_PROVIDER_INFO*, LPCWSTR, CRYPT_ATTRIBUTES*, void*, SIGNER_CONTEXT**)
        ctypedef HRESULT (*SignerTimeStampType)(SIGNER_SUBJECT_INFO*, LPCWSTR, CRYPT_ATTRIBUTES*, void*)
        ctypedef HRESULT (*SignerTimeStampEx2Type)(DWORD, SIGNER_SUBJECT_INFO*, LPCWSTR, char*, CRYPT_ATTRIBUTES*, void*, SIGNER_CONTEXT**)
        cdef enum:
            SIGNER_TIMESTAMP_AUTHENTICODE
            SIGNER_TIMESTAMP_RFC3161
        char* OID_SHA1
        char* OID_SHA256
        ctypedef HRESULT (*SignerFreeSignerContextType)(SIGNER_CONTEXT*)

    #
    cdef Py_UNICODE _empty_wstring[1]
    _empty_wstring[:] = [0]

    cpdef void codesign_file(filename,
                             certificate,
                             LPCWSTR password,
                             LPCWSTR timestamp = NULL,
                             bint use_rfc3161 = False,
                             bint use_sha256 = False):
        """Codesign a file using the Microsoft signing API found in mssign32.dll.
    
        :param filename: the filename of the file to codesign
        :param certificate: the filename of the certificate file to codesign with
        :param password: the password used to unlock the certificate
        :param timestamp: a URL of the timestamping service to timestamp the code signature with
        :param use_rfc3161: whether or not to use the RFC 3161 timestamping protocol.  If ``True``, use RFC 3161.
          If ``False``, use Authenticode.
        :param use_sha256: whether or not to use SHA-256 as the timestamping hash function.  If ``True``, use SHA-256.
          If ``False``, use SHA-1.
        """
        cdef HANDLE mssign32 = NULL
        cdef SignerSignExType signer_sign_ex_fun
        cdef SignerTimeStampType signer_time_stamp_fun
        cdef SignerTimeStampEx2Type signer_time_stamp_ex2_fun
        cdef SignerFreeSignerContextType signer_free_signer_context_fun
        cdef CRYPT_DATA_BLOB cert_blob
        cdef HANDLE cert_store = NULL
        cdef const CERT_CONTEXT* cert_context = NULL
        cdef DWORD key_spec, key_spec_len
        cdef SIGNER_FILE_INFO signer_file_info
        cdef SIGNER_SUBJECT_INFO signer_subject_info
        cdef DWORD index
        cdef SIGNER_CERT_STORE_INFO signer_cert_store_info
        cdef SIGNER_CERT signer_cert
        cdef SIGNER_ATTR_AUTHCODE signer_attr_authcode
        cdef SIGNER_SIGNATURE_INFO signer_sig_info
        cdef SIGNER_CONTEXT* signer_context = NULL

        try:
            # Sanity check arguments
            if not os.path.isfile(filename):
                raise FileNotFoundError(f"No such file: '{filename}'")
            if not os.path.isfile(certificate):
                raise FileNotFoundError(f"No such file: '{certificate}'")
            if use_sha256 and not use_rfc3161:
                raise Exception("SHA-256 timestamping requires the RFC 3161 timestamping protocol")

            # Load DLL and functions from mssign32.dll
            mssign32 = LoadLibrary("mssign32.dll")
            if mssign32 is NULL:
                raise Exception(f"Cannot load mssign32.dll (0x{GetLastError():08x})")
            signer_sign_ex_fun = <SignerSignExType>GetProcAddress(mssign32, "SignerSignEx")
            if signer_sign_ex_fun is NULL:
                raise Exception(f"Cannot find function 'SignerSignEx' (0x{GetLastError():08x})")
            signer_time_stamp_fun = <SignerTimeStampType>GetProcAddress(mssign32, "SignerTimeStamp")
            if signer_time_stamp_fun is NULL:
                raise Exception(f"Cannot find function 'SignerTimeStamp' (0x{GetLastError():08x})")
            signer_time_stamp_ex2_fun = <SignerTimeStampEx2Type>GetProcAddress(mssign32, "SignerTimeStampEx2")
            if signer_time_stamp_ex2_fun is NULL:
                raise Exception(f"Cannot find function 'SignerTimeStampEx2' (0x{GetLastError():08x})")
            signer_free_signer_context_fun = <SignerFreeSignerContextType>GetProcAddress(mssign32, "SignerFreeSignerContext")
            if signer_free_signer_context_fun is NULL:
                raise Exception(f"Cannot find function 'SignerFreeSignerContext' (0x{GetLastError():08x})")

            # Open the certificate file and convert it into an in-memory cert store
            with open(certificate, "rb") as cert:
                cert_data = cert.read()
            cert_blob.cbData = <DWORD>len(cert_data)
            cert_blob.pbData = <char*>cert_data
            cert_store = PFXImportCertStore(&cert_blob, password, 0)
            if cert_store is NULL:
                cert_store = PFXImportCertStore(&cert_blob, _empty_wstring, 0)
            if cert_store is NULL:
                cert_store = PFXImportCertStore(&cert_blob, NULL, 0)
            if cert_store is NULL:
                raise Exception(f"Could not load certificate; is the password correct? (0x{GetLastError():08x})")

            # Extract the cert from the new cert store
            cert_context = CertFindCertificateInStore(cert_store, X509_ASN_ENCODING | PKCS_7_ASN_ENCODING, 0,
                                                      CERT_FIND_ANY, NULL, NULL)
            if cert_context is NULL:
                raise Exception(f"Could not get certificate from store (0x{GetLastError():08x})")
            found_private_key = False
            while not found_private_key:
                key_spec_len = sizeof(key_spec)
                has_private_key = CertGetCertificateContextProperty(cert_context, CERT_KEY_SPEC_PROP_ID,
                                                                    &key_spec, &key_spec_len)
                if has_private_key:
                    found_private_key = True
                else:
                    cert_context = CertFindCertificateInStore(cert_store, X509_ASN_ENCODING | PKCS_7_ASN_ENCODING, 0,
                                                              CERT_FIND_ANY, NULL, cert_context)
                    if cert_context is NULL:
                        raise Exception(f"Could not get certificate from store (0x{GetLastError():08x})")

            # Prepare structures
            signer_file_info.cbSize = sizeof(SIGNER_FILE_INFO)
            signer_file_info.pwszFileName = filename
            signer_file_info.hFile = NULL

            signer_subject_info.cbSize = sizeof(SIGNER_SUBJECT_INFO)
            signer_subject_info.pdwIndex = &index
            signer_subject_info.dwSubjectChoice = SIGNER_SUBJECT_FILE
            signer_subject_info.pSignerFileInfo = &signer_file_info

            signer_cert_store_info.cbSize = sizeof(SIGNER_CERT_STORE_INFO)
            signer_cert_store_info.pSigningCert = cert_context
            signer_cert_store_info.dwCertPolicy = SIGNER_CERT_POLICY_CHAIN
            signer_cert_store_info.hCertStore = NULL

            signer_cert.cbSize = sizeof(SIGNER_CERT)
            signer_cert.dwCertChoice = SIGNER_CERT_STORE
            signer_cert.pCertStoreInfo = &signer_cert_store_info
            signer_cert.hwnd = NULL

            signer_attr_authcode.cbSize = sizeof(SIGNER_ATTR_AUTHCODE)
            signer_attr_authcode.fCommercial = False
            signer_attr_authcode.fIndividual = True
            signer_attr_authcode.pwszName = _empty_wstring
            signer_attr_authcode.pwszInfo = NULL

            signer_sig_info.cbSize = sizeof(SIGNER_SIGNATURE_INFO)
            signer_sig_info.algidHash = CALG_SHA_256 if use_sha256 else CALG_SHA1
            signer_sig_info.dwAttrChoice = SIGNER_AUTHCODE_ATTR
            signer_sig_info.pAttrAuthcode = &signer_attr_authcode
            signer_sig_info.psAuthenticated = NULL
            signer_sig_info.psUnauthenticated = NULL

            # Sign the file
            result = signer_sign_ex_fun(0, &signer_subject_info, &signer_cert, &signer_sig_info, NULL, NULL, NULL, NULL,
                                        &signer_context)
            if signer_context is not NULL:
                signer_free_signer_context_fun(signer_context)
            if result is not S_OK:
                raise Exception(f"Could not sign file (0x{GetLastError():08x})")

            # Timestamp the file
            if timestamp is not NULL:
                if use_rfc3161:
                    result = signer_time_stamp_ex2_fun(SIGNER_TIMESTAMP_RFC3161, &signer_subject_info, timestamp,
                                                       OID_SHA256 if use_sha256 else OID_SHA1, NULL, NULL, &signer_context)
                    if signer_context is not NULL:
                        signer_free_signer_context_fun(signer_context)
                else:
                    result = signer_time_stamp_fun(&signer_subject_info, timestamp, NULL, NULL)
                if result is not S_OK:
                    raise Exception(f"Could not timestamp file (0x{GetLastError():08x})")
        finally:
            if cert_context is not NULL:
                CertFreeCertificateContext(cert_context)
            if cert_store is not NULL:
                CertCloseStore(cert_store, CERT_CLOSE_STORE_CHECK_FLAG)
            if mssign32 is not NULL:
                FreeLibrary(mssign32)

ELSE:

    def codesign_file(filename, certificate, password, timestamp = None, use_rfc3161 = False, use_sha256 = False):
        """Codesign a file using the Microsoft signing API found in mssign32.dll.

        :param filename: the filename of the file to codesign
        :param certificate: the filename of the certificate file to codesign with
        :param password: the password used to unlock the certificate
        :param timestamp: a URL of the timestamping service to timestamp the code signature with
        :param use_rfc3161: whether or not to use the RFC 3161 timestamping protocol.  If ``True``, use RFC 3161.
          If ``False``, use Authenticode.
        :param use_sha256: whether or not to use SHA-256 as the timestamping hash function.  If ``True``, use SHA-256.
          If ``False``, use SHA-1.
        """
        raise OSError("Codesigning not supported on non-Win32 platforms")
