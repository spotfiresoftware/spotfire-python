/* Copyright (c) 2022. Cloud Software Group, Inc.
   This file is subject to the license terms contained
   in the license file that is distributed with this file. */

#include "sbdf_helpers.h"
#include "sbdf.h"

/* Utility functions for opening FILE pointers Pythonically from ``Union[str,bytes,int]``
 * (similar in behavior to Python's open() function).
 */
FILE *_pathlike_to_fileptr(PyObject *file, const char* mode) {
    FILE *the_file = NULL;
    int fd;
    char *filename;
    PyObject *filename_obj;

    /* int: use the given file descriptor */
    if(PyLong_Check(file)) {
        fd = PyObject_AsFileDescriptor(file);
        if(fd == -1) return NULL;
        the_file = fdopen(fd, mode);
    /* bytes: use the given file name */
    } else if(PyBytes_Check(file)) {
        filename = PyBytes_AsString(file);
        the_file = fopen(filename, mode);
    /* unicode/str: decode the given filename as utf-8 */
    } else if(PyUnicode_Check(file)) {
        if(!PyUnicode_FSConverter(file, &filename_obj)) return NULL;
        filename = PyBytes_AsString(filename_obj);
        the_file = fopen(filename, mode);
        Py_XDECREF(filename_obj);
    /* else: raise an exception */
    } else {
        PyErr_SetString(PyExc_TypeError, "str, bytes, or integer argument expected");
    }

    if(the_file == NULL) {
        PyErr_SetFromErrno(PyExc_IOError);
    }
    return the_file;
}

/* Utility functions for managing a list of allocated C pointers and to clean them up with a specific function */
void _allocated_list_new(struct _AllocatedList *alist, int capacity) {
    alist->count = 0;
    alist->capacity = capacity;
    alist->allocated = PyMem_RawMalloc(capacity * sizeof(struct _AllocatedList));
}

void _allocated_list_add(struct _AllocatedList *alist, void *allocated) {
    if (alist->count == alist->capacity) {
        alist->capacity *= 2;
        alist->allocated = PyMem_RawRealloc(alist->allocated, alist->capacity * sizeof(struct _AllocatedList));
    }
    alist->allocated[alist->count++] = allocated;
}

void _allocated_list_done(struct _AllocatedList *alist, _allocated_dealloc_fn fun) {
    for(int i = 0; i < alist->count; i++) {
        fun(alist->allocated[i]);
        alist->allocated[i] = NULL;
    }
}

/* Utility functions for extracting strings from Python ``Union[str,bytes]`` into C */
sbdf_object *_export_extract_string_obj(PyObject *vals, PyObject *invalids, Py_ssize_t start, Py_ssize_t count) {
    sbdf_object *t = calloc(1, sizeof(sbdf_object));

    t->type = sbdf_vt_string();
    t->count = (int)count;
    char **data = (char **)calloc(count, sizeof(char *));
    if (!data)
    {
        PyErr_Format(PyExc_MemoryError, "memory exhausted");
        sbdf_obj_destroy(t);
        return NULL;
    }
    t->data = data;

    for(int i = 0; i < count; i++) {
        Py_ssize_t idx = start + i;
        PyObject *inv = PySequence_GetItem(invalids, idx);
        if(inv == NULL) {
            sbdf_obj_destroy(t);
            return NULL;
        }
        if(PyObject_IsTrue(inv)) {
            /* true: invalid value, add empty value to t->data */
            data[i] = sbdf_str_create_len("", 0);
        } else {
            /* false: valid value, add encoded value to t->data */
            PyObject *val = PySequence_GetItem(vals, idx);
            if(val == NULL) {
                Py_XDECREF(inv);
                sbdf_obj_destroy(t);
                return NULL;
            }
            PyObject *val_str = PyObject_Str(val);
            if(val_str == NULL) {
                Py_XDECREF(val);
                Py_XDECREF(inv);
                sbdf_obj_destroy(t);
                return NULL;
            }
            PyObject *val_encoded = PyObject_CallMethod(val_str, "encode", "s", "utf-8");
            if(val_encoded == NULL) {
                Py_XDECREF(val_str);
                Py_XDECREF(val);
                Py_XDECREF(inv);
                sbdf_obj_destroy(t);
                return NULL;
            }
            char *val_buf;
            Py_ssize_t val_len;
            if(PyBytes_AsStringAndSize(val_encoded, &val_buf, &val_len) == -1) {
                Py_XDECREF(val_encoded);
                Py_XDECREF(val_str);
                Py_XDECREF(val);
                Py_XDECREF(inv);
                sbdf_obj_destroy(t);
                return NULL;
            }
            data[i] = sbdf_str_create_len(val_buf, (int)val_len);
            Py_XDECREF(val_encoded);
            Py_XDECREF(val_str);
            Py_XDECREF(val);
        }
        Py_XDECREF(inv);
    }

    return t;
}

sbdf_object *_export_extract_binary_obj(PyObject *vals, PyObject *invalids, Py_ssize_t start, Py_ssize_t count) {
    sbdf_object *t = calloc(1, sizeof(sbdf_object));

    t->type = sbdf_vt_binary();
    t->count = (int)count;
    unsigned char **data = (unsigned char **)calloc(count, sizeof(unsigned char *));
    if (!data)
    {
        PyErr_Format(PyExc_MemoryError, "memory exhausted");
        sbdf_obj_destroy(t);
        return NULL;
    }
    t->data = data;

    for(int i = 0; i < count; i++) {
        Py_ssize_t idx = start + i;
        PyObject *inv = PySequence_GetItem(invalids, idx);
        if(inv == NULL) {
            sbdf_obj_destroy(t);
            return NULL;
        }
        if(PyObject_IsTrue(inv)) {
            /* true: invalid value, add empty value to t->data */
            data[i] = sbdf_ba_create(0, 0);
        } else {
            /* false: valid value, add value to t->data */
            PyObject *val = PySequence_GetItem(vals, idx);
            if(val == NULL) {
                Py_XDECREF(inv);
                sbdf_obj_destroy(t);
                return NULL;
            }
            if(!PyBytes_Check(val)) {
                PyErr_Format(PyExc_SBDFError, "cannot convert '%S' to Spotfire Binary type; incompatible types", val);
                Py_XDECREF(val);
                Py_XDECREF(inv);
                sbdf_obj_destroy(t);
                return NULL;
            }
            char *val_buf;
            Py_ssize_t val_len;
            if(PyBytes_AsStringAndSize(val, &val_buf, &val_len) == -1) {
                Py_XDECREF(val);
                Py_XDECREF(inv);
                sbdf_obj_destroy(t);
                return NULL;
            }
            data[i] = sbdf_ba_create((unsigned char *)val_buf, (int)val_len);
            Py_XDECREF(val);
        }
        Py_XDECREF(inv);
    }

    return t;
}
