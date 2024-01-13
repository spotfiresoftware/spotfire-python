/* Copyright (c) 2022. Cloud Software Group, Inc.
   This file is subject to the license terms contained
   in the license file that is distributed with this file. */

#ifndef SPOTFIRE_SBDF_HELPERS_H_
#define SPOTFIRE_SBDF_HELPERS_H_

#include <Python.h>
#include <stdio.h>
#include <all.h>

/* Utility functions for opening FILE pointers Pythonically from ``Union[str,bytes,int]``
 * (similar in behavior to Python's open() function).
 */
extern FILE *_pathlike_to_fileptr(PyObject *file, const char* mode);

/* Utility functions for managing a list of allocated C pointers and to clean them up with a specific function */
struct _AllocatedList {
    Py_ssize_t count;
    Py_ssize_t capacity;
    void **allocated;
};

typedef void(*_allocated_dealloc_fn)(void *);

extern void _allocated_list_new(struct _AllocatedList *alist, Py_ssize_t capacity);
extern void _allocated_list_add(struct _AllocatedList *alist, void *allocated);
extern void _allocated_list_done(struct _AllocatedList *alist, _allocated_dealloc_fn fun);

/* Utility functions and definitions for managing data types */
struct _SbdfDecimal {
    unsigned char coeff[12];
    unsigned char unused[2];
    unsigned char exponent_low;
    unsigned char exponent_high_and_sign;
};

/* Utility functions for extracting strings from Python ``Union[str,bytes]`` into C */
extern sbdf_object *_export_extract_string_obj(PyObject *vals, PyObject *invalids, Py_ssize_t start, Py_ssize_t count);
extern sbdf_object *_export_extract_binary_obj(PyObject *vals, PyObject *invalids, Py_ssize_t start, Py_ssize_t count);

#endif /* SPOTFIRE_SBDF_HELPERS_H_ */
