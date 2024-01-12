# Copyright © 2022. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

cdef extern from "sbdf_helpers.h":
    # Utility functions for opening FILE pointers Pythonically from ``Union[str,bytes,int]``
    # (similar in behavior to Python's open() function).
    stdio.FILE* _pathlike_to_fileptr(object file, const char* mode) except NULL

    # Utility functions for managing a list of allocated C pointers and to clean them up with a specific function
    struct _AllocatedList:
        pass
    ctypedef void(*_allocated_dealloc_fn)(void *)
    void _allocated_list_new(_AllocatedList* alist, Py_ssize_t capacity)
    void _allocated_list_add(_AllocatedList* alist, void* allocated)
    void _allocated_list_done(_AllocatedList* alist, _allocated_dealloc_fn fun)

    # Utility functions and definitions for managing data types
    struct _SbdfDecimal:
        unsigned char coeff[12]
        unsigned char exponent_low
        unsigned char exponent_high_and_sign

    # Utility functions for extracting strings from Python ``Union[str,bytes]`` into C
    sbdf_c.sbdf_object* _export_extract_string_obj(object val, object invalids, Py_ssize_t start, Py_ssize_t count) \
        except NULL
    sbdf_c.sbdf_object* _export_extract_binary_obj(object val, object invalids, Py_ssize_t start, Py_ssize_t count) \
        except NULL
