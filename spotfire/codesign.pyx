# cython: language_level=3

# Copyright © 2021. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Tools to apply Authenticode code signing signatures and timestamps to files using the native Microsoft APIs.
Only runs on Windows platforms."""

cpdef enum CertificateStoreLocation:
    CURRENT_USER = 1
    LOCAL_MACHINE = 2


def codesign_file(filename, certificate, password, timestamp = None, use_rfc3161 = False, use_sha256 = False):
    """Codesign a file with the Microsoft signing API found in mssign32.dll using a certificate found in a PFX file
    or PKCS#12 container.

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


def codesign_file_from_store(filename, store_location, store_name, store_cn, timestamp = None, use_rfc3161 = False,
                             use_sha256 = False):
    """Codesign a file with the Microsoft signing API found in mssign32.dll using a certificate found in a system
    certificate store.

    :param filename: the filename of the file to codesign
    :param store_location: the location of the Windows certificate store to find the certificate to sign with in
    :param store_name: the name of the Windows certificate store to find the certificate to sign with in
    :param store_cn: a string specifying the subject common name (or a substring thereof) of the certificate to
      sign with
    :param timestamp: a URL of the timestamping service to timestamp the code signature with
    :param use_rfc3161: whether or not to use the RFC 3161 timestamping protocol.  If ``True``, use RFC 3161.
      If ``False``, use Authenticode.
    :param use_sha256: whether or not to use SHA-256 as the timestamping hash function.  If ``True``, use SHA-256.
      If ``False``, use SHA-1.
    """
    raise OSError("Codesigning not supported on non-Win32 platforms")
