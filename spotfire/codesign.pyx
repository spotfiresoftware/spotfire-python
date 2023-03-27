# cython: language_level=3

# Copyright © 2021. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Tools to apply Authenticode code signing signatures and timestamps to files using the native Microsoft APIs.
Only runs on Windows platforms."""

IF UNAME_SYSNAME == "Windows":

    import os

    from vendor cimport windows
    from vendor.windows cimport wincrypt, mssign32

    cdef class CodesignError(Exception):
        """An exception that is raised to indicate a problem during code signing."""
        def __init__(self, *args):
            super().__init__(*args)
            self.winerror = windows.GetLastError()

        cdef windows.DWORD winerror

        def __str__(self):
            return f"[WinError {self.winerror:08x}] {super().__str__()}"

    # An empty string.  Sometimes no passwords are encoded this way, sometimes as NULL.
    cdef Py_UNICODE _empty_wstring[1]
    _empty_wstring[:] = [0]

    cpdef void codesign_file(filename,
                             certificate,
                             windows.LPCWSTR password,
                             windows.LPCWSTR timestamp = NULL,
                             bint use_rfc3161 = False,
                             bint use_sha256 = False) except *:
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
        cdef windows.HANDLE mssign32_library = NULL
        cdef mssign32.SignerSignExType signer_sign_ex_fun
        cdef mssign32.SignerTimeStampType signer_time_stamp_fun
        cdef mssign32.SignerTimeStampEx2Type signer_time_stamp_ex2_fun
        cdef mssign32.SignerFreeSignerContextType signer_free_signer_context_fun
        cdef wincrypt.CRYPT_DATA_BLOB cert_blob
        cdef windows.HANDLE cert_store = NULL
        cdef const wincrypt.CERT_CONTEXT* cert_context = NULL
        cdef windows.DWORD key_spec, key_spec_len
        cdef mssign32.SIGNER_FILE_INFO signer_file_info
        cdef mssign32.SIGNER_SUBJECT_INFO signer_subject_info
        cdef windows.DWORD index
        cdef mssign32.SIGNER_CERT_STORE_INFO signer_cert_store_info
        cdef mssign32.SIGNER_CERT signer_cert
        cdef mssign32.SIGNER_ATTR_AUTHCODE signer_attr_authcode
        cdef mssign32.SIGNER_SIGNATURE_INFO signer_sig_info
        cdef mssign32.SIGNER_CONTEXT* signer_context = NULL

        try:
            # Sanity check arguments
            if not os.path.isfile(filename):
                raise FileNotFoundError(f"No such file: '{filename}'")
            if not os.path.isfile(certificate):
                raise FileNotFoundError(f"No such file: '{certificate}'")
            if use_sha256 and not use_rfc3161:
                raise ValueError("SHA-256 timestamping requires the RFC 3161 timestamping protocol")

            # Load DLL and functions from mssign32.dll
            mssign32_library = windows.LoadLibrary("mssign32.dll")
            if mssign32_library is NULL:
                raise CodesignError("Cannot load mssign32.dll")
            signer_sign_ex_fun = <mssign32.SignerSignExType>windows.GetProcAddress(mssign32_library, "SignerSignEx")
            if signer_sign_ex_fun is NULL:
                raise CodesignError("Cannot find function 'SignerSignEx'")
            signer_time_stamp_fun = <mssign32.SignerTimeStampType>windows.GetProcAddress(mssign32_library, "SignerTimeStamp")
            if signer_time_stamp_fun is NULL:
                raise CodesignError("Cannot find function 'SignerTimeStamp'")
            signer_time_stamp_ex2_fun = <mssign32.SignerTimeStampEx2Type>windows.GetProcAddress(mssign32_library, "SignerTimeStampEx2")
            if signer_time_stamp_ex2_fun is NULL:
                raise CodesignError("Cannot find function 'SignerTimeStampEx2'")
            signer_free_signer_context_fun = <mssign32.SignerFreeSignerContextType>windows.GetProcAddress(mssign32_library, "SignerFreeSignerContext")
            if signer_free_signer_context_fun is NULL:
                raise CodesignError("Cannot find function 'SignerFreeSignerContext'")

            # Open the certificate file and convert it into an in-memory cert store
            with open(certificate, "rb") as cert:
                cert_data = cert.read()
            cert_blob.cbData = <windows.DWORD>len(cert_data)
            cert_blob.pbData = <char*>cert_data
            cert_store = wincrypt.PFXImportCertStore(&cert_blob, password, 0)
            if cert_store is NULL:
                cert_store = wincrypt.PFXImportCertStore(&cert_blob, _empty_wstring, 0)
            if cert_store is NULL:
                cert_store = wincrypt.PFXImportCertStore(&cert_blob, NULL, 0)
            if cert_store is NULL:
                raise CodesignError(f"Could not load certificate {certificate}; is the password correct?")

            # Extract the cert from the new cert store
            cert_context = wincrypt.CertFindCertificateInStore(cert_store,
                                                               wincrypt.X509_ASN_ENCODING | wincrypt.PKCS_7_ASN_ENCODING,
                                                               0, wincrypt.CERT_FIND_ANY, NULL, NULL)
            if cert_context is NULL:
                raise CodesignError("Could not get certificate from store")
            found_private_key = False
            while not found_private_key:
                key_spec_len = sizeof(key_spec)
                has_private_key = wincrypt.CertGetCertificateContextProperty(cert_context,
                                                                             wincrypt.CERT_KEY_SPEC_PROP_ID,
                                                                             &key_spec, &key_spec_len)
                if has_private_key:
                    found_private_key = True
                else:
                    cert_context = wincrypt.CertFindCertificateInStore(cert_store,
                                                                       wincrypt.X509_ASN_ENCODING | wincrypt.PKCS_7_ASN_ENCODING,
                                                                       0, wincrypt.CERT_FIND_ANY, NULL, cert_context)
                    if cert_context is NULL:
                        raise CodesignError("Could not get certificate from store")

            # Prepare structures
            signer_file_info.cbSize = sizeof(mssign32.SIGNER_FILE_INFO)
            signer_file_info.pwszFileName = filename
            signer_file_info.hFile = NULL

            signer_subject_info.cbSize = sizeof(mssign32.SIGNER_SUBJECT_INFO)
            index = 0
            signer_subject_info.pdwIndex = &index
            signer_subject_info.dwSubjectChoice = mssign32.SIGNER_SUBJECT_FILE
            signer_subject_info.pSignerFileInfo = &signer_file_info

            signer_cert_store_info.cbSize = sizeof(mssign32.SIGNER_CERT_STORE_INFO)
            signer_cert_store_info.pSigningCert = cert_context
            signer_cert_store_info.dwCertPolicy = mssign32.SIGNER_CERT_POLICY_CHAIN
            signer_cert_store_info.hCertStore = NULL

            signer_cert.cbSize = sizeof(mssign32.SIGNER_CERT)
            signer_cert.dwCertChoice = mssign32.SIGNER_CERT_STORE
            signer_cert.pCertStoreInfo = &signer_cert_store_info
            signer_cert.hwnd = NULL

            signer_attr_authcode.cbSize = sizeof(mssign32.SIGNER_ATTR_AUTHCODE)
            signer_attr_authcode.fCommercial = False
            signer_attr_authcode.fIndividual = True
            signer_attr_authcode.pwszName = _empty_wstring
            signer_attr_authcode.pwszInfo = NULL

            signer_sig_info.cbSize = sizeof(mssign32.SIGNER_SIGNATURE_INFO)
            signer_sig_info.algidHash = wincrypt.CALG_SHA_256 if use_sha256 else wincrypt.CALG_SHA1
            signer_sig_info.dwAttrChoice = mssign32.SIGNER_AUTHCODE_ATTR
            signer_sig_info.pAttrAuthcode = &signer_attr_authcode
            signer_sig_info.psAuthenticated = NULL
            signer_sig_info.psUnauthenticated = NULL

            # Sign the file
            result = signer_sign_ex_fun(0, &signer_subject_info, &signer_cert, &signer_sig_info, NULL, NULL, NULL, NULL,
                                        &signer_context)
            if signer_context is not NULL:
                signer_free_signer_context_fun(signer_context)
            if result is not windows.S_OK:
                raise CodesignError(f"Could not sign file {filename}")

            # Timestamp the file
            if timestamp is not NULL:
                if use_rfc3161:
                    result = signer_time_stamp_ex2_fun(mssign32.SIGNER_TIMESTAMP_RFC3161, &signer_subject_info,
                                                       timestamp,
                                                       mssign32.OID_SHA256 if use_sha256 else mssign32.OID_SHA1,
                                                       NULL, NULL, &signer_context)
                    if signer_context is not NULL:
                        signer_free_signer_context_fun(signer_context)
                else:
                    result = signer_time_stamp_fun(&signer_subject_info, timestamp, NULL, NULL)
                if result is not windows.S_OK:
                    raise CodesignError(f"Could not timestamp file {filename}")
        finally:
            if cert_context is not NULL:
                wincrypt.CertFreeCertificateContext(cert_context)
            if cert_store is not NULL:
                wincrypt.CertCloseStore(cert_store, wincrypt.CERT_CLOSE_STORE_CHECK_FLAG)
            if mssign32_library is not NULL:
                windows.FreeLibrary(mssign32_library)

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
