# Copyright © 2021. TIBCO Software Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Tools to apply Authenticode code signing signatures and timestamps to files using the native Microsoft APIs.
Only defined on Windows platforms."""

import sys

if sys.platform == "win32":
    # pylint: disable=invalid-name,too-few-public-methods,attribute-defined-outside-init
    import ctypes
    from ctypes import wintypes
    import os
    import typing

    # Constant declarations
    _S_OK = 0

    _X509_ASN_ENCODING = 0x00010000
    _PKCS_7_ASN_ENCODING = 0x00000001

    _CERT_FIND_ANY = 0
    _CERT_KEY_SPEC_PROP_ID = 6
    _CERT_CLOSE_STORE_CHECK_FLAG = 2

    _SIGNER_SUBJECT_FILE = 1
    _SIGNER_CERT_POLICY_CHAIN = 2
    _SIGNER_CERT_STORE = 2
    _SIGNER_AUTHCODE_ATTR = 1

    _SIGNER_TIMESTAMP_AUTHENTICODE = 1
    _SIGNER_TIMESTAMP_RFC3161 = 2

    _CALG_SHA_256 = 0x800C
    _CALG_SHA1 = 0x8004
    _OID_SHA256 = b"2.16.840.1.101.3.4.2.1"
    _OID_SHA1 = b"1.3.14.3.2.26"

    # Type declarations
    _PCCERT_CONTEXT = ctypes.c_void_p
    _PSIGNER_CONTEXT = ctypes.c_void_p
    _PSIGNER_PROVIDER_INFO = ctypes.c_void_p
    _ALG_ID = ctypes.c_uint
    _PCRYPT_ATTRIBUTES = ctypes.c_void_p

    class _CRYPT_DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.c_char_p)]

    class _SIGNER_FILE_INFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("pwszFileName", wintypes.LPCWSTR),
                    ("hFile", wintypes.HANDLE)]

    class _SIGNER_SUBJECT_INFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("pdwIndex", wintypes.LPDWORD),
                    ("dwSubjectChoice", wintypes.DWORD),
                    ("pSignerFileInfo", ctypes.POINTER(_SIGNER_FILE_INFO))]

    class _SIGNER_CERT_STORE_INFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("pSigningCert", _PCCERT_CONTEXT),
                    ("dwCertPolicy", wintypes.DWORD),
                    ("hCertStore", wintypes.HANDLE)]

    class _SIGNER_CERT(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("dwCertChoice", wintypes.DWORD),
                    ("pCertStoreInfo", ctypes.POINTER(_SIGNER_CERT_STORE_INFO)),
                    ("hwnd", wintypes.HWND)]

    class _SIGNER_ATTR_AUTHCODE(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("fCommercial", wintypes.BOOL),
                    ("fIndividual", wintypes.BOOL),
                    ("pwszName", wintypes.LPCWSTR),
                    ("pwszInfo", wintypes.LPCWSTR)]

    class _SIGNER_SIGNATURE_INFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("algidHash", _ALG_ID),
                    ("dwAttrChoice", wintypes.DWORD),
                    ("pAttrAuthcode", ctypes.POINTER(_SIGNER_ATTR_AUTHCODE)),
                    ("psAuthenticated", _PCRYPT_ATTRIBUTES),
                    ("psUnauthenticated", _PCRYPT_ATTRIBUTES)]

    # Parameter declarations
    def _wrap_function(lib, function_name, restype, argtypes):
        """Simplify wrapping ctypes functions"""
        func = lib.__getattr__(function_name)
        func.restype = restype
        func.argtypes = argtypes
        return func


    _pfx_import_cert_store = _wrap_function(ctypes.windll.crypt32,
                                            "PFXImportCertStore",
                                            wintypes.HANDLE,
                                            [ctypes.POINTER(_CRYPT_DATA_BLOB),
                                             wintypes.LPCWSTR,
                                             wintypes.DWORD])

    _cert_close_store = _wrap_function(ctypes.windll.crypt32,
                                       "CertCloseStore",
                                       wintypes.BOOL,
                                       [wintypes.HANDLE,
                                        wintypes.DWORD])

    _cert_find_cert_in_store = _wrap_function(ctypes.windll.crypt32,
                                              "CertFindCertificateInStore",
                                              _PCCERT_CONTEXT,
                                              [wintypes.HANDLE,
                                               wintypes.DWORD,
                                               wintypes.DWORD,
                                               wintypes.DWORD,
                                               ctypes.c_void_p,
                                               _PCCERT_CONTEXT])

    _cert_get_context_property = _wrap_function(ctypes.windll.crypt32,
                                                "CertGetCertificateContextProperty",
                                                wintypes.BOOL,
                                                [_PCCERT_CONTEXT,
                                                 wintypes.DWORD,
                                                 ctypes.c_void_p,
                                                 wintypes.LPDWORD])

    _cert_free_context = _wrap_function(ctypes.windll.crypt32,
                                        "CertFreeCertificateContext",
                                        wintypes.BOOL,
                                        [_PCCERT_CONTEXT])

    _signer_sign_ex = _wrap_function(ctypes.windll.mssign32,
                                     "SignerSignEx",
                                     ctypes.HRESULT,
                                     [wintypes.DWORD,
                                      ctypes.POINTER(_SIGNER_SUBJECT_INFO),
                                      ctypes.POINTER(_SIGNER_CERT),
                                      ctypes.POINTER(_SIGNER_SIGNATURE_INFO),
                                      _PSIGNER_PROVIDER_INFO,
                                      wintypes.LPCWSTR,
                                      _PCRYPT_ATTRIBUTES,
                                      ctypes.c_void_p,
                                      ctypes.POINTER(_PSIGNER_CONTEXT)])

    _signer_timestamp = _wrap_function(ctypes.windll.mssign32,
                                       "SignerTimeStamp",
                                       ctypes.HRESULT,
                                       [ctypes.POINTER(_SIGNER_SUBJECT_INFO),
                                        wintypes.LPCWSTR,
                                        _PCRYPT_ATTRIBUTES,
                                        ctypes.c_void_p])

    _signer_timestamp_ex2 = _wrap_function(ctypes.windll.mssign32,
                                           "SignerTimeStampEx2",
                                           ctypes.HRESULT,
                                           [wintypes.DWORD,
                                            ctypes.POINTER(_SIGNER_SUBJECT_INFO),
                                            wintypes.LPCWSTR,
                                            ctypes.c_char_p,
                                            _PCRYPT_ATTRIBUTES,
                                            ctypes.c_void_p,
                                            ctypes.POINTER(_PSIGNER_CONTEXT)])

    _signer_free_context = _wrap_function(ctypes.windll.mssign32,
                                          "SignerFreeSignerContext",
                                          ctypes.HRESULT,
                                          [_PSIGNER_CONTEXT])

    # Public functions

    # noinspection PyUnboundLocalVariable
    def codesign_file(filename: str,
                      certificate: str,
                      password: typing.Optional[str],
                      timestamp: typing.Optional[str] = None,
                      use_rfc3161: bool = False,
                      use_sha256: bool = False) -> None:
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
        try:
            # Sanity check arguments
            if not os.path.isfile(filename):
                raise FileNotFoundError(f"No such file: '{filename}'")
            if not os.path.isfile(certificate):
                raise FileNotFoundError(f"No such file: '{certificate}'")
            if use_sha256 and not use_rfc3161:
                raise Exception("SHA-256 timestamping requires the RFC 3161 timestamping protocol")

            # Open the certificate file and convert it into an in-memory cert store
            cert_store = _open_certificate(certificate, password)

            # Extract the cert from the new cert store
            cert_context = _extract_certificate(cert_store)

            # Prepare structures
            index = wintypes.DWORD()
            signer_subject_info = _create_subject(index, filename)

            # Sign the file
            _sign(cert_context, use_sha256, signer_subject_info)

            # Timestamp the file
            _timestamp(signer_subject_info, timestamp, use_rfc3161, use_sha256)

        finally:
            try:
                if cert_context is not None:
                    _cert_free_context(cert_context)
            except NameError:
                pass

            try:
                if cert_store is not None:
                    _cert_close_store(cert_store, _CERT_CLOSE_STORE_CHECK_FLAG)
            except NameError:
                pass


    def _open_certificate(certificate, password):
        """Open the certificate file and convert it into an in-memory cert store."""
        with open(certificate, "rb") as cert:
            cert_data = cert.read()
        cert_blob = _CRYPT_DATA_BLOB(len(cert_data), cert_data)
        cert_store = _pfx_import_cert_store(ctypes.byref(cert_blob), password, 0)
        if cert_store is None:
            cert_store = _pfx_import_cert_store(ctypes.byref(cert_blob), "", 0)
        if cert_store is None:
            cert_store = _pfx_import_cert_store(ctypes.byref(cert_blob), None, 0)
        if cert_store is None:
            raise Exception(f"Could not load certificate; is the password correct? (0x{ctypes.GetLastError():08x})")
        return cert_store


    def _extract_certificate(cert_store):
        """Extract the cert from the new cert store."""
        cert_context = _cert_find_cert_in_store(cert_store, _X509_ASN_ENCODING | _PKCS_7_ASN_ENCODING, 0,
                                                _CERT_FIND_ANY, None, None)
        if cert_context is None:
            raise Exception(f"Could not get certificate from store (0x{ctypes.GetLastError():08x})")
        key_spec = wintypes.DWORD()
        found_private_key = False
        while not found_private_key:
            key_spec_len = wintypes.DWORD(ctypes.sizeof(key_spec))
            has_private_key = _cert_get_context_property(cert_context, _CERT_KEY_SPEC_PROP_ID,
                                                         ctypes.byref(key_spec), ctypes.byref(key_spec_len))
            if has_private_key:
                found_private_key = True
            else:
                cert_context = _cert_find_cert_in_store(cert_store, _X509_ASN_ENCODING | _PKCS_7_ASN_ENCODING, 0,
                                                        _CERT_FIND_ANY, None, cert_context)
                if cert_context is None:
                    raise Exception(f"Could not get certificate from store (0x{ctypes.GetLastError():08x})")
        return cert_context


    def _create_subject(index, filename):
        """Create a subject information structure for a given file."""
        signer_file_info = _SIGNER_FILE_INFO()
        signer_file_info.cbSize = ctypes.sizeof(_SIGNER_FILE_INFO)
        signer_file_info.pwszFileName = filename
        signer_file_info.hFile = None

        signer_subject_info = _SIGNER_SUBJECT_INFO()
        signer_subject_info.cbSize = ctypes.sizeof(_SIGNER_SUBJECT_INFO)
        signer_subject_info.pdwIndex = ctypes.pointer(index)
        signer_subject_info.dwSubjectChoice = _SIGNER_SUBJECT_FILE
        signer_subject_info.pSignerFileInfo = ctypes.pointer(signer_file_info)

        return signer_subject_info


    def _sign(cert_context, use_sha256, signer_subject_info):
        """Sign the file."""
        signer_cert_store_info = _SIGNER_CERT_STORE_INFO()
        signer_cert_store_info.cbSize = ctypes.sizeof(_SIGNER_CERT_STORE_INFO)
        signer_cert_store_info.pSigningCert = cert_context
        signer_cert_store_info.dwCertPolicy = _SIGNER_CERT_POLICY_CHAIN
        signer_cert_store_info.hCertStore = None

        signer_cert = _SIGNER_CERT()
        signer_cert.cbSize = ctypes.sizeof(_SIGNER_CERT)
        signer_cert.dwCertChoice = _SIGNER_CERT_STORE
        signer_cert.pCertStoreInfo = ctypes.pointer(signer_cert_store_info)
        signer_cert.hwnd = None

        signer_attr_authcode = _SIGNER_ATTR_AUTHCODE()
        signer_attr_authcode.cbSize = ctypes.sizeof(_SIGNER_ATTR_AUTHCODE)
        signer_attr_authcode.fCommercial = False
        signer_attr_authcode.fIndividual = True
        signer_attr_authcode.pwszName = ""
        signer_attr_authcode.pwszInfo = None

        signer_signature_info = _SIGNER_SIGNATURE_INFO()
        signer_signature_info.cbSize = ctypes.sizeof(_SIGNER_SIGNATURE_INFO)
        signer_signature_info.algidHash = _CALG_SHA_256 if use_sha256 else _CALG_SHA1
        signer_signature_info.dwAttrChoice = _SIGNER_AUTHCODE_ATTR
        signer_signature_info.pAttrAuthcode = ctypes.pointer(signer_attr_authcode)
        signer_signature_info.psAuthenticated = None
        signer_signature_info.psUnauthenticated = None

        signer_context = _PSIGNER_CONTEXT()
        result = _signer_sign_ex(0,
                                 ctypes.byref(signer_subject_info),
                                 ctypes.byref(signer_cert),
                                 ctypes.byref(signer_signature_info),
                                 None,
                                 None,
                                 None,
                                 None,
                                 ctypes.byref(signer_context))
        if signer_context is not None:
            _signer_free_context(signer_context)
        if result is not _S_OK:
            raise Exception(f"Could not sign file (0x{ctypes.GetLastError():08x})")


    def _timestamp(signer_subject_info, timestamp, use_rfc3161, use_sha256):
        """Timestamp the file."""
        if timestamp is not None:
            if use_rfc3161:
                signer_context = _PSIGNER_CONTEXT()
                result = _signer_timestamp_ex2(_SIGNER_TIMESTAMP_RFC3161,
                                               ctypes.byref(signer_subject_info),
                                               timestamp,
                                               _OID_SHA256 if use_sha256 else _OID_SHA1,
                                               None,
                                               None,
                                               ctypes.byref(signer_context))
                if signer_context is not None:
                    _signer_free_context(signer_context)
            else:
                result = _signer_timestamp(ctypes.byref(signer_subject_info), timestamp, None, None)
            if result is not _S_OK:
                raise Exception(f"Could not timestamp file (0x{ctypes.GetLastError():08x})")
