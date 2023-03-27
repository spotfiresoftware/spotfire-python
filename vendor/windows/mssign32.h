#ifndef _MSSIGN32_H
#define _MSSIGN32_H

// This file was created from various MSDN articles, as Microsoft does
// not define the signing structures and functions in a header file
// included in the Windows SDK.

// Required structures that are not defined in a public header file
typedef struct _SIGNER_FILE_INFO {
    DWORD cbSize;
    LPCWSTR pwszFileName;
    HANDLE hFile;
} SIGNER_FILE_INFO, *PSIGNER_FILE_INFO;

typedef struct _SIGNER_BLOB_INFO {
    DWORD cbSize;
    GUID *pGuidSubject;
    DWORD cbBlob;
    BYTE *pbBlob;
    LPCWSTR pwszDisplayName;
} SIGNER_BLOB_INFO, *PSIGNER_BLOB_INFO;

typedef struct _SIGNER_SUBJECT_INFO {
    DWORD cbSize;
    DWORD *pdwIndex;
    DWORD dwSubjectChoice;
    union {
        SIGNER_FILE_INFO *pSignerFileInfo;
        SIGNER_BLOB_INFO *pSignerBlobInfo;
    };
} SIGNER_SUBJECT_INFO, *PSIGNER_SUBJECT_INFO;

#define SIGNER_SUBJECT_FILE 1

typedef struct _SIGNER_CERT_STORE_INFO {
    DWORD cbSize;
    PCCERT_CONTEXT pSigningCert;
    DWORD dwCertPolicy;
    HCERTSTORE hCertStore;
} SIGNER_CERT_STORE_INFO, *PSIGNER_CERT_STORE_INFO;

#define SIGNER_CERT_POLICY_CHAIN 2

typedef struct _SIGNER_SPC_CHAIN_INFO {
    DWORD cbSize;
    LPCWSTR pwszSpcFile;
    DWORD dwCertPolicy;
    HCERTSTORE hCertStore;
} SIGNER_SPC_CHAIN_INFO, *PSIGNER_SPC_CHAIN_INFO;

typedef struct _SIGNER_CERT {
    DWORD cbSize;
    DWORD dwCertChoice;
    union {
        LPCWSTR pwszSpcFile;
        SIGNER_CERT_STORE_INFO *pCertStoreInfo;
        SIGNER_SPC_CHAIN_INFO *pSpcChainInfo;
    };
    HWND hwnd;
} SIGNER_CERT, *PSIGNER_CERT;

#define SIGNER_CERT_STORE 2

typedef struct _SIGNER_ATTR_AUTHCODE {
    DWORD cbSize;
    BOOL fCommercial;
    BOOL fIndividual;
    LPCWSTR pwszName;
    LPCWSTR pwszInfo;
} SIGNER_ATTR_AUTHCODE, *PSIGNER_ATTR_AUTHCODE;

typedef struct _SIGNER_SIGNATURE_INFO {
    DWORD cbSize;
    ALG_ID algidHash;
    DWORD dwAttrChoice;
    union {
        SIGNER_ATTR_AUTHCODE *pAttrAuthcode;
    };
    PCRYPT_ATTRIBUTES psAuthenticated;
    PCRYPT_ATTRIBUTES psUnauthenticated;
} SIGNER_SIGNATURE_INFO, *PSIGNER_SIGNATURE_INFO;

#define SIGNER_AUTHCODE_ATTR 1

typedef struct _SIGNER_PROVIDER_INFO {
    DWORD cbSize;
    LPCWSTR pwszProviderName;
    DWORD dwProviderType;
    DWORD dwKeySpec;
    DWORD dwPvkChoice;
    union {
        LPWSTR pwszPvkFileName;
        LPWSTR pwszKeyContainer;
    };
} SIGNER_PROVIDER_INFO, *PSIGNER_PROVIDER_INFO;

typedef struct _SIGNER_CONTEXT {
    DWORD cbSize;
    DWORD cbBlob;
    BYTE *pbBlob;
} SIGNER_CONTEXT, *PSIGNER_CONTEXT;

typedef HRESULT(WINAPI* SignerFreeSignerContextType)(
    __in  SIGNER_CONTEXT *pSignerContext
    );

typedef HRESULT(WINAPI *SignerSignExType)(
    __in      DWORD dwFlags,
    __in      SIGNER_SUBJECT_INFO *pSubjectInfo,
    __in      SIGNER_CERT *pSignerCert,
    __in      SIGNER_SIGNATURE_INFO *pSignatureInfo,
    __in_opt  SIGNER_PROVIDER_INFO *pProviderInfo,
    __in_opt  LPCWSTR pwszHttpTimeStamp,
    __in_opt  PCRYPT_ATTRIBUTES psRequest,
    __in_opt  LPVOID pSipData,
    __out     SIGNER_CONTEXT **ppSignerContext
    );

typedef HRESULT(WINAPI *SignerTimeStampType)(
    __in      SIGNER_SUBJECT_INFO  *pSubjectInfo,
    __in      LPCWSTR              pwszHttpTimeStamp,
    __in_opt  PCRYPT_ATTRIBUTES    psRequest,
    __in_opt  LPVOID               pSipData
    );

// This function is currently documented incorrectly on MSDN.
// Source: http://stackoverflow.com/a/34367072
typedef HRESULT(WINAPI *SignerTimeStampEx2Type)(
    __in      DWORD                  dwFlags,
    __in      SIGNER_SUBJECT_INFO    *pSubjectInfo,
    __in      PCWSTR                 pwszHttpTimeStamp,
    __in      PCSTR                  pszTimeStampAlgorithmOid,
    __in_opt  PCRYPT_ATTRIBUTES      psRequest,
    __in_opt  PVOID                  pSipData,
    __out     SIGNER_CONTEXT         **ppSignerContext
    );

#define SIGNER_TIMESTAMP_AUTHENTICODE 1
#define SIGNER_TIMESTAMP_RFC3161 2

#define OID_SHA1 "1.3.14.3.2.26"
#define OID_SHA256 "2.16.840.1.101.3.4.2.1"

#endif
