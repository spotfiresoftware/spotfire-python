/* Copyright (c) 2023. Cloud Software Group, Inc.
   This file is subject to the license terms contained
   in the license file that is distributed with this file. */

#include <Python.h>

#ifdef _WIN32

#include <windows.h>
#include <fcntl.h>
#include <fci.h>

/* Utility functions for use by the FCI callbacks; they are not exposed to the PYX file */
static wchar_t *_fci_convert_utf_to_wide(const char *utf, int *err) {
    PyObject *obj = PyUnicode_FromString(utf);
    if (obj == NULL) {
        if (PyErr_ExceptionMatches(PyExc_MemoryError)) {
            *err = ENOMEM;
        }
        else {
            *err = EINVAL;
        }
        PyErr_Clear();
        return NULL;
    }
    wchar_t *wide = PyUnicode_AsWideCharString(obj, NULL);
    if (wide == NULL) {
        *err = ENOMEM;
        PyErr_Clear();
    }
    Py_DECREF(obj);
    return wide;
}

/* FCI callback functions */
FNFCIALLOC(_fci_cb_alloc) {
    return PyMem_RawMalloc(cb);
}

FNFCIFREE(_fci_cb_free) {
    PyMem_RawFree(memory);
}

FNFCIOPEN(_fci_cb_open) {
    wchar_t *wide = _fci_convert_utf_to_wide(pszFile, err);
    if (wide == NULL) {
        return -1;
    }
    int result = _wopen(wide, oflag | O_NOINHERIT, pmode);
    PyMem_Free(wide);
    if (result == -1)
        *err = errno;
    return result;
}

FNFCIREAD(_fci_cb_read) {
    UINT result = (UINT)_read((int)hf, memory, cb);
    if (result != cb)
        *err = errno;
    return result;
}

FNFCIWRITE(_fci_cb_write) {
    UINT result = (UINT)_write((int)hf, memory, cb);
    if (result != cb)
        *err = errno;
    return result;
}

FNFCICLOSE(_fci_cb_close) {
    int result = _close((int)hf);
    if (result != 0)
        *err = errno;
    return result;
}

FNFCISEEK(_fci_cb_seek) {
    long result = (long)_lseek((int)hf, dist, seektype);
    if (result == -1)
        *err = errno;
    return result;
}

FNFCIDELETE(_fci_cb_delete) {
    wchar_t *wide = _fci_convert_utf_to_wide(pszFile, err);
    if (wide == NULL) {
        return -1;
    }
    int result = _wremove(wide);
    PyMem_Free(wide);
    if (result != 0)
        *err = errno;
    return result;
}

FNFCIFILEPLACED(_fci_cb_file_placed) {
    return 0;
}

FNFCIGETTEMPFILE(_fci_cb_get_temp_file) {
    char *name = _tempnam("", "cabtmp");
    if ((name != NULL) && ((int)strlen(name) < cbTempName)) {
        strcpy(pszTempName, name);
        free(name);
        return TRUE;
    }

    if (name) free(name);
    return FALSE;
}

FNFCISTATUS(_fci_cb_status) {
    return 0;
}

FNFCIGETNEXTCABINET(_fci_cb_get_next_cabinet) {
    return TRUE;
}

FNFCIGETOPENINFO(_fci_cb_get_open_info) {
    wchar_t *wide = _fci_convert_utf_to_wide(pszName, err);
    if (wide == NULL) {
        return -1;
    }

    /* Get file date/time */
    HANDLE handle = CreateFileW(wide, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (handle == INVALID_HANDLE_VALUE) {
        PyMem_Free(wide);
        return -1;
    }
    FILETIME ft;
    if(GetFileTime(handle, NULL, NULL, &ft) == FALSE) {
        CloseHandle(handle);
        PyMem_Free(wide);
        return -1;
    }
    CloseHandle(handle);
    FileTimeToDosDateTime(&ft, pdate, ptime);

    /* Get file attributes */
    DWORD attrs = GetFileAttributesW(wide);
    *pattribs = attrs & (_A_RDONLY | _A_SYSTEM | _A_HIDDEN | _A_ARCH);

    int result = _wopen(wide, _O_RDONLY | _O_BINARY | O_NOINHERIT);
    PyMem_Free(wide);
    return result;
}

#else  /* _WIN32 */
#endif /* _WIN32 */

