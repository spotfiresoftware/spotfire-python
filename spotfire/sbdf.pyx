# cython: language_level=3

# Copyright © 2022. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Functions to import data tables into Python from SBDF files and export data from Python to SBDF files."""

import collections.abc
import datetime
import decimal
import io
import warnings

import cython

import spotfire
from spotfire import _utils

import numpy as np
import pandas as pd

from libc cimport stdio, string, limits
from cpython cimport datetime as datetime_c, mem
cimport numpy as np_c
from vendor cimport sbdf_c


# Dynamically load optional modules
try:
    import geopandas as gpd
    import shapely
    import shapely.wkb
    import shapely.geometry.base as shp_geom
except ImportError:
    gpd = None
    shapely = None
    shp_geom = None

try:
    import matplotlib
    import matplotlib.figure
    import matplotlib.pyplot
except ImportError:
    matplotlib = None

try:
    import seaborn
except ImportError:
    seaborn = None

try:
    import PIL
    import PIL.Image
except ImportError:
    PIL = None

try:
    import polars as pl
except ImportError:
    pl = None


# Various utility helper functions for doing things that are problematic in PYX files
include "sbdf_helpers.pxi"


# Initialize modules
np_c.import_array()
datetime_c.import_datetime()


# Exceptions raised by this module
class SBDFError(Exception):
    """An exception that is raised to indicate a problem during import or export of SBDF files."""


cdef public object PyExc_SBDFError = <object>SBDFError


# Warnings raised by this module
class SBDFWarning(Warning):
    """A warning that is raised to indicate an issue during import or export of SBDF files."""


import enum


class OutputFormat(enum.Enum):
    """Supported output formats for :func:`import_data`."""
    PANDAS = "pandas"
    POLARS = "polars"


# Utility functions and definitions for managing data types
cdef extern from *:
    """
    #define _USECS_PER_MSEC 1000
    #define _MSECS_PER_SEC  1000
    #define _SECS_PER_DAY   86400
    """
    int _USECS_PER_MSEC
    int _MSECS_PER_SEC
    int _SECS_PER_DAY


cdef object _timedelta_from_msec(long long msec):
    """Create a new ``timedelta`` object based on a number of milliseconds.

    :param msec: number of milliseconds
    :return: new timedelta object
    """
    cdef int days = <int>(msec // (_SECS_PER_DAY * _MSECS_PER_SEC))
    cdef int sec = <int>((msec // _MSECS_PER_SEC) % _SECS_PER_DAY)
    cdef int usec = <int>((msec % _MSECS_PER_SEC) * _USECS_PER_MSEC)
    return datetime_c.timedelta_new(days, sec, usec)


cdef object _DATETIME_EPOCH = datetime.datetime(1, 1, 1)
cdef object _TIMEDELTA_ONE_MSEC = _timedelta_from_msec(1)

# Milliseconds between the SBDF epoch (datetime(1, 1, 1)) and the Unix epoch (datetime(1970, 1, 1)).
# = 719162 days * 86400 s/day * 1000 ms/s, derived from:
#   (datetime.datetime(1970, 1, 1) - datetime.datetime(1, 1, 1)).total_seconds() * 1000
# Used in the Polars import path to convert raw SBDF int64 ms values to Unix-based int64 ms values
# without boxing through Python datetime objects.
cdef long long _SBDF_TO_UNIX_EPOCH_MS = 62135596800000


cdef extern from *:
    """
    #define _DECIMAL_EXPONENT_BIAS 6176
    """
    int _DECIMAL_EXPONENT_BIAS


cdef object _decimal_from_bytes(_SbdfDecimal* value):
    """Convert a 16-byte SBDF decimal value to a Python ``Decimal`` object.

    :param value: SBDF decimal value
    :return: new Decimal object
    """
    # Coefficient
    coefficient = 0
    cdef int i
    for i in range(11, -1, -1):
        coefficient <<= 8
        coefficient |= value.coeff[i]
    # Exponent
    exponent = ((((value.exponent_high_and_sign << 8) | value.exponent_low) & 0x7FFE) >> 1) - _DECIMAL_EXPONENT_BIAS
    # Sign bit
    if value.exponent_high_and_sign >> 7:
        sign = 1
    else:
        sign = 0

    # Break up the coefficient into digits
    digits = []
    while coefficient != 0:
        digits.insert(0, coefficient % 10)
        coefficient //= 10

    return decimal.Decimal((sign, tuple(digits), exponent))


cdef _SbdfDecimal _decimal_to_bytes(dec: decimal.Decimal):
    """Convert a Python ``Decimal`` object to a 16-byte SBDF decimal value.

    :param dec: Decimal object
    :return: new SBDF decimal value
    """
    if not isinstance(dec, decimal.Decimal):
        raise TypeError("cannot convert non-decimal")
    cdef _SbdfDecimal out
    cdef int i
    dec_tuple = dec.as_tuple()
    string.memset(&out, 0, sizeof(_SbdfDecimal))

    # Coefficient
    coefficient = 0
    for digit in dec_tuple.digits:
        coefficient *= 10
        coefficient += digit
    for i in range(12):
        out.coeff[i] = coefficient & 0xFF
        coefficient >>= 8
    if coefficient:
        raise ValueError("too many digits in coefficient")
    # Exponent and sign bit
    biased_exponent = dec_tuple.exponent + _DECIMAL_EXPONENT_BIAS
    out.exponent_low = (biased_exponent & 0x7F) << 1
    out.exponent_high_and_sign = (dec_tuple.sign << 7) | (biased_exponent >> 7)

    return out


def _valuetype_id_to_spotfire_typename(typeid: int):
    """Convert an internal value type ID into the Spotfire type name that it represents.

    :param typeid: the integer value type ID
    :return: the Spotfire type name, or ``None`` if typeid does not represent a value type
    """
    if typeid == sbdf_c.SBDF_BOOLTYPEID:
        return "Boolean"
    elif typeid == sbdf_c.SBDF_INTTYPEID:
        return "Integer"
    elif typeid == sbdf_c.SBDF_LONGTYPEID:
        return "LongInteger"
    elif typeid == sbdf_c.SBDF_FLOATTYPEID:
        return "SingleReal"
    elif typeid == sbdf_c.SBDF_DOUBLETYPEID:
        return "Real"
    elif typeid == sbdf_c.SBDF_DATETIMETYPEID:
        return "DateTime"
    elif typeid == sbdf_c.SBDF_DATETYPEID:
        return "Date"
    elif typeid == sbdf_c.SBDF_TIMETYPEID:
        return "Time"
    elif typeid == sbdf_c.SBDF_TIMESPANTYPEID:
        return "TimeSpan"
    elif typeid == sbdf_c.SBDF_STRINGTYPEID:
        return "String"
    elif typeid == sbdf_c.SBDF_BINARYTYPEID:
        return "Binary"
    elif typeid == sbdf_c.SBDF_DECIMALTYPEID:
        return "Currency"
    else:
        return None


def spotfire_typename_to_valuetype_id(typename: str):
    """Convert a Spotfire type name into the internal value type ID that it represents.

    :param typename: the Spotfire type name
    :return: the integer value type ID, or ``None`` if typename does not represent a value type
    """
    if typename == "Boolean":
        return sbdf_c.SBDF_BOOLTYPEID
    elif typename == "Integer":
        return sbdf_c.SBDF_INTTYPEID
    elif typename == "LongInteger":
        return sbdf_c.SBDF_LONGTYPEID
    elif typename == "SingleReal":
        return sbdf_c.SBDF_FLOATTYPEID
    elif typename == "Real":
        return sbdf_c.SBDF_DOUBLETYPEID
    elif typename == "DateTime":
        return sbdf_c.SBDF_DATETIMETYPEID
    elif typename == "Date":
        return sbdf_c.SBDF_DATETYPEID
    elif typename == "Time":
        return sbdf_c.SBDF_TIMETYPEID
    elif typename == "TimeSpan":
        return sbdf_c.SBDF_TIMESPANTYPEID
    elif typename == "String":
        return sbdf_c.SBDF_STRINGTYPEID
    elif typename == "Binary":
        return sbdf_c.SBDF_BINARYTYPEID
    elif typename == "Currency":
        return sbdf_c.SBDF_DECIMALTYPEID
    else:
        return None


# Import data from SBDF into Python.
@cython.auto_pickle(False)
cdef class _ImportContext:
    """Object to store information for each column as it is imported."""
    cdef int numpy_type_num
    cdef sbdf_c.sbdf_valuetype value_type
    cdef list values_arrays
    cdef list invalid_arrays

    def __init__(self, numpy_type_num: int, vt: sbdf_c.sbdf_valuetype):
        """Initialize the import context, including the holding arrays.

        :param numpy_type_num: NumPy type number for the value array; see
                               https://numpy.org/doc/stable/reference/c-api/dtype.html#enumerated-types for more
                               information
        :param vt: SBDF value type
        """
        # Store the NumPy type number
        self.numpy_type_num = numpy_type_num

        # Initialize the SBDF value type
        self.value_type = vt

        # Create a zero-element array for holding values
        cdef np_c.npy_intp shape[1]
        shape[0] = <np_c.npy_intp>0
        self.values_arrays = []

        # Create a zero-element array for holding invalids
        self.invalid_arrays = []

    cdef (int, sbdf_c.sbdf_object*, sbdf_c.sbdf_object*) get_values_and_invalid(self,
                                                                                sbdf_c.sbdf_columnslice* col_slice):
        """Extract the values and invalid arrays from the column slice.

        :param col_slice: the SBDF column slice to extract from
        :return: tuple containing SBDF error code, SBDF value object, and SBDF invalids object
        """
        # Unpack the value array values
        cdef sbdf_c.sbdf_object* values = NULL
        cdef int error = sbdf_c.sbdf_va_get_values(col_slice.values, &values)
        if error != sbdf_c.SBDF_OK:
            return error, NULL, NULL
        self.value_type = values.type

        # Unpack the invalid value array
        cdef sbdf_c.sbdf_valuearray* invalid_va = NULL
        cdef sbdf_c.sbdf_object* invalid = NULL
        error = sbdf_c.sbdf_cs_get_property(col_slice, sbdf_c.SBDF_ISINVALID_VALUEPROPERTY, &invalid_va)
        if error == sbdf_c.SBDF_OK:
            error = sbdf_c.sbdf_va_get_values(invalid_va, &invalid)
            if error != sbdf_c.SBDF_OK:
                self.cleanup_values_and_invalid(values, invalid)
                return error, NULL, NULL
        elif error != sbdf_c.SBDF_ERROR_PROPERTY_NOT_FOUND:
            self.cleanup_values_and_invalid(values, invalid)
            return error, NULL, NULL

        return sbdf_c.SBDF_OK, values, invalid

    cdef void cleanup_values_and_invalid(self, sbdf_c.sbdf_object* values, sbdf_c.sbdf_object* invalid):
        """Properly clean up the values and invalid arrays from the SBDF API.

        :param values: SBDF value object to clean up
        :param invalid: SBDF invalids object to clean up
        """
        if invalid != NULL:
            sbdf_c.sbdf_obj_destroy(invalid)
        sbdf_c.sbdf_obj_destroy(values)

    cdef np_c.ndarray new_slice_from_data(self, int count, void* data):
        """Create a NumPy slice ``ndarray`` from the given data.

        :param count: the number of values in the data
        :param data: the data
        :return: new values NumPy slice array
        """
        cdef np_c.npy_intp shape[1]
        shape[0] = <np_c.npy_intp>count
        snfd = np_c.PyArray_SimpleNewFromData(1, shape, self.numpy_type_num, data)
        return np_c.PyArray_NewCopy(snfd, np_c.NPY_ORDER.NPY_CORDER)

    cdef np_c.ndarray new_slice_from_empty(self, int count):
        """Create a NumPy slice ``ndarray`` capable of holding the given amount of data, to be filled in later.

        :param count: the number of values to be able to hold
        :return: new values NumPy slice array
        """
        cdef np_c.npy_intp shape[1]
        shape[0] = <np_c.npy_intp>count
        return np_c.PyArray_EMPTY(1, shape, self.numpy_type_num, 0)

    cdef np_c.ndarray new_slice_from_invalid(self, int count, sbdf_c.sbdf_object* invalid):
        """Create a boolean NumPy slice ``ndarray`` from the invalid array.

        :param count: the number of values in the data
        :param invalid: the SBDF invalids object
        :return: new invalid NumPy slice array
        """
        cdef np_c.npy_intp shape[1]
        shape[0] = <np_c.npy_intp>count
        if invalid != NULL:
            snfd = np_c.PyArray_SimpleNewFromData(1, shape, np_c.NPY_BOOL, <void*>invalid.data)
            return np_c.PyArray_NewCopy(snfd, np_c.NPY_ORDER.NPY_CORDER)
        else:
            return np_c.PyArray_ZEROS(1, shape, np_c.NPY_BOOL, 0)

    cdef void append_values_slice(self, np_c.ndarray values_slice, np_c.ndarray invalid_slice):
        """Append the NumPy slice arrays to the full table values

        :param values_slice: values NumPy slice array to append
        :param invalid_slice: invalid NumPy slice array to append
        """
        self.values_arrays.append(values_slice)
        self.invalid_arrays.append(invalid_slice)

    cpdef np_c.ndarray get_values_array(self):
        """Get the full table values ``ndarray``.

        :return: the full values NumPy array
        """
        # Build concatenated numpy array
        if self.values_arrays:
            return np.concatenate(self.values_arrays)
        else:
            return np.array([], dtype=np.dtype(self.get_numpy_dtype()))

    cpdef np_c.ndarray get_invalid_array(self):
        """Get the full table invalid ``ndarray``.

        :return: the full invalid NumPy array
        """
        # Build concatenated numpy array
        if self.invalid_arrays:
            return np.concatenate(self.invalid_arrays)
        else:
            return np.array([], dtype=np.bool_)

    def get_pandas_dtype_name(self) -> str:
        """Get the correct Pandas dtype for this column.

        :return: the Pandas dtype name for this column
        """
        if self.numpy_type_num == np_c.NPY_INT32:
            return "Int32"
        elif self.numpy_type_num == np_c.NPY_INT64:
            return "Int64"
        elif self.numpy_type_num == np_c.NPY_FLOAT32:
            return "float32"
        elif self.numpy_type_num == np_c.NPY_FLOAT64:
            return "float64"
        else:
            return "object"

    def get_numpy_dtype(self):
        """Get the correct NumPy dtype for this ctype.

        :return: the NumPy dtype name for this ctype
        """
        if self.numpy_type_num == np_c.NPY_INT32:
            return "int32"
        elif self.numpy_type_num == np_c.NPY_INT64:
            return "int64"
        elif self.numpy_type_num == np_c.NPY_FLOAT32:
            return "float32"
        elif self.numpy_type_num == np_c.NPY_FLOAT64:
            return "float64"
        elif self.numpy_type_num == np_c.NPY_BOOL:
            return "bool"
        else:
            return "object"

    def get_spotfire_type_name(self) -> str:
        """Get the correct Spotfire type name for this column.

        :return: the Spotfire type name for this column
        """
        return _valuetype_id_to_spotfire_typename(self.value_type.id)

    cpdef bint is_object_numpy_type(self):
        """Return True if the numpy type for this column is NPY_OBJECT.

        :return: True if the numpy type is object, False otherwise

        .. note:: ``numpy_type_num`` is a ``cdef`` attribute and is therefore inaccessible from
                  Python-side ``cdef object`` functions.  This ``cpdef`` wrapper exposes it so that
                  :func:`_import_build_polars_dataframe` can branch on it without touching the
                  Cython-only attribute directly.
        """
        return self.numpy_type_num == np_c.NPY_OBJECT

    cpdef int get_value_type_id(self):
        """Return the SBDF value type ID for this column.

        :return: the integer SBDF value type ID

        .. note:: ``value_type`` is a ``cdef`` C struct attribute inaccessible from Python.  This
                  ``cpdef`` wrapper lets :func:`_import_build_polars_dataframe` dispatch on type
                  without a Cython-level cast.
        """
        return self.value_type.id

    cpdef void clear_values_arrays(self):
        """Release the internal per-slice values arrays to allow early garbage collection.

        Call this after :meth:`get_values_array` has produced the concatenated result and the
        caller no longer needs the per-slice data.  Dropping these references makes the underlying
        NPY_OBJECT (or NPY_INT64) slice arrays eligible for GC before the Polars Arrow buffer is
        allocated, reducing peak memory from three live copies to two (or one, for types where
        Polars can reference the numpy buffer directly).
        """
        self.values_arrays = []


# Individual functions for importing each value type.
ctypedef int(*importer_fn)(_ImportContext, sbdf_c.sbdf_columnslice*)


cdef int _import_vts_numpy(_ImportContext context, sbdf_c.sbdf_columnslice* col_slice):
    """Import a column slice using NumPy to directly load from memory allocated by the SBDF API."""
    cdef int error
    (error, values, invalid) = context.get_values_and_invalid(col_slice)
    if error == sbdf_c.SBDF_OK:
        values_slice = context.new_slice_from_data(values.count, <void*>values.data)
        invalid_slice = context.new_slice_from_invalid(values.count, invalid)
        context.append_values_slice(values_slice, invalid_slice)
        context.cleanup_values_and_invalid(values, invalid)
    return error


cdef int _import_vt_datetime(_ImportContext context, sbdf_c.sbdf_columnslice* col_slice):
    """Import a column slice consisting of datetime values."""
    cdef int error
    (error, values, invalid) = context.get_values_and_invalid(col_slice)
    cdef long long* data
    cdef int i
    if error == sbdf_c.SBDF_OK:
        values_slice = context.new_slice_from_empty(values.count)
        data = <long long*>values.data
        for i in range(values.count):
            values_slice[i] = _DATETIME_EPOCH + _timedelta_from_msec(data[i])
        invalid_slice = context.new_slice_from_invalid(values.count, invalid)
        context.append_values_slice(values_slice, invalid_slice)
        context.cleanup_values_and_invalid(values, invalid)
    return error


cdef int _import_vt_date(_ImportContext context, sbdf_c.sbdf_columnslice* col_slice):
    """Import a column slice consisting of date values."""
    cdef int error
    (error, values, invalid) = context.get_values_and_invalid(col_slice)
    cdef long long* data
    cdef int i
    if error == sbdf_c.SBDF_OK:
        values_slice = context.new_slice_from_empty(values.count)
        data = <long long*>values.data
        for i in range(values.count):
            values_slice[i] = (_DATETIME_EPOCH + _timedelta_from_msec(data[i])).date()
        invalid_slice = context.new_slice_from_invalid(values.count, invalid)
        context.append_values_slice(values_slice, invalid_slice)
        context.cleanup_values_and_invalid(values, invalid)
    return error


cdef int _import_vt_date_int32(_ImportContext context, sbdf_c.sbdf_columnslice* col_slice):
    """Import a date column slice as int32 days since Unix epoch (Polars path only).

    Converts the raw SBDF int64 millisecond values to int32 days at the C level, writing
    directly into an NPY_INT32 slice.  This avoids an intermediate int64 array and the
    subsequent astype(np.int32) copy, reducing total allocations from C data to one.

    SBDF dates are always stored at midnight (exact multiples of 86400000 ms), so C
    integer division equals Python floor division for both positive and negative offsets.
    """
    cdef int error
    (error, values, invalid) = context.get_values_and_invalid(col_slice)
    cdef long long* data
    cdef int i
    if error == sbdf_c.SBDF_OK:
        values_slice = context.new_slice_from_empty(values.count)
        data = <long long*>values.data
        for i in range(values.count):
            values_slice[i] = <int>((data[i] - _SBDF_TO_UNIX_EPOCH_MS) / 86400000)
        invalid_slice = context.new_slice_from_invalid(values.count, invalid)
        context.append_values_slice(values_slice, invalid_slice)
        context.cleanup_values_and_invalid(values, invalid)
    return error


cdef int _import_vt_time_int64(_ImportContext context, sbdf_c.sbdf_columnslice* col_slice):
    """Import a time column slice as int64 ns since midnight (Polars path only).

    SBDF Time values are stored as int64 milliseconds since midnight.  Polars Time is
    stored as int64 nanoseconds since midnight internally in Arrow, so each value is
    multiplied by 1,000,000.  pl.Series(int64, pl.Time) then wraps the buffer zero-copy.
    """
    cdef int error
    (error, values, invalid) = context.get_values_and_invalid(col_slice)
    cdef long long* data
    cdef Py_ssize_t i
    if error == sbdf_c.SBDF_OK:
        values_slice = context.new_slice_from_empty(values.count)
        data = <long long*>values.data
        for i in range(values.count):
            values_slice[i] = data[i] * 1000000
        invalid_slice = context.new_slice_from_invalid(values.count, invalid)
        context.append_values_slice(values_slice, invalid_slice)
        context.cleanup_values_and_invalid(values, invalid)
    return error


cdef int _import_vt_time(_ImportContext context, sbdf_c.sbdf_columnslice* col_slice):
    """Import a column slice consisting of time values."""
    cdef int error
    (error, values, invalid) = context.get_values_and_invalid(col_slice)
    cdef long long* data
    cdef int i
    if error == sbdf_c.SBDF_OK:
        values_slice = context.new_slice_from_empty(values.count)
        data = <long long*>values.data
        for i in range(values.count):
            values_slice[i] = (_DATETIME_EPOCH + _timedelta_from_msec(data[i])).timetz()
        invalid_slice = context.new_slice_from_invalid(values.count, invalid)
        context.append_values_slice(values_slice, invalid_slice)
        context.cleanup_values_and_invalid(values, invalid)
    return error


cdef int _import_vt_timespan(_ImportContext context, sbdf_c.sbdf_columnslice* col_slice):
    """Import a column slice consisting of timespan values."""
    cdef int error
    (error, values, invalid) = context.get_values_and_invalid(col_slice)
    cdef long long* data
    cdef int i
    if error == sbdf_c.SBDF_OK:
        values_slice = context.new_slice_from_empty(values.count)
        data = <long long*>values.data
        for i in range(values.count):
            values_slice[i] = _timedelta_from_msec(data[i])
        invalid_slice = context.new_slice_from_invalid(values.count, invalid)
        context.append_values_slice(values_slice, invalid_slice)
        context.cleanup_values_and_invalid(values, invalid)
    return error


cdef int _import_vt_string(_ImportContext context, sbdf_c.sbdf_columnslice* col_slice):
    """Import a column slice consisting of string values."""
    cdef int error
    (error, values, invalid) = context.get_values_and_invalid(col_slice)
    cdef char** data
    cdef int i
    if error == sbdf_c.SBDF_OK:
        values_slice = context.new_slice_from_empty(values.count)
        data = <char**>values.data
        for i in range(values.count):
            i_len = sbdf_c.sbdf_str_len(<const char*>data[i])
            values_slice[i] = data[i][:i_len].decode("utf-8")
        invalid_slice = context.new_slice_from_invalid(values.count, invalid)
        context.append_values_slice(values_slice, invalid_slice)
        context.cleanup_values_and_invalid(values, invalid)
    return error


cdef int _import_vt_bytes(_ImportContext context, sbdf_c.sbdf_columnslice* col_slice):
    """Import a column slice consisting of bytes values."""
    cdef int error
    (error, values, invalid) = context.get_values_and_invalid(col_slice)
    cdef void** data
    cdef int i
    if error == sbdf_c.SBDF_OK:
        values_slice = context.new_slice_from_empty(values.count)
        data = <void**>values.data
        for i in range(values.count):
            i_len = sbdf_c.sbdf_ba_get_len(<const unsigned char*>data[i])
            values_slice[i] = (<char*>data[i])[:i_len]
        invalid_slice = context.new_slice_from_invalid(values.count, invalid)
        context.append_values_slice(values_slice, invalid_slice)
        context.cleanup_values_and_invalid(values, invalid)
    return error


cdef int _import_vt_decimal(_ImportContext context, sbdf_c.sbdf_columnslice* col_slice):
    """Import a column slice consisting of decimal values."""
    cdef int error
    (error, values, invalid) = context.get_values_and_invalid(col_slice)
    cdef _SbdfDecimal* data
    cdef int i
    if error == sbdf_c.SBDF_OK:
        values_slice = context.new_slice_from_empty(values.count)
        data = <_SbdfDecimal*>values.data
        for i in range(values.count):
            values_slice[i] = _decimal_from_bytes(&data[i])
        invalid_slice = context.new_slice_from_invalid(values.count, invalid)
        context.append_values_slice(values_slice, invalid_slice)
        context.cleanup_values_and_invalid(values, invalid)
    return error


cdef dict _import_metadata(sbdf_c.sbdf_metadata_head* md, int column_num):
    """Process an SBDF API metadata structure into its Python equivalent.

    :param md: SBDF metadata structure
    :param column_num: 0-based column number, or -1 for table metadata
    """
    metadata = {}
    cdef sbdf_c.sbdf_metadata* md_iter = md.first
    cdef sbdf_c.sbdf_object* obj = NULL
    cdef int i
    cdef char** data_string
    cdef double* data_double
    cdef long* data_long
    cdef float* data_float
    cdef int* data_int
    cdef unsigned char* data_bool
    cdef long long* data_datetime
    cdef void** data_bytes
    cdef _SbdfDecimal* data_decimal

    if column_num == -1:
        column_num_str = "Table"
    else:
        column_num_str = f"Column {column_num}"

    while md_iter != NULL:
        # Do not process the column name or type entries
        if string.strcmp(md_iter.name, sbdf_c.SBDF_COLUMNMETADATA_NAME) == 0 or \
           string.strcmp(md_iter.name, sbdf_c.SBDF_COLUMNMETADATA_DATATYPE) == 0:
            md_iter = md_iter.next
            continue

        # Extract the metadata entry name
        name = md_iter.name.decode("utf-8")

        # Decode the value based on its type
        obj = md_iter.value
        md_val = []
        if obj.type.id == sbdf_c.SBDF_STRINGTYPEID:
            data_string = <char**>obj.data
            for i in range(obj.count):
                i_len = sbdf_c.sbdf_str_len(<const char*>data_string[i])
                md_val.append(data_string[i][:i_len].decode("utf-8"))
        elif obj.type.id == sbdf_c.SBDF_DOUBLETYPEID:
            data_double = <double*>obj.data
            for i in range(obj.count):
                md_val.append(data_double[i])
        elif obj.type.id == sbdf_c.SBDF_LONGTYPEID:
            data_long = <long*>obj.data
            for i in range(obj.count):
                md_val.append(data_long[i])
        elif obj.type.id == sbdf_c.SBDF_FLOATTYPEID:
            data_float = <float*>obj.data
            for i in range(obj.count):
                md_val.append(data_float[i])
        elif obj.type.id == sbdf_c.SBDF_INTTYPEID:
            data_int = <int*>obj.data
            for i in range(obj.count):
                md_val.append(data_int[i])
        elif obj.type.id == sbdf_c.SBDF_BOOLTYPEID:
            data_bool = <unsigned char*>obj.data
            for i in range(obj.count):
                md_val.append(data_bool[i] != 0)
        elif obj.type.id == sbdf_c.SBDF_DATETIMETYPEID:
            data_datetime = <long long*>obj.data
            for i in range(obj.count):
                md_val.append(_DATETIME_EPOCH + _timedelta_from_msec(data_datetime[i]))
        elif obj.type.id == sbdf_c.SBDF_DATETYPEID:
            data_datetime = <long long*>obj.data
            for i in range(obj.count):
                md_val.append((_DATETIME_EPOCH + _timedelta_from_msec(data_datetime[i])).date())
        elif obj.type.id == sbdf_c.SBDF_TIMETYPEID:
            data_datetime = <long long*>obj.data
            for i in range(obj.count):
                md_val.append((_DATETIME_EPOCH + _timedelta_from_msec(data_datetime[i])).timetz())
        elif obj.type.id == sbdf_c.SBDF_TIMESPANTYPEID:
            data_datetime = <long long*>obj.data
            for i in range(obj.count):
                md_val.append(_timedelta_from_msec(data_datetime[i]))
        elif obj.type.id == sbdf_c.SBDF_BINARYTYPEID:
            data_bytes = <void**>obj.data
            for i in range(obj.count):
                i_len = sbdf_c.sbdf_ba_get_len(<const unsigned char*>data_bytes[i])
                md_val.append((<char*>data_bytes[i])[:i_len])
        elif obj.type.id == sbdf_c.SBDF_DECIMALTYPEID:
            data_decimal = <_SbdfDecimal*>obj.data
            for i in range(obj.count):
                md_val.append(_decimal_from_bytes(&data_decimal[i]))

        # Add the decoded value to the Python equivalent, and progress to the next entry
        metadata[name] = md_val
        md_iter = md_iter.next

    return metadata


cdef object _import_polars_dtype(_ImportContext context):
    """Return the Polars dtype corresponding to the SBDF value type in the import context.

    :param context: import context for a column
    :return: the Polars dtype object
    """
    vt_id = context.value_type.id
    if vt_id == sbdf_c.SBDF_BOOLTYPEID:
        return pl.Boolean
    elif vt_id == sbdf_c.SBDF_INTTYPEID:
        return pl.Int32
    elif vt_id == sbdf_c.SBDF_LONGTYPEID:
        return pl.Int64
    elif vt_id == sbdf_c.SBDF_FLOATTYPEID:
        return pl.Float32
    elif vt_id == sbdf_c.SBDF_DOUBLETYPEID:
        return pl.Float64
    elif vt_id == sbdf_c.SBDF_STRINGTYPEID:
        return pl.Utf8
    elif vt_id == sbdf_c.SBDF_DATETIMETYPEID:
        return pl.Datetime
    elif vt_id == sbdf_c.SBDF_DATETYPEID:
        return pl.Date
    elif vt_id == sbdf_c.SBDF_TIMETYPEID:
        return pl.Time
    elif vt_id == sbdf_c.SBDF_TIMESPANTYPEID:
        return pl.Duration
    elif vt_id == sbdf_c.SBDF_BINARYTYPEID:
        return pl.Binary
    elif vt_id == sbdf_c.SBDF_DECIMALTYPEID:
        return pl.Decimal
    else:
        raise SBDFError(f"unsupported SBDF value type id {vt_id} for Polars output")


cdef object _import_build_polars_dataframe(column_names, importer_contexts):
    """Build a Polars DataFrame directly from import context data, with no Pandas intermediary.

    :param column_names: list of column name strings
    :param importer_contexts: list of _ImportContext objects
    :return: a Polars DataFrame
    """
    warnings.warn(
        "Polars DataFrames do not support Spotfire metadata; table and column metadata are not "
        "preserved. See https://github.com/pola-rs/polars/issues/5117",
        SBDFWarning
    )
    series_list = []
    for i, name in enumerate(column_names):
        context = importer_contexts[i]
        invalids = context.get_invalid_array()
        vt_id = context.get_value_type_id()

        if vt_id == sbdf_c.SBDF_DATETIMETYPEID:
            # Raw int64 ms since SBDF epoch → subtract fixed offset → Int64 Series →
            # cast to Datetime('ms').  Polars' cast between Int64 and Datetime('ms') is a
            # zero-copy metadata operation (both are int64 internally in Arrow), so the
            # Series shares the same buffer as the numpy array: 1 copy total from C data.
            values = context.get_values_array()
            context.clear_values_arrays()
            values -= _SBDF_TO_UNIX_EPOCH_MS
            col = pl.Series(name=name, values=values, dtype=pl.Int64).cast(pl.Datetime('ms'))
            if invalids.any():
                col = col.scatter(np.where(invalids)[0], None)

        elif vt_id == sbdf_c.SBDF_DATETYPEID:
            # _import_vt_date_int32 already converted ms→days and wrote int32 directly.
            # pl.Series(int32, pl.Date) is zero-copy: 1 copy total from C data.
            values = context.get_values_array()
            context.clear_values_arrays()
            col = pl.Series(name=name, values=values, dtype=pl.Date)
            if invalids.any():
                col = col.scatter(np.where(invalids)[0], None)

        elif vt_id == sbdf_c.SBDF_TIMESPANTYPEID:
            # Timespans are int64 ms with no epoch bias.  Duration('ms') is int64 in Arrow,
            # so the cast is zero-copy: 1 copy total from C data.
            values = context.get_values_array()
            context.clear_values_arrays()
            col = pl.Series(name=name, values=values, dtype=pl.Int64).cast(pl.Duration('ms'))
            if invalids.any():
                col = col.scatter(np.where(invalids)[0], None)

        elif vt_id == sbdf_c.SBDF_TIMETYPEID:
            # _import_vt_time_int64 stores int64 ns since midnight (Polars Time internal format).
            # pl.Series(int64, pl.Time) validates every element, including null positions.
            # SBDF null slots may contain sentinel values (e.g. INT64_MAX) which, after the
            # ×1_000_000 ms→ns scale, exceed the valid Time range [0, 86_400_000_000_000 ns].
            # Zero them out before constructing the Series so validation passes; the invalids
            # array then overwrites those slots with None immediately after.
            values = context.get_values_array()
            context.clear_values_arrays()
            if invalids.any():
                values[invalids] = 0
            col = pl.Series(name=name, values=values, dtype=pl.Time)
            if invalids.any():
                col = col.scatter(np.where(invalids)[0], None)

        elif not context.is_object_numpy_type():
            # Numeric types (bool, int, float): numpy → Polars directly; Polars may zero-copy
            # the buffer.  No early release needed — these arrays are small relative to the data.
            values = context.get_values_array()
            col = pl.Series(name=name, values=values, dtype=_import_polars_dtype(context))
            if invalids.any():
                col = col.scatter(np.where(invalids)[0], None)

        else:
            # String, time, binary, decimal: Polars requires a Python list (no compatible numpy
            # dtype).  Release the concatenated array before building the Arrow buffer to cap
            # peak memory at 2 live copies (list + Arrow) instead of 3.
            values = context.get_values_array()
            values_list = values.tolist()
            context.clear_values_arrays()
            del values
            if invalids.any():
                for idx in np.where(invalids)[0]:
                    values_list[idx] = None
            col = pl.Series(name=name, values=values_list, dtype=_import_polars_dtype(context))

        series_list.append(col)

    return pl.DataFrame(series_list)


def import_data(sbdf_file, output_format=OutputFormat.PANDAS):
    """Import data from an SBDF file and create a DataFrame.

    :param sbdf_file: the filename of the SBDF file to import
    :param output_format: the format of the returned DataFrame; an :class:`OutputFormat` member
    :return: the DataFrame containing the imported data
    :raises SBDFError: if a problem is encountered during import
    """
    # Validate output_format before opening the file so we fail fast on bad input.
    if not isinstance(output_format, OutputFormat):
        raise SBDFError(f"unknown output_format {output_format!r}; expected an OutputFormat enum member")

    cdef int error, i
    cdef stdio.FILE* input_file = NULL
    cdef int major_v, minor_v
    cdef sbdf_c.sbdf_tablemetadata* table_meta = NULL
    cdef importer_fn* importer_fns = NULL
    cdef char* col_name
    cdef sbdf_c.sbdf_valuetype col_type
    cdef sbdf_c.sbdf_tableslice* table_slice
    cdef sbdf_c.sbdf_columnslice* col_slice

    try:
        # Open the SBDF file
        input_file = _pathlike_to_fileptr(sbdf_file, "rb")

        # Read the file header
        error = sbdf_c.sbdf_fh_read(input_file, &major_v, &minor_v)
        if error != sbdf_c.SBDF_OK:
            raise SBDFError(f"error reading '{sbdf_file}': {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

        # Examine the version information
        if major_v != 1 or minor_v != 0:
            raise SBDFError(f"error reading '{sbdf_file}': unsupported file version {major_v}.{minor_v}")

        # Read the table metadata
        error = sbdf_c.sbdf_tm_read(input_file, &table_meta)
        if error != sbdf_c.SBDF_OK:
            raise SBDFError(f"error reading '{sbdf_file}': {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

        # Parse metadata information
        num_columns = table_meta.no_columns

        # Add table metadata
        table_metadata = _import_metadata(table_meta.table_metadata, -1)

        # Determine the importer for each column
        column_names = []
        column_metadata = []
        importer_contexts = []
        importer_fns = <importer_fn*>mem.PyMem_RawMalloc(sizeof(importer_fn) * num_columns)

        for i in range(num_columns):
            sbdf_c.sbdf_cm_get_name(table_meta.column_metadata[i], &col_name)
            sbdf_c.sbdf_cm_get_type(table_meta.column_metadata[i], &col_type)

            column_names.append(col_name.decode('utf-8'))

            if col_type.id == sbdf_c.SBDF_BOOLTYPEID:
                importer_contexts.append(_ImportContext(np_c.NPY_BOOL, col_type))
                importer_fns[i] = _import_vts_numpy
            elif col_type.id == sbdf_c.SBDF_DOUBLETYPEID:
                importer_contexts.append(_ImportContext(np_c.NPY_FLOAT64, col_type))
                importer_fns[i] = _import_vts_numpy
            elif col_type.id == sbdf_c.SBDF_LONGTYPEID:
                importer_contexts.append(_ImportContext(np_c.NPY_INT64, col_type))
                importer_fns[i] = _import_vts_numpy
            elif col_type.id == sbdf_c.SBDF_FLOATTYPEID:
                importer_contexts.append(_ImportContext(np_c.NPY_FLOAT32, col_type))
                importer_fns[i] = _import_vts_numpy
            elif col_type.id == sbdf_c.SBDF_INTTYPEID:
                importer_contexts.append(_ImportContext(np_c.NPY_INT32, col_type))
                importer_fns[i] = _import_vts_numpy
            elif col_type.id == sbdf_c.SBDF_DATETIMETYPEID:
                if output_format == OutputFormat.POLARS:
                    # Store raw int64 ms values; _import_build_polars_dataframe will adjust the
                    # epoch offset and reinterpret as datetime64[ms] without boxing Python objects.
                    importer_contexts.append(_ImportContext(np_c.NPY_INT64, col_type))
                    importer_fns[i] = _import_vts_numpy
                else:
                    importer_contexts.append(_ImportContext(np_c.NPY_OBJECT, col_type))
                    importer_fns[i] = _import_vt_datetime
            elif col_type.id == sbdf_c.SBDF_DATETYPEID:
                if output_format == OutputFormat.POLARS:
                    importer_contexts.append(_ImportContext(np_c.NPY_INT32, col_type))
                    importer_fns[i] = _import_vt_date_int32
                else:
                    importer_contexts.append(_ImportContext(np_c.NPY_OBJECT, col_type))
                    importer_fns[i] = _import_vt_date
            elif col_type.id == sbdf_c.SBDF_TIMESPANTYPEID:
                if output_format == OutputFormat.POLARS:
                    # Timespans are stored as int64 ms with no epoch — reinterpret directly as
                    # timedelta64[ms] in _import_build_polars_dataframe.
                    importer_contexts.append(_ImportContext(np_c.NPY_INT64, col_type))
                    importer_fns[i] = _import_vts_numpy
                else:
                    importer_contexts.append(_ImportContext(np_c.NPY_OBJECT, col_type))
                    importer_fns[i] = _import_vt_timespan
            elif col_type.id == sbdf_c.SBDF_TIMETYPEID:
                if output_format == OutputFormat.POLARS:
                    importer_contexts.append(_ImportContext(np_c.NPY_INT64, col_type))
                    importer_fns[i] = _import_vt_time_int64
                else:
                    importer_contexts.append(_ImportContext(np_c.NPY_OBJECT, col_type))
                    importer_fns[i] = _import_vt_time
            elif col_type.id == sbdf_c.SBDF_STRINGTYPEID:
                importer_contexts.append(_ImportContext(np_c.NPY_OBJECT, col_type))
                importer_fns[i] = _import_vt_string
            elif col_type.id == sbdf_c.SBDF_BINARYTYPEID:
                importer_contexts.append(_ImportContext(np_c.NPY_OBJECT, col_type))
                importer_fns[i] = _import_vt_bytes
            elif col_type.id == sbdf_c.SBDF_DECIMALTYPEID:
                importer_contexts.append(_ImportContext(np_c.NPY_OBJECT, col_type))
                importer_fns[i] = _import_vt_decimal
            else:
                raise SBDFError(f"column '{col_name}' has unsupported type id {col_type.id}")
            sbdf_c.sbdf_str_destroy(col_name)
            col_name = NULL

            # Add column metadata
            column_metadata.append(_import_metadata(table_meta.column_metadata[i], i))

        # Read the table slices
        while not error:
            error = sbdf_c.sbdf_ts_read(input_file, table_meta, NULL, &table_slice)
            if error != sbdf_c.SBDF_OK:
                break

            for i in range(table_slice.no_columns):
                col_slice = table_slice.columns[i]
                error = importer_fns[i](importer_contexts[i], col_slice)
                if error != sbdf_c.SBDF_OK:
                    break

            # Destroy the table slice, including the value arrays
            sbdf_c.sbdf_ts_destroy(table_slice)
            table_slice = NULL

        # Destroy the table metadata, which also destroys the column metadata
        sbdf_c.sbdf_tm_destroy(table_meta)
        table_meta = NULL

        if error != sbdf_c.SBDF_OK and error != sbdf_c.SBDF_TABLEEND:
            raise SBDFError(f"error reading '{sbdf_file}': {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

        # Short-circuit before pd.concat to avoid the Pandas intermediary entirely.
        # This keeps the import zero-copy for large DataFrames: numpy arrays collected
        # by each _ImportContext go straight into Polars Series without ever becoming
        # a Pandas DataFrame.
        if output_format == OutputFormat.POLARS:
            if pl is None:
                raise SBDFError("polars is not installed; install it with 'pip install spotfire[polars]'")
            return _import_build_polars_dataframe(column_names, importer_contexts)

        # Build a new Pandas DataFrame with the results
        imported_columns = []
        for i in range(num_columns):
            values = importer_contexts[i].get_values_array()
            invalid_array = importer_contexts[i].get_invalid_array()
            dtype_name = importer_contexts[i].get_pandas_dtype_name()
            if dtype_name in ("Int32", "Int64"):
                # Build nullable integer array with mask in one shot; avoids a second-pass
                # .loc assignment that triggers Pandas dtype coercion overhead.
                base_dtype = "int32" if dtype_name == "Int32" else "int64"
                column_series = pd.Series(
                    pd.arrays.IntegerArray(values.astype(base_dtype), invalid_array),
                    name=column_names[i])
            else:
                column_series = pd.Series(values, dtype=dtype_name, name=column_names[i])
                column_series.loc[invalid_array] = None
            imported_columns.append(column_series)
        dataframe = pd.concat(imported_columns, axis=1)
        for i in range(num_columns):
            dataframe[column_names[i]].spotfire_column_metadata = column_metadata[i]
            dataframe[column_names[i]].attrs['spotfire_type'] = importer_contexts[i].get_spotfire_type_name()
        if gpd is not None and table_metadata.get('MapChart.IsGeocodingTable'):
            # Turn the DataFrame into a GeoDataFrame if geopandas was detected and the table metadata
            # indicates geocoding is present in the SBDF data
            if 'Geometry' not in dataframe or not isinstance(dataframe['Geometry'][0], bytes):
                raise SBDFError("cannot convert to GeoDataFrame")
            # Convert to GeoDataFrame
            geometry = []
            for x in dataframe['Geometry']:
                geometry.append(shapely.wkb.loads(x))
            dataframe = dataframe.drop(columns='Geometry')
            gdf = gpd.GeoDataFrame(dataframe, geometry=geometry)
            spotfire.copy_metadata(dataframe, gdf)
            # Determine the correct CRS to use
            if 'MapChart.GeographicCrs' in table_metadata.keys() and table_metadata['MapChart.GeographicCrs'] != "":
                proj = table_metadata['MapChart.GeographicCrs'][0]
                gdf.crs = proj
                try:
                    # GeoPandas <= 0.6.3 compatibility
                    if not gdf.crs.startswith("+init="):
                        gdf.crs = f"+init={proj}"
                except AttributeError:
                    pass
            dataframe = gdf
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dataframe.spotfire_table_metadata = table_metadata
        return dataframe

    finally:
        # Close the input file
        if input_file != NULL:
            stdio.fclose(input_file)

        # Free memory for the column importer bookkeeping
        if importer_fns != NULL:
            mem.PyMem_RawFree(importer_fns)


# Polars-specific exporter IDs stored in _ExportContext.polars_exporter_id.
# Using C-level constants avoids Python object lookup in the hot export loop.
cdef int _POL_EXP_DEFAULT = 0
cdef int _POL_EXP_DATETIME = 1
cdef int _POL_EXP_DATE = 2
cdef int _POL_EXP_TIMESPAN = 3
cdef int _POL_EXP_TIME = 4
cdef int _POL_EXP_STRING = 5


# Export data to SBDF from Python.
@cython.auto_pickle(False)
cdef class _ExportContext:
    """Object to store information for each column as it is exported."""
    cdef int valuetype_id
    cdef np_c.ndarray values_array
    cdef np_c.ndarray invalid_array
    cdef bint any_invalid
    cdef int polars_exporter_id  # 0=default; 1=datetime; 2=date; 3=timespan; 4=time; 5=string
    cdef np_c.ndarray _arrow_offsets  # int64 view of Arrow offsets buffer (string fast path)
    cdef np_c.ndarray _arrow_data     # uint8 view of Arrow values buffer (string fast path)

    def __init__(self):
        """Initialize the export context."""
        self.valuetype_id = 0
        self.values_array = None
        self.invalid_array = None
        self.any_invalid = False
        self.polars_exporter_id = 0
        self._arrow_offsets = None
        self._arrow_data = None

    cdef void set_arrays(self, np_c.ndarray values, invalid):
        """Set the NumPy ``ndarray`` with the values to export and a list or NumPy ``ndarray`` of whether each value
        is invalid.

        :param values: full values NumPy array
        :param invalid: full invalids list or NumPy array
        """
        self.values_array = values
        self.invalid_array = np.asarray(invalid, dtype="bool")
        self.any_invalid = any(invalid)

    cdef void set_arrow_string(self, np_c.ndarray offsets, np_c.ndarray data,
                               np_c.ndarray invalid):
        """Set Arrow buffer views for a Polars String/Utf8 column (bypasses values_array).

        :param offsets: int64 numpy view of the Arrow LargeUtf8 offsets buffer (length n+1)
        :param data: uint8 numpy view of the Arrow LargeUtf8 values buffer (concatenated UTF-8 bytes)
        :param invalid: bool numpy array marking null rows
        """
        self._arrow_offsets = offsets
        self._arrow_data = data
        self.invalid_array = invalid
        self.any_invalid = bool(invalid.any())

    def __len__(self):
        if self.values_array is not None:
            return np_c.PyArray_DIM(self.values_array, 0)
        elif self._arrow_offsets is not None:
            return np_c.PyArray_DIM(self._arrow_offsets, 0) - 1
        else:
            return 0

    cdef void set_valuetype_id(self, valuetype_id: int):
        """Set the value type to export this column as.

        :param valuetype_id: the integer value type ID
        """
        self.valuetype_id = valuetype_id

    cpdef int get_valuetype_id(self):
        """Get the value type to export this column as.

        :return: the integer value type ID
        """
        return self.valuetype_id

    cpdef int get_polars_exporter_id(self):
        """Get the Polars-specific exporter ID (0 = use default exporter).

        :return: 0 default; 1 datetime; 2 date; 3 timespan; 4 time
        """
        return self.polars_exporter_id

    def get_numpy_dtype(self):
        """Get the correct NumPy dtype for this column.

        :return: the NumPy dtype name for this column
        """
        if self.valuetype_id == sbdf_c.SBDF_DOUBLETYPEID:
            return "float64"
        elif self.valuetype_id == sbdf_c.SBDF_LONGTYPEID:
            return "int64"
        elif self.valuetype_id == sbdf_c.SBDF_FLOATTYPEID:
            return "float32"
        elif self.valuetype_id == sbdf_c.SBDF_INTTYPEID:
            return "int32"
        elif self.valuetype_id == sbdf_c.SBDF_BOOLTYPEID:
            return "bool"
        else:
            return "object"

    def get_numpy_na_value(self):
        """Get the correct value for representing a NA value in the values array.

        :return: the value for representing an NA value
        """
        if self.valuetype_id == sbdf_c.SBDF_DOUBLETYPEID or self.valuetype_id == sbdf_c.SBDF_FLOATTYPEID:
            return 0.
        elif self.valuetype_id == sbdf_c.SBDF_LONGTYPEID or self.valuetype_id == sbdf_c.SBDF_INTTYPEID:
            return 0
        elif self.valuetype_id == sbdf_c.SBDF_BOOLTYPEID:
            return False
        else:
            return None


# Individual functions for extracting data and metadata for exporting each supported Python type.
cdef _export_obj_dataframe(obj):
    """Extract column information for a Pandas ``DataFrame``.

    :param obj: DataFrame object to export
    :return: tuple containing dictionary of table metadata, list of column names, list of dictionaries of column
              metadata, and list of export context objects
    """
    if len(set(obj.keys().to_list())) != len(obj.columns):
        raise SBDFError("obj does not have unique column names")

    # Table/column metadata and column information
    try:
        table_metadata = obj.spotfire_table_metadata
    except AttributeError:
        table_metadata = {}
    export_column_names = obj.columns.tolist()
    column_names = []
    column_metadata = []
    exporter_contexts = []
    for col in export_column_names:
        if obj[col].dtype == 'geometry':
            # Special case for the 'geometry' dtype from geopandas
            _export_obj_geodataframe_geometry(obj[col], obj.crs, table_metadata, column_names, column_metadata,
                                              exporter_contexts)
        else:
            # Normal columns
            column_names.append(col)
            context = _ExportContext()
            if 'spotfire_type' in obj[col].attrs:
                context.set_valuetype_id(_export_infer_valuetype_from_spotfire_typename(obj[col], f"column '{col}'"))
            else:
                context.set_valuetype_id(_export_infer_valuetype_from_pandas_dtype(obj[col], f"column '{col}'"))
            na_value = context.get_numpy_na_value()
            nas = {None: na_value,
                   np.nan: na_value,
                   pd.NA: na_value,
                   pd.NaT: na_value,
                   }
            if obj[col].dtype == "object":
                values = obj[col].replace(nas).to_numpy()
            else:
                values = obj[col].replace(nas).to_numpy(dtype=context.get_numpy_dtype())
            invalids = pd.isnull(obj[col])
            context.set_arrays(values, invalids)
            exporter_contexts.append(context)
            try:
                column_metadata.append(obj[col].spotfire_column_metadata)
            except AttributeError:
                column_metadata.append({})

    return table_metadata, column_names, column_metadata, exporter_contexts


cdef void _export_obj_geodataframe_geometry(geometry, geometry_crs, table_metadata, column_names, column_metadata,
                                            exporter_contexts):
    """Extract column information and generate additional columns for the geometry of a GeoPandas ``GeoDataFrame``.

    :param geometry:
    :param geometry_crs:
    :param table_metadata: dict containing table metadata
    :param column_names: list of column names
    :param column_metadata: list of dictionaries containing column metadata
    :param exporter_contexts: list of export context objects
    """
    cdef Py_ssize_t geometry_len = len(geometry)
    cdef np_c.npy_intp shape[1]
    shape[0] = <np_c.npy_intp>geometry_len
    cdef np_c.ndarray invalids = np_c.PyArray_ZEROS(1, shape, np_c.NPY_BOOL, 0)
    cdef np_c.ndarray values
    cdef int i

    # Geometry
    column_names.append("Geometry")
    column_metadata.append({"MapChart.ColumnTypeId": ["Geometry"], "ContentType": ["application/x-wkb"]})
    context = _ExportContext()
    context.set_valuetype_id(sbdf_c.SBDF_BINARYTYPEID)
    values = np_c.PyArray_ZEROS(1, shape, np_c.NPY_OBJECT, 0)
    for i in range(geometry_len):
        values[i] = shapely.wkb.dumps(geometry[i])
    context.set_arrays(values, invalids)
    exporter_contexts.append(context)

    # CRS
    if geometry_crs is not None:
        try:
            table_metadata["MapChart.GeographicCrs"] = [geometry_crs.to_string()]
        except AttributeError:
            # GeoPandas <= 0.6.3
            if geometry_crs.startsWith("+init="):
                table_metadata["MapChart.GeographicCrs"] = [geometry_crs[6:]]
            else:
                table_metadata["MapChart.GeographicCrs"] = [geometry_crs]


cdef _export_obj_series(obj, default_column_name):
    """Extract column information for a Pandas ``Series``.

    :param obj: Series object to export
    :param default_column_name: column name to use when obj does not have a name
    :return: tuple containing dict of table metadata, list of column names, list of dicts of column metadata, and
              list of export context objects
    """
    if obj.name is None:
        column_name = default_column_name
        description = "series"
    else:
        column_name = obj.name
        description = f"series '{obj.name}'"

    # Column metadata and information
    context = _ExportContext()
    if 'spotfire_type' in obj.attrs:
        context.set_valuetype_id(_export_infer_valuetype_from_spotfire_typename(obj, description))
    else:
        context.set_valuetype_id(_export_infer_valuetype_from_pandas_dtype(obj, description))
    context.set_arrays(obj.to_numpy(context.get_numpy_dtype(), na_value=context.get_numpy_na_value()),
                       _export_infer_invalids(obj))
    try:
        column_metadata = obj.spotfire_column_metadata
    except AttributeError:
        column_metadata = {}

    return {}, [column_name], [column_metadata], [context]


cdef int _export_infer_valuetype_from_polars_dtype(dtype, series_description):
    """Determine a value type for a data set based on the Polars dtype for the series.

    :param dtype: the Polars dtype object
    :param series_description: description of series (for error reporting)
    :return: the integer value type id representing the type of series
    :raise SBDFError: if the dtype is unknown
    """
    # Use __class__.__name__ rather than isinstance() checks.  Polars dtype objects are
    # not ordinary Python classes resolvable at Cython compile time, so isinstance() would
    # require importing the exact dtype class — which breaks when Polars isn't installed.
    # Class name strings are stable across the Polars versions we support (>= 0.20).
    dtype_name = dtype.__class__.__name__
    if dtype_name == "Boolean":
        return sbdf_c.SBDF_BOOLTYPEID
    elif dtype_name in ("Int8", "Int16", "Int32", "UInt8", "UInt16"):
        return sbdf_c.SBDF_INTTYPEID
    elif dtype_name in ("Int64", "UInt32", "UInt64"):
        if dtype_name == "UInt64":
            warnings.warn(f"Polars UInt64 type in {series_description} will be exported as LongInteger (signed "
                          f"64-bit); values above 9,223,372,036,854,775,807 will overflow", SBDFWarning)
        return sbdf_c.SBDF_LONGTYPEID
    elif dtype_name == "Float32":
        return sbdf_c.SBDF_FLOATTYPEID
    elif dtype_name == "Float64":
        return sbdf_c.SBDF_DOUBLETYPEID
    elif dtype_name in ("Utf8", "String"):
        return sbdf_c.SBDF_STRINGTYPEID
    elif dtype_name == "Date":
        return sbdf_c.SBDF_DATETYPEID
    elif dtype_name == "Datetime":
        if getattr(dtype, 'time_zone', None) is not None:
            warnings.warn(f"Polars Datetime type in {series_description} has timezone '{dtype.time_zone}'; "
                          f"timezone information will not be preserved in SBDF", SBDFWarning)
        return sbdf_c.SBDF_DATETIMETYPEID
    elif dtype_name == "Duration":
        return sbdf_c.SBDF_TIMESPANTYPEID
    elif dtype_name == "Time":
        return sbdf_c.SBDF_TIMETYPEID
    elif dtype_name == "Binary":
        return sbdf_c.SBDF_BINARYTYPEID
    elif dtype_name == "Decimal":
        warnings.warn(f"Polars Decimal type in {series_description} export is experimental; "
                      f"precision may not be fully preserved", SBDFWarning)
        return sbdf_c.SBDF_DECIMALTYPEID
    elif dtype_name in ("Categorical", "Enum"):
        # SBDF has no categorical type; export as String
        warnings.warn(f"Polars {dtype_name} type in {series_description} will be exported as String; "
                      f"category information will not be preserved", SBDFWarning)
        return sbdf_c.SBDF_STRINGTYPEID
    elif dtype_name == "Null":
        # pl.Series([None, None]) has dtype Null when no type can be inferred.  Export as
        # String; _export_polars_series_to_numpy produces a placeholder array and the
        # invalids mask marks every row missing, so the stored values are never read.
        return sbdf_c.SBDF_STRINGTYPEID
    else:
        raise SBDFError(f"unknown Polars dtype '{dtype_name}' in {series_description}")


cdef np_c.ndarray _export_polars_series_to_numpy(_ExportContext context, series,
                                                 np_c.ndarray invalids):
    """Convert a non-temporal Polars Series to a NumPy array for the SBDF exporter.

    Temporal types (Datetime, Date, Duration, Time) are handled by
    ``_export_polars_setup_arrays`` before this function is reached.

    :param context: export context holding the resolved value type
    :param series: Polars Series to convert (non-temporal)
    :param invalids: boolean NumPy array marking which rows are null/NaN
    :return: NumPy ndarray of values
    """
    dtype_name = series.dtype.__class__.__name__
    if dtype_name == "Null":
        # A Null-dtype series has no values to convert; return a same-length placeholder array.
        # The invalids mask (set by the caller via series.is_null()) marks every row as missing,
        # so the placeholder values are never read by the SBDF writer.
        return np.full(len(series), None, dtype=object)
    if dtype_name in ("Categorical", "Enum"):
        # Cast to String so .to_numpy() returns plain Python strings
        series = series.cast(pl.Utf8)
        dtype_name = "Utf8"
    na_value = context.get_numpy_na_value()
    if na_value is not None:
        # Numeric / boolean column.  Skip fill_null when the series is null-free:
        # to_numpy(allow_copy=False) returns a zero-copy view of the Arrow buffer.
        # Fall back to fill_null+copy when nulls are present (Arrow's validity bitmap
        # cannot be expressed inline in a numpy array for integer/boolean dtypes).
        if invalids.any():
            return np.asarray(series.fill_null(na_value).to_numpy(allow_copy=True),
                              dtype=context.get_numpy_dtype())
        else:
            try:
                return np.asarray(series.to_numpy(allow_copy=False),
                                  dtype=context.get_numpy_dtype())
            except (pl.exceptions.InvalidOperationError, RuntimeError):
                # Polars raises InvalidOperationError (older versions) or RuntimeError (1.x+) when
                # allow_copy=False cannot be honoured (e.g., series contains nulls).  Both are caught
                # so the fallback copy path works across Polars versions.
                return np.asarray(series.to_numpy(allow_copy=True),
                                  dtype=context.get_numpy_dtype())
    else:
        return np.asarray(series.to_numpy(allow_copy=True), dtype=object)


cdef _export_obj_polars_dataframe(obj):
    """Extract column information for a Polars ``DataFrame``.

    :param obj: Polars DataFrame object to export
    :return: tuple containing dictionary of table metadata, list of column names, list of dictionaries of column
              metadata, and list of export context objects
    """
    warnings.warn(
        "Polars DataFrames do not support Spotfire metadata; the exported SBDF will not contain "
        "table or column metadata. See https://github.com/pola-rs/polars/issues/5117",
        SBDFWarning
    )
    if len(set(obj.columns)) != len(obj.columns):
        raise SBDFError("obj does not have unique column names")

    column_names = []
    column_metadata = []
    exporter_contexts = []
    for col in obj.columns:
        series = obj[col]
        column_names.append(col)
        context = _ExportContext()
        context.set_valuetype_id(_export_infer_valuetype_from_polars_dtype(series.dtype, f"column '{col}'"))
        _export_polars_setup_arrays(context, series)
        column_metadata.append({})
        exporter_contexts.append(context)

    return {}, column_names, column_metadata, exporter_contexts


cdef _export_obj_polars_series(obj, default_column_name):
    """Extract column information for a Polars ``Series``.

    :param obj: Polars Series object to export
    :param default_column_name: column name to use when obj does not have a name
    :return: tuple containing dict of table metadata, list of column names, list of dicts of column metadata, and
              list of export context objects
    """
    warnings.warn(
        "Polars DataFrames do not support Spotfire metadata; the exported SBDF will not contain "
        "table or column metadata. See https://github.com/pola-rs/polars/issues/5117",
        SBDFWarning
    )
    column_name = obj.name if obj.name else default_column_name
    description = f"series '{obj.name}'" if obj.name else "series"

    context = _ExportContext()
    context.set_valuetype_id(_export_infer_valuetype_from_polars_dtype(obj.dtype, description))
    _export_polars_setup_arrays(context, obj)

    return {}, [column_name], [{}], [context]


cdef _export_obj_numpy(np_c.ndarray obj, default_column_name):
    """Extract column information for a NumPy ``ndarray``.

    :param obj: ndarray object to export
    :param default_column_name: column name to use
    :return: tuple containing dict of table metadata, list of column names, list of dicts of column metadata, and
              list of export context objects
    """
    context = _ExportContext()
    context.set_valuetype_id(_export_infer_valuetype_from_type(obj, "array"))
    context.set_arrays(obj, _export_infer_invalids(obj))

    return {}, [default_column_name], [{}], [context]


cdef _export_obj_dict_of_lists(dict obj):
    """Extract column information for a Python ``dict[str, list]``.

    :param obj: dict object mapping strings to lists to export
    :return: tuple containing dict of table metadata, list of column names, list of dicts of column metadata, and
              list of export context objects
    """
    cdef int i
    cdef np_c.ndarray values

    for item in obj.values():
        if not isinstance(item, list):
            raise SBDFError("obj is not a dict of lists")

    # Column metadata and information
    column_names = list(obj.keys())
    column_metadata = []
    exporter_contexts = []
    for col in column_names:
        context = _ExportContext()
        context.set_valuetype_id(_export_infer_valuetype_from_type(obj[col], f"column '{col}'"))
        shape = len(obj[col])
        values = np.empty(shape, dtype=context.get_numpy_dtype())
        for i in range(shape):
            if pd.isnull(obj[col][i]):
                values[i] = context.get_numpy_na_value()
            else:
                values[i] = obj[col][i]
        context.set_arrays(values, _export_infer_invalids(obj[col]))
        exporter_contexts.append(context)
        column_metadata.append({})

    return {}, column_names, column_metadata, exporter_contexts


cdef _export_obj_scalar(obj, default_column_name):
    """Extract column information for a Python scalar value.

    :param obj: scalar value to export
    :param default_column_name: column name to use
    :return: tuple containing dict of table metadata, list of column names, list of dicts of column metadata, and
              list of export context objects"""
    cdef np_c.ndarray values

    context = _ExportContext()
    context.set_valuetype_id(_export_infer_valuetype_from_type([obj], "value"))
    values = np.array([obj], dtype=context.get_numpy_dtype())
    context.set_arrays(values, [False])

    return {}, [default_column_name], [{}], [context]


cdef _export_obj_iterable(obj, default_column_name):
    """Extract column information for a Python iterable object.

    :param obj: iterable object to export
    :param default_column_name: column name to use
    :return: tuple containing dict of table metadata, list of column names, list of dicts of column metadata, and
              list of export context objects

    .. seealso: https://docs.python.org/3/glossary.html#term-iterable
    """
    context = _ExportContext()
    context.set_valuetype_id(_export_infer_valuetype_from_type(obj, "list"))
    values_list = []
    invalids_list = []
    for x in obj:
        if pd.isnull(x):
            values_list.append(context.get_numpy_na_value())
            invalids_list.append(True)
        else:
            values_list.append(x)
            invalids_list.append(False)
    context.set_arrays(np.array(values_list, dtype=context.get_numpy_dtype()),
                       np.array(invalids_list, dtype="bool"))

    return {}, [default_column_name], [{}], [context]


cdef _export_obj_matplotlib_figure(obj, default_column_name):
    """Extract column information for a Matplotlib ``figure``.

    :param obj: figure object to export
    :param default_column_name: column name to use
    :return: tuple containing dict of table metadata, list of column names, list of dicts of column metadata, and
              list of export context objects
    """
    cdef np_c.ndarray values

    context = _ExportContext()
    context.set_valuetype_id(sbdf_c.SBDF_BINARYTYPEID)
    with io.BytesIO() as buf:
        obj.set_canvas(matplotlib.pyplot.gcf().canvas)
        obj.savefig(buf, format="png")
        values = np.array([buf.getvalue()], dtype='object')
        context.set_arrays(values, [False])

    return {}, [default_column_name], [{}], [context]


cdef _export_obj_seaborn_grid(obj, default_column_name):
    """Extract column information for a Seaborn ``Grid``.

    :param obj: grid object to export
    :param default_column_name: column name to use
    :return: tuple containing dict of table metadata, list of column names, list of dicts of column metadata, and
              list of export context objects
    """
    cdef np_c.ndarray values

    context = _ExportContext()
    context.set_valuetype_id(sbdf_c.SBDF_BINARYTYPEID)
    with io.BytesIO() as buf:
        obj.savefig(buf)
        values = np.array([buf.getvalue()], dtype='object')
        context.set_arrays(values, [False])

    return {}, [default_column_name], [{}], [context]


cdef _export_obj_pil_image(obj, default_column_name):
    """Extract column information for a PIL ``Image``.

    :param obj: image object to export
    :param default_column_name: column name to use
    :return: tuple containing dict of table metadata, list of column names, list of dicts of column metadata, and
              list of export context objects
    """
    cdef np_c.ndarray values

    context = _ExportContext()
    context.set_valuetype_id(sbdf_c.SBDF_BINARYTYPEID)
    with io.BytesIO() as buf:
        obj.save(buf, format="png")
        values = np.array([buf.getvalue()], dtype='object')
        context.set_arrays(values, [False])

    return {}, [default_column_name], [{}], [context]


cdef np_c.ndarray _export_infer_invalids(values):
    """Infer invalid array information from values.

    :param values: values to infer invalids from
    :return: invalids NumPy array
    """
    cdef int i
    cdef np_c.npy_intp shape[1]
    shape[0] = <np_c.npy_intp>len(values)
    cdef np_c.ndarray invalids = np_c.PyArray_ZEROS(1, shape, np_c.NPY_BOOL, 0)
    for i in range(shape[0]):
        if pd.isnull(values[i]):
            invalids[i] = True
    return invalids


# Individual functions for exporting each Spotfire value type.
ctypedef int(*exporter_fn)(_ExportContext, Py_ssize_t, Py_ssize_t, sbdf_c.sbdf_object**)


cdef exporter_fn _export_get_exporter(int valuetype_id):
    """Get the right exporter function for a value type.

    :param valuetype_id: the integer value type id
    :return: the exporter function
    """
    if valuetype_id == sbdf_c.SBDF_BOOLTYPEID:
        return _export_vt_bool
    elif valuetype_id == sbdf_c.SBDF_INTTYPEID:
        return _export_vt_int
    elif valuetype_id == sbdf_c.SBDF_LONGTYPEID:
        return _export_vt_long
    elif valuetype_id == sbdf_c.SBDF_FLOATTYPEID:
        return _export_vt_float
    elif valuetype_id == sbdf_c.SBDF_DOUBLETYPEID:
        return _export_vt_double
    elif valuetype_id == sbdf_c.SBDF_DATETIMETYPEID:
        return _export_vt_datetime
    elif valuetype_id == sbdf_c.SBDF_DATETYPEID:
        return _export_vt_date
    elif valuetype_id == sbdf_c.SBDF_TIMETYPEID:
        return _export_vt_time
    elif valuetype_id == sbdf_c.SBDF_TIMESPANTYPEID:
        return _export_vt_timespan
    elif valuetype_id == sbdf_c.SBDF_STRINGTYPEID:
        return _export_vt_string
    elif valuetype_id == sbdf_c.SBDF_BINARYTYPEID:
        return _export_vt_binary
    elif valuetype_id == sbdf_c.SBDF_DECIMALTYPEID:
        return _export_vt_decimal


cdef np_c.ndarray _polars_temporal_to_numpy(series):
    """Return a raw-integer NumPy array from a Polars integer Series, zero-copy when possible.

    ``series`` must already be cast to the target integer type (Int32 or Int64).
    Zero-copy succeeds for null-free series; falls back to a fill-zero copy when nulls
    are present (Polars cannot expose the Arrow validity bitmap inline in a numpy view
    for integer types).  The zeroed values at null positions are never read by Spotfire
    because the SBDF invalids array marks those rows as missing.
    """
    try:
        return series.to_numpy(allow_copy=False)
    except (pl.exceptions.InvalidOperationError, RuntimeError):
        # Polars raises InvalidOperationError (older versions) or RuntimeError (1.x+) when
        # allow_copy=False cannot be honoured (e.g., series contains nulls).  Both are caught
        # so the fallback copy path works across Polars versions.
        return series.to_numpy(allow_copy=True)


cdef void _export_polars_setup_arrays(_ExportContext context, series):
    """Populate context arrays and polars_exporter_id for a Polars Series.

    For temporal types, extracts raw integer buffers (zero-copy when the series has no
    nulls) and selects a dedicated C-level exporter that performs the epoch / unit
    conversion without boxing Python objects.  For all other types, delegates to
    ``_export_polars_series_to_numpy``.
    """
    dtype_name = series.dtype.__class__.__name__
    if dtype_name in ("Float32", "Float64"):
        invalids = (series.is_null() | series.is_nan()).to_numpy()
    else:
        invalids = series.is_null().to_numpy()

    if dtype_name == "Datetime":
        # Normalise to ms precision for SBDF; cast Datetime('ms')→Int64 is zero-copy.
        if getattr(series.dtype, 'time_unit', 'ms') != 'ms':
            raw = series.cast(pl.Datetime('ms')).cast(pl.Int64)
        else:
            raw = series.cast(pl.Int64)
        # fill_null(0) ensures to_numpy() returns int64 (not float64 with nan) when nulls
        # are present.  The invalids mask already records which positions are null, so the
        # sentinel value of 0 at those slots is never read by the SBDF writer.
        context.set_arrays(_polars_temporal_to_numpy(raw.fill_null(0)), invalids)
        context.polars_exporter_id = _POL_EXP_DATETIME
    elif dtype_name == "Duration":
        if getattr(series.dtype, 'time_unit', 'ms') != 'ms':
            raw = series.cast(pl.Duration('ms')).cast(pl.Int64)
        else:
            raw = series.cast(pl.Int64)
        context.set_arrays(_polars_temporal_to_numpy(raw.fill_null(0)), invalids)
        context.polars_exporter_id = _POL_EXP_TIMESPAN
    elif dtype_name == "Date":
        # Date is always int32 days since Unix epoch in Arrow.
        context.set_arrays(_polars_temporal_to_numpy(series.cast(pl.Int32).fill_null(0)), invalids)
        context.polars_exporter_id = _POL_EXP_DATE
    elif dtype_name == "Time":
        # Time is always int64 ns since midnight in Arrow.
        context.set_arrays(_polars_temporal_to_numpy(series.cast(pl.Int64).fill_null(0)), invalids)
        context.polars_exporter_id = _POL_EXP_TIME
    elif dtype_name in ("Utf8", "String", "Categorical", "Enum"):
        # Arrow fast path: read raw UTF-8 bytes directly from the Arrow LargeUtf8 buffers,
        # bypassing Python str object creation and re-encoding in the C helper.
        # Requires pyarrow; falls back to the to_numpy() path when it is not installed.
        if dtype_name in ("Categorical", "Enum"):
            series = series.cast(pl.Utf8)
        try:
            arrow_arr = series.to_arrow()
            # Older Polars versions may return a ChunkedArray; combine into a single array.
            if hasattr(arrow_arr, 'combine_chunks'):
                arrow_arr = arrow_arr.combine_chunks()
            if str(arrow_arr.type) not in ("large_string", "large_utf8"):
                raise SBDFError(f"expected Arrow large_string type for Polars String column, "
                                f"got '{arrow_arr.type}'")
            bufs = arrow_arr.buffers()
            # bufs[0] = validity bitmap (unused; we use the Polars invalids mask instead)
            # bufs[1] = int64 offsets (n+1 values); bufs[2] = concatenated UTF-8 bytes
            offsets_np = np.frombuffer(bufs[1], dtype=np.int64)
            data_raw = bufs[2]
            if data_raw is not None and len(data_raw) > 0:
                data_np = np.frombuffer(data_raw, dtype=np.uint8)
            else:
                data_np = np.empty(0, dtype=np.uint8)
            context.set_arrow_string(offsets_np, data_np, np.asarray(invalids, dtype=bool))
            context.polars_exporter_id = _POL_EXP_STRING
        except ImportError:
            context.set_arrays(_export_polars_series_to_numpy(context, series, invalids), invalids)
    else:
        context.set_arrays(_export_polars_series_to_numpy(context, series, invalids), invalids)


cdef int _export_vt_polars_datetime(_ExportContext context, Py_ssize_t start, Py_ssize_t count,
                                    sbdf_c.sbdf_object** obj):
    """Export a Polars Datetime column.

    ``values_array`` holds int64 ms since the Unix epoch.  Adds the fixed SBDF-to-Unix
    offset in a tight C loop across all positions; null positions are zeroed in the
    input by Polars and are ignored by Spotfire via the SBDF invalids array.
    """
    cdef np_c.npy_intp shape[1]
    shape[0] = <np_c.npy_intp>count
    cdef np_c.ndarray out = np_c.PyArray_ZEROS(1, shape, np_c.NPY_INT64, 0)
    cdef long long* src = <long long*>np_c.PyArray_DATA(context.values_array)
    cdef long long* dst = <long long*>np_c.PyArray_DATA(out)
    cdef Py_ssize_t i
    for i in range(count):
        dst[i] = src[start + i] + _SBDF_TO_UNIX_EPOCH_MS
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_datetime(), <int>count, np_c.PyArray_DATA(out), NULL, obj)


cdef int _export_vt_polars_date(_ExportContext context, Py_ssize_t start, Py_ssize_t count,
                                sbdf_c.sbdf_object** obj):
    """Export a Polars Date column.

    ``values_array`` holds int32 days since the Unix epoch.  Converts each value to
    int64 ms since the SBDF epoch in a tight C loop.
    """
    cdef np_c.npy_intp shape[1]
    shape[0] = <np_c.npy_intp>count
    cdef np_c.ndarray out = np_c.PyArray_ZEROS(1, shape, np_c.NPY_INT64, 0)
    cdef int* src = <int*>np_c.PyArray_DATA(context.values_array)
    cdef long long* dst = <long long*>np_c.PyArray_DATA(out)
    cdef Py_ssize_t i
    for i in range(count):
        dst[i] = (<long long>src[start + i]) * 86400000 + _SBDF_TO_UNIX_EPOCH_MS
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_date(), <int>count, np_c.PyArray_DATA(out), NULL, obj)


cdef int _export_vt_polars_timespan(_ExportContext context, Py_ssize_t start, Py_ssize_t count,
                                    sbdf_c.sbdf_object** obj):
    """Export a Polars Duration column.

    ``values_array`` holds int64 ms.  SBDF TimeSpan is also int64 ms with no epoch
    bias, so the Arrow buffer can be sliced and passed directly to the C writer without
    any per-element loop.
    """
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_timespan(), <int>count,
                                      _export_get_offset_ptr(context.values_array, start, count),
                                      NULL, obj)


cdef int _export_vt_polars_time(_ExportContext context, Py_ssize_t start, Py_ssize_t count,
                                sbdf_c.sbdf_object** obj):
    """Export a Polars Time column.

    ``values_array`` holds int64 ns since midnight (Polars / Arrow internal format).
    Converts to int64 ms for SBDF in a tight C loop.
    """
    cdef np_c.npy_intp shape[1]
    shape[0] = <np_c.npy_intp>count
    cdef np_c.ndarray out = np_c.PyArray_ZEROS(1, shape, np_c.NPY_INT64, 0)
    cdef long long* src = <long long*>np_c.PyArray_DATA(context.values_array)
    cdef long long* dst = <long long*>np_c.PyArray_DATA(out)
    cdef Py_ssize_t i
    for i in range(count):
        dst[i] = src[start + i] // 1000000
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_time(), <int>count, np_c.PyArray_DATA(out), NULL, obj)


cdef int _export_vt_polars_string(_ExportContext context, Py_ssize_t start, Py_ssize_t count,
                                  sbdf_c.sbdf_object** obj):
    """Export a Polars String/Utf8 column directly from Arrow LargeUtf8 buffers.

    Reads raw UTF-8 bytes from the Arrow values buffer using the Arrow int64
    offsets buffer, bypassing Python str object creation and re-encoding.
    The Polars Arrow type must be large_string (int64 offsets); an AssertionError
    is raised at setup time (in _export_polars_setup_arrays) if it is not.
    """
    obj[0] = _export_extract_string_obj_arrow(
        <const char *>np_c.PyArray_DATA(context._arrow_data),
        <const long long *>np_c.PyArray_DATA(context._arrow_offsets),
        <const unsigned char *>np_c.PyArray_DATA(context.invalid_array),
        start, count
    )
    return sbdf_c.SBDF_OK


cdef int _export_vt_bool(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of boolean values."""
    cdef np_c.ndarray values
    dtype = context.values_array.dtype
    if dtype == "bool":
        values = context.values_array
    else:
        values = context.values_array.astype("bool")
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_bool(), <int>count, _export_get_offset_ptr(values, start, count),
                                      NULL, obj)


cdef int _export_vt_int(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of integer values."""
    cdef np_c.ndarray values
    dtype = context.values_array.dtype
    if not np.can_cast(dtype, "int32") and dtype != "int64":
        raise SBDFError(f"cannot convert '{context.values_array[0]}' to Spotfire Integer type; incompatible types")
    if dtype == "int32":
        values = context.values_array
    else:
        values = context.values_array.astype("int32")
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_int(), <int>count, _export_get_offset_ptr(values, start, count),
                                      NULL, obj)


cdef int _export_vt_long(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of long integer values."""
    cdef np_c.ndarray values
    dtype = context.values_array.dtype
    if not np.can_cast(dtype, "int64"):
        raise SBDFError(f"cannot convert '{context.values_array[0]}' to Spotfire LongInteger type; incompatible types")
    if dtype == "int64":
        values = context.values_array
    else:
        values = context.values_array.astype("int64")
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_long(), <int>count, _export_get_offset_ptr(values, start, count),
                                      NULL, obj)


cdef int _export_vt_float(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of float values."""
    cdef np_c.ndarray values
    dtype = context.values_array.dtype
    if not np.can_cast(dtype, "float32") and dtype != "float64":
        raise SBDFError(f"cannot convert '{context.values_array[0]}' to Spotfire SingleReal type; incompatible types")
    if dtype == "float32":
        values = context.values_array
    else:
        values = context.values_array.astype("float32")
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_float(), <int>count, _export_get_offset_ptr(values, start, count),
                                      NULL, obj)


cdef int _export_vt_double(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of double values."""
    cdef np_c.ndarray values
    dtype = context.values_array.dtype
    if not np.can_cast(dtype, "float64"):
        raise SBDFError(f"cannot convert '{context.values_array[0]}' to Spotfire Real type; incompatible types")
    if dtype == "float64":
        values = context.values_array
    else:
        values = context.values_array.astype("float64")
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_double(), <int>count, _export_get_offset_ptr(values, start, count),
                                      NULL, obj)


cdef int _export_vt_datetime(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of datetime values."""
    cdef np_c.npy_intp shape[1]
    shape[0] = <np_c.npy_intp>count
    cdef np_c.ndarray new_values = np_c.PyArray_ZEROS(1, shape, np_c.NPY_INT64, 0)
    cdef int i
    current_tz = datetime.datetime.now().astimezone().tzinfo
    for i in range(count):
        if not context.invalid_array[start + i]:
            val_i = context.values_array[start + i]
            if isinstance(val_i, pd.Timestamp):
                if val_i.tz:
                    dt = val_i.tz_convert(current_tz).tz_localize(None).to_pydatetime()
                else:
                    dt = val_i.to_pydatetime()
            elif isinstance(val_i, np.datetime64):
                dt = np.datetime64(val_i, "ms").astype(datetime.datetime)
            elif isinstance(val_i, datetime.datetime):
                dt = val_i
            else:
                raise SBDFError(f"cannot convert '{val_i}' to Spotfire DateTime type; incompatible types")
            new_values[i] = int((dt - _DATETIME_EPOCH) / _TIMEDELTA_ONE_MSEC)
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_datetime(), <int>count, np_c.PyArray_DATA(new_values), NULL, obj)


cdef int _export_vt_date(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of date values."""
    cdef np_c.npy_intp shape[1]
    shape[0] = <np_c.npy_intp> count
    cdef np_c.ndarray new_values = np_c.PyArray_ZEROS(1, shape, np_c.NPY_INT64, 0)
    cdef int i
    for i in range(count):
        if not context.invalid_array[start + i]:
            val_i = context.values_array[start + i]
            if isinstance(val_i, pd.Timestamp):
                val = val_i.date()
            elif isinstance(val_i, datetime.date):
                val = val_i
            else:
                raise SBDFError(f"cannot convert '{val_i}' to Spotfire Date type; incompatible types")
            new_values[i] = int((val - _DATETIME_EPOCH.date()) / _TIMEDELTA_ONE_MSEC)
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_date(), <int>count, np_c.PyArray_DATA(new_values), NULL, obj)


cdef int _export_vt_time(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of time values."""
    cdef np_c.npy_intp shape[1]
    shape[0] = <np_c.npy_intp> count
    cdef np_c.ndarray new_values = np_c.PyArray_ZEROS(1, shape, np_c.NPY_INT64, 0)
    cdef int i
    for i in range(count):
        if not context.invalid_array[start + i]:
            val_i = context.values_array[start + i]
            if isinstance(val_i, datetime.time):
                val = datetime.datetime.combine(datetime.datetime.min, val_i) - datetime.datetime.min
            else:
                raise SBDFError(f"cannot convert '{val_i}' to Spotfire Time type; incompatible types")
            new_values[i] = val // _TIMEDELTA_ONE_MSEC
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_time(), <int>count, np_c.PyArray_DATA(new_values), NULL, obj)


cdef int _export_vt_timespan(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of timespan values."""
    cdef np_c.npy_intp shape[1]
    shape[0] = <np_c.npy_intp>count
    cdef np_c.ndarray new_values = np_c.PyArray_ZEROS(1, shape, np_c.NPY_INT64, 0)
    cdef int i
    for i in range(count):
        if not context.invalid_array[start + i]:
            val_i = context.values_array[start + i]
            if isinstance(val_i, pd.Timedelta):
                td = val_i.to_pytimedelta()
            elif isinstance(val_i, np.timedelta64):
                td = np.timedelta64(val_i, "ms").astype(datetime.timedelta)
            elif isinstance(val_i, datetime.timedelta):
                td = val_i
            else:
                raise SBDFError(f"cannot convert '{val_i}' to Spotfire TimeSpan type; incompatible types")
            new_values[i] = int(td / _TIMEDELTA_ONE_MSEC)
    return sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_timespan(), <int>count, np_c.PyArray_DATA(new_values), NULL, obj)


cdef int _export_vt_string(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of string values."""
    obj[0] = _export_extract_string_obj(context.values_array, context.invalid_array, start, count)
    return sbdf_c.SBDF_OK


cdef int _export_vt_binary(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of binary values."""
    obj[0] = _export_extract_binary_obj(context.values_array, context.invalid_array, start, count)
    return sbdf_c.SBDF_OK


cdef int _export_vt_decimal(_ExportContext context, Py_ssize_t start, Py_ssize_t count, sbdf_c.sbdf_object** obj):
    """Export a slice of data consisting of decimal values."""
    cdef unsigned char* buf = <unsigned char*>mem.PyMem_RawMalloc(count * sizeof(_SbdfDecimal))
    cdef int i
    cdef _SbdfDecimal dec
    try:
        string.memset(buf, 0, count * sizeof(_SbdfDecimal))
        for i in range(count):
            if not context.invalid_array[start + i]:
                val_i = context.values_array[start + i]
                dec = _decimal_to_bytes(val_i)
                string.memcpy(&buf[i * sizeof(_SbdfDecimal)], &dec, sizeof(_SbdfDecimal))
        error = sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_decimal(), <int>count, buf, NULL, obj)
        return error
    except TypeError:
        raise SBDFError(f"cannot convert '{val_i}' to Spotfire Currency type; incompatible types")
    finally:
        mem.PyMem_RawFree(buf)


cdef bint _export_infer_int_promotion(values, values_description):
    """Determine if values can be promoted from Integer type to LongInteger.

    :param values: the values to check for promotion
    :param values_description: description of values (for error reporting)
    :return: whether the values can be promoted
    """
    for i in values:
        if isinstance(i, int) and not limits.INT_MIN < i < limits.INT_MAX:
            warnings.warn(f"values in {values_description} do not fit in type 'Integer'; "
                          "promoting type to 'LongInteger'", SBDFWarning)
            return True
    return False


cdef int _export_infer_valuetype_from_type(values, values_description):
    """Determine a value type for a data set based on the Python type of the objects in the values list.

    :param values: the values to infer the value type of
    :param values_description: description of values (for error reporting)
    :return: the integer value type id representing the type of values
    :raise SBDFError: if the types of values are mixed, all missing, or unknown
    """
    # Remove any None (or other none-ish things) from values
    if isinstance(values, pd.Series):
        vals = values.dropna().tolist()
    else:
        vals = []
        for x in values:
            if not pd.isnull(x):
                vals.append(x)

    # Check if any values remain
    if not vals:
        raise SBDFError(f"cannot determine type for {values_description}; all values are missing")

    # Check to make sure only one type remains
    vals_type = type(vals[0])
    for val in vals:
        if not isinstance(val, vals_type):
            raise SBDFError(f"types in {values_description} do not match")

    # Determine the right type id
    if vals_type is bool:
        return sbdf_c.SBDF_BOOLTYPEID
    elif vals_type is np.int32:
        return sbdf_c.SBDF_INTTYPEID
    elif vals_type is int:
        return sbdf_c.SBDF_LONGTYPEID
    elif vals_type is np.int64:
        return sbdf_c.SBDF_LONGTYPEID
    elif vals_type is np.float32:
        return sbdf_c.SBDF_FLOATTYPEID
    elif vals_type is float:
        return sbdf_c.SBDF_DOUBLETYPEID
    elif vals_type is np.float64:
        return sbdf_c.SBDF_DOUBLETYPEID
    elif vals_type is datetime.datetime:
        return sbdf_c.SBDF_DATETIMETYPEID
    elif vals_type is pd.Timestamp:
        return sbdf_c.SBDF_DATETIMETYPEID
    elif vals_type is datetime.date:
        return sbdf_c.SBDF_DATETYPEID
    elif vals_type is datetime.time:
        return sbdf_c.SBDF_TIMETYPEID
    elif vals_type is datetime.timedelta:
        return sbdf_c.SBDF_TIMESPANTYPEID
    elif vals_type is pd.Timedelta:
        return sbdf_c.SBDF_TIMESPANTYPEID
    elif vals_type is str:
        return sbdf_c.SBDF_STRINGTYPEID
    elif vals_type is bytes:
        return sbdf_c.SBDF_BINARYTYPEID
    elif vals_type is decimal.Decimal:
        return sbdf_c.SBDF_DECIMALTYPEID
    else:
        raise SBDFError(f"unknown type '{_utils.type_name(vals_type)}' in {values_description}")


cdef int _export_infer_valuetype_from_pandas_dtype(series, series_description):
    """Determine a value type for a data set based on the Pandas dtype for the series.

    :param series: the values to infer the value type of
    :param series_description: description of series (for error reporting)
    :return: the integer value type id representing the type of series
    :raise SBDFError: if the types of values are mixed, all missing, or unknown
    """
    dtype = series.dtype.name
    if dtype == "object":
        return _export_infer_valuetype_from_type(series, series_description)
    elif dtype == "category":
        return _export_infer_valuetype_from_pandas_dtype(series.astype(series.cat.categories.dtype), series_description)
    elif dtype == "bool":
        return sbdf_c.SBDF_BOOLTYPEID
    elif dtype == "boolean":
        return sbdf_c.SBDF_BOOLTYPEID
    elif dtype == "int32":
        return sbdf_c.SBDF_INTTYPEID
    elif dtype == "Int32":
        return sbdf_c.SBDF_INTTYPEID
    elif dtype == "int64":
        return sbdf_c.SBDF_LONGTYPEID
    elif dtype == "Int64":
        return sbdf_c.SBDF_LONGTYPEID
    elif dtype == "float32":
        return sbdf_c.SBDF_FLOATTYPEID
    elif dtype == "Float32":
        return sbdf_c.SBDF_FLOATTYPEID
    elif dtype == "float64":
        return sbdf_c.SBDF_DOUBLETYPEID
    elif dtype == "Float64":
        return sbdf_c.SBDF_DOUBLETYPEID
    elif dtype.startswith("datetime64["):
        return sbdf_c.SBDF_DATETIMETYPEID
    elif dtype.startswith("timedelta64["):
        return sbdf_c.SBDF_TIMESPANTYPEID
    elif dtype == "string":
        return sbdf_c.SBDF_STRINGTYPEID
    else:
        raise SBDFError(f"unknown dtype '{dtype}' in {series_description}")


cdef object _VT_CONVERSIONS_ALL = [sbdf_c.SBDF_BOOLTYPEID, sbdf_c.SBDF_STRINGTYPEID]
cdef object _VT_CONVERSIONS_NUMERIC = [sbdf_c.SBDF_BOOLTYPEID, sbdf_c.SBDF_INTTYPEID, sbdf_c.SBDF_LONGTYPEID,
                                       sbdf_c.SBDF_FLOATTYPEID, sbdf_c.SBDF_DOUBLETYPEID]


cdef int _export_infer_valuetype_from_spotfire_typename(series, series_description):
    """Determine a value type for a data set based on the name of the Spotfire type.

    :param series: the values to infer the value type of
    :param series_description: description of series (for error reporting)
    :return: the integer value type id representing the type of series
    :raise SBDFError: if the types of series are inconvertible, mixed, all missing, or unknown
    """
    # Determine if a type has been specified.
    typename = series.attrs['spotfire_type']
    specified_vt = spotfire_typename_to_valuetype_id(typename)

    # Verify the specified type is allowed to be converted from.
    if specified_vt == sbdf_c.SBDF_INTTYPEID and _export_infer_int_promotion(series, series_description):
        # special case for int promotion
        return sbdf_c.SBDF_LONGTYPEID
    elif specified_vt is not None:
        # Type was specified; return immediately if allowable.
        # Conversions to Boolean or String allowed from all types.
        if specified_vt in _VT_CONVERSIONS_ALL:
            return specified_vt
        # Other conversions are dependent on the inferred type.
        try:
            inferred_vt = _export_infer_valuetype_from_pandas_dtype(series, series_description)
        except SBDFError:
            # If no inferred type, accept the specified type.
            return specified_vt
        # Conversions between Boolean, Integer, LongInteger, Real, and SingleReal are all allowed.
        if specified_vt in _VT_CONVERSIONS_NUMERIC and inferred_vt in _VT_CONVERSIONS_NUMERIC:
            return specified_vt
        # Otherwise, the specified type must match the inferred type
        if specified_vt == inferred_vt:
            return specified_vt
        # Raise an error if not allowable
        raise SBDFError(f"cannot convert Spotfire {_valuetype_id_to_spotfire_typename(inferred_vt)} type to Spotfire"
                        f" {typename} type; incompatible types")
    else:
        # No type was specified; return the inferred type.
        return _export_infer_valuetype_from_pandas_dtype(series, series_description)


cdef int _export_get_value_encoding(int valuetype_id, bint encoding_rle):
    """Determine the correct SBDF encoding to use for a column.

    :param valuetype_id: the integer value type id of the column
    :param encoding_rle: whether RLE encoding was requested by the caller of export_data
    :return: the integer SBDF encoding constant for the column
    """
    if valuetype_id == sbdf_c.SBDF_BOOLTYPEID:
        return sbdf_c.SBDF_BITARRAYENCODINGTYPEID
    elif encoding_rle and valuetype_id != sbdf_c.SBDF_BINARYTYPEID:
        return sbdf_c.SBDF_RUNLENGTHENCODINGTYPEID
    else:
        return sbdf_c.SBDF_PLAINARRAYENCODINGTYPEID


cdef (int, sbdf_c.sbdf_valuearray*) _export_process_invalid_array(_ExportContext context,
                                                                  Py_ssize_t start, Py_ssize_t count,
                                                                  sbdf_c.sbdf_columnslice* col_slice):
    """Process the invalid array into SBDF API structures.

    :param context: the export context containing information about the column
    :param start: the index of the first row in the column slice to create
    :param count: the number of rows in the column slice to create
    :param col_slice: the SBDF column slice to add the invalid array to
    :return: Cython C-tuple containing SBDF error code and created SBDF value array
    """
    cdef sbdf_c.sbdf_object* invalids = NULL
    cdef sbdf_c.sbdf_valuearray* invalid_array = NULL
    if context.any_invalid:
        error = sbdf_c.sbdf_obj_create_arr(sbdf_c.sbdf_vt_bool(), <int>count,
                                           _export_get_offset_ptr(context.invalid_array, start, count),
                                           NULL, &invalids)
        if error != sbdf_c.SBDF_OK:
            return error, NULL
        error = sbdf_c.sbdf_va_create_dflt(invalids, &invalid_array)
        if error != sbdf_c.SBDF_OK:
            return error, NULL
        sbdf_c.sbdf_obj_destroy(invalids)
        error = sbdf_c.sbdf_cs_add_property(col_slice, sbdf_c.SBDF_ISINVALID_VALUEPROPERTY, invalid_array)
        if error != sbdf_c.SBDF_OK:
            return error, NULL
        return error, invalid_array
    else:
        return sbdf_c.SBDF_OK, NULL


cdef inline void* _export_get_offset_ptr(np_c.ndarray array, Py_ssize_t start, Py_ssize_t count):
    """Slice a NumPy ``ndarray`` using Cython memoryviews.

    :param array: the NumPy array to slice
    :param start: the index of the first element of the slice
    :param count: the number of elements to include in the slice
    :return: a pointer to the memory (owned by the NumPy array) of the slice
    """
    cdef np_c.ndarray sliced = array[start : start + count]
    return np_c.PyArray_DATA(sliced)


cdef sbdf_c.sbdf_metadata_head* _export_metadata(dict md, int column_num):
    """Process a Python metadata representation into its SBDF API equivalent

    :param md: dictionary containing table or column metadata
    :param column_num: 0-based column number, or -1 for table metadata (for error reporting)
    :return: SBDF metadata structure
    :raise SBDFError: if errors occur in the SBDF C library
    """
    cdef sbdf_c.sbdf_metadata_head* md_head = NULL
    cdef sbdf_c.sbdf_object* obj = NULL
    cdef int val_len
    cdef sbdf_c.sbdf_valuetype val_type
    cdef int* data_lengths = NULL
    cdef double* data_double
    cdef long* data_long
    cdef float* data_float
    cdef int* data_int
    cdef unsigned char* data_bool
    cdef long long* data_datetime
    cdef _SbdfDecimal* data_decimal

    error = sbdf_c.sbdf_md_create(&md_head)
    if error != sbdf_c.SBDF_OK:
        raise SBDFError(f"cannot create metadata: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

    if column_num == -1:
        metadata_description = "Table"
    else:
        metadata_description = f"Column {column_num}"

    for (name_str, val) in md.items():
        name = name_str.encode("utf-8")
        if not isinstance(val, list):
            val = [val]
        val_len = <int>len(val)
        if val_len > 1:
            raise SBDFError(f"{metadata_description} metadata '{name_str}' is not length 1")
        val_type.id = _export_infer_valuetype_from_type(val, f"{metadata_description} metadata '{name_str}'")

        if val_type.id == sbdf_c.SBDF_STRINGTYPEID:
            obj = _export_extract_string_obj(val, [False] * val_len, 0, val_len)
            error = sbdf_c.SBDF_OK
        elif val_type.id == sbdf_c.SBDF_DOUBLETYPEID:
            data_double = <double*>mem.PyMem_RawMalloc(val_len * sizeof(double))
            for i in range(val_len):
                data_double[i] = val[i]
            error = sbdf_c.sbdf_obj_create_arr(val_type, val_len, data_double, NULL, &obj)
            mem.PyMem_RawFree(<void*>data_double)
        elif val_type.id == sbdf_c.SBDF_LONGTYPEID:
            data_long = <long*>mem.PyMem_RawMalloc(val_len * sizeof(long))
            for i in range(val_len):
                data_long[i] = val[i]
            error = sbdf_c.sbdf_obj_create_arr(val_type, val_len, data_long, NULL, &obj)
            mem.PyMem_RawFree(<void*>data_long)
        elif val_type.id == sbdf_c.SBDF_FLOATTYPEID:
            data_float = <float*>mem.PyMem_RawMalloc(val_len * sizeof(float))
            for i in range(val_len):
                data_float[i] = val[i]
            error = sbdf_c.sbdf_obj_create_arr(val_type, val_len, data_float, NULL, &obj)
            mem.PyMem_RawFree(<void*>data_float)
        elif val_type.id == sbdf_c.SBDF_INTTYPEID:
            data_int = <int*>mem.PyMem_RawMalloc(val_len * sizeof(int))
            for i in range(val_len):
                data_int[i] = val[i]
            error = sbdf_c.sbdf_obj_create_arr(val_type, val_len, data_int, NULL, &obj)
            mem.PyMem_RawFree(<void*>data_int)
        elif val_type.id == sbdf_c.SBDF_BOOLTYPEID:
            data_bool = <unsigned char*>mem.PyMem_RawMalloc(val_len * sizeof(unsigned char))
            for i in range(val_len):
                data_bool[i] = 1 if val[i] else 0
            error = sbdf_c.sbdf_obj_create_arr(val_type, val_len, data_bool, NULL, &obj)
            mem.PyMem_RawFree(<void*>data_bool)
        elif val_type.id == sbdf_c.SBDF_DATETIMETYPEID:
            data_datetime = <long long*>mem.PyMem_RawMalloc(val_len * sizeof(long long))
            for i in range(val_len):
                dt = val[i].to_pydatetime() if isinstance(val[i], pd.Timestamp) else val[i]
                data_datetime[i] = int((dt - _DATETIME_EPOCH)/_TIMEDELTA_ONE_MSEC)
            error = sbdf_c.sbdf_obj_create_arr(val_type, val_len, data_datetime, NULL, &obj)
            mem.PyMem_RawFree(<void*>data_datetime)
        elif val_type.id == sbdf_c.SBDF_DATETYPEID:
            data_datetime = <long long *>mem.PyMem_RawMalloc(val_len * sizeof(long long))
            for i in range(val_len):
                data_datetime[i] = int((val[i] - _DATETIME_EPOCH.date())/_TIMEDELTA_ONE_MSEC)
            error = sbdf_c.sbdf_obj_create_arr(val_type, val_len, data_datetime, NULL, &obj)
            mem.PyMem_RawFree(<void*>data_datetime)
        elif val_type.id == sbdf_c.SBDF_TIMETYPEID:
            data_datetime = <long long *>mem.PyMem_RawMalloc(val_len * sizeof(long long))
            for i in range(val_len):
                data_datetime[i] = (datetime.datetime.combine(datetime.datetime.min, val[i]) - datetime.datetime.min) \
                                   // _TIMEDELTA_ONE_MSEC
            error = sbdf_c.sbdf_obj_create_arr(val_type, val_len, data_datetime, NULL, &obj)
            mem.PyMem_RawFree(<void*>data_datetime)
        elif val_type.id == sbdf_c.SBDF_TIMESPANTYPEID:
            data_datetime = <long long*>mem.PyMem_RawMalloc(val_len * sizeof(long long))
            for i in range(val_len):
                td = val[i].to_pytimedelta() if isinstance(val[i], pd.Timedelta) else val[i]
                data_datetime[i] = int(td / _TIMEDELTA_ONE_MSEC)
            error = sbdf_c.sbdf_obj_create_arr(val_type, val_len, data_datetime, NULL, &obj)
            mem.PyMem_RawFree(<void*>data_datetime)
        elif val_type.id == sbdf_c.SBDF_BINARYTYPEID:
            obj = _export_extract_binary_obj(val, [False] * val_len, 0, val_len)
            error = sbdf_c.SBDF_OK
        elif val_type.id == sbdf_c.SBDF_DECIMALTYPEID:
            data_decimal = <_SbdfDecimal*>mem.PyMem_RawMalloc(val_len * sizeof(_SbdfDecimal))
            for i in range(val_len):
                data_decimal[i] = _decimal_to_bytes(val[i])
            error = sbdf_c.sbdf_obj_create_arr(val_type, val_len, data_decimal, data_lengths, &obj)
            mem.PyMem_RawFree(<void*>data_decimal)
        if error != sbdf_c.SBDF_OK:
            raise SBDFError(f"cannot create metadata object: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

        # Add the metadata item
        error = sbdf_c.sbdf_md_add(name, obj, NULL, md_head)
        if error != sbdf_c.SBDF_OK:
            raise SBDFError(f"cannot add metadata: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")
        sbdf_c.sbdf_obj_destroy(obj)
        obj = NULL

    return md_head


def export_data(obj, sbdf_file, default_column_name="x", Py_ssize_t rows_per_slice=0, encoding_rle=True):
    """Export data to an SBDF file.

    :param obj: the data object to export
    :param sbdf_file: the filename to export the data to
    :param default_column_name: the column name to use when exporting data objects without intrinsic names (such as
                                lists or scalar values)
    :param rows_per_slice: the number of data rows to emit per table slice.  If 0, automatically determine an
                           appropriate value
    :param encoding_rle: should the table slices be encoded using RLE?
    :raises SBDFError: if a problem is encountered during export
    """
    cdef int i
    cdef stdio.FILE* output_file = NULL
    cdef sbdf_c.sbdf_metadata_head* table_md = NULL
    cdef sbdf_c.sbdf_tablemetadata* table_meta = NULL
    cdef Py_ssize_t num_columns
    cdef sbdf_c.sbdf_metadata_head* col_md = NULL
    cdef sbdf_c.sbdf_valuetype col_vt
    cdef Py_ssize_t row_count = 0
    cdef Py_ssize_t row_offset = 0
    cdef _AllocatedList saved_value_arrays
    cdef _AllocatedList saved_col_slices
    cdef sbdf_c.sbdf_tableslice* table_slice = NULL
    cdef exporter_fn exporter
    cdef sbdf_c.sbdf_object* values = NULL
    cdef int value_encoding = 0
    cdef sbdf_c.sbdf_valuearray* value_array = NULL
    cdef sbdf_c.sbdf_columnslice* col_slice = NULL
    cdef sbdf_c.sbdf_valuearray* invalid_array = NULL

    try:
        # Extract data and metadata from obj
        # Polars DataFrames (tabular)
        if pl is not None and isinstance(obj, pl.DataFrame):
            exported = _export_obj_polars_dataframe(obj)
        # Polars Series (columnar)
        elif pl is not None and isinstance(obj, pl.Series):
            exported = _export_obj_polars_series(obj, default_column_name)
        # Pandas DataFrames (tabular)
        elif isinstance(obj, pd.DataFrame):
            exported = _export_obj_dataframe(obj)
        # Pandas Series (columnar)
        elif isinstance(obj, pd.Series):
            exported = _export_obj_series(obj, default_column_name)
        # NumPy Array (columnar)
        elif isinstance(obj, np_c.ndarray):
            exported = _export_obj_numpy(obj, default_column_name)
        # Dicts of Lists (tabular)
        elif isinstance(obj, dict):
            exported = _export_obj_dict_of_lists(obj)
        # Strings and Bytes (scalar)
        elif isinstance(obj, (str, bytes, bytearray)):
            exported = _export_obj_scalar(obj, default_column_name)
        # Iterable (columnar)
        elif isinstance(obj, collections.abc.Iterable):
            exported = _export_obj_iterable(obj, default_column_name)
        # Matplotlib Figures (scalar)
        elif matplotlib is not None and isinstance(obj, matplotlib.figure.Figure):
            exported = _export_obj_matplotlib_figure(obj, default_column_name)
        # Seaborn Grids (scalar)
        elif seaborn is not None and isinstance(obj, seaborn.axisgrid.Grid):
            exported = _export_obj_seaborn_grid(obj, default_column_name)
        # PIL Images (scalar)
        elif PIL is not None and isinstance(obj, PIL.Image.Image):
            exported = _export_obj_pil_image(obj, default_column_name)
        # Try if all else fails (scalar)
        else:
            exported = _export_obj_scalar(obj, default_column_name)
        table_metadata, column_names, column_metadata, exporter_contexts = exported

        # Open the SBDF file
        output_file = _pathlike_to_fileptr(sbdf_file, "wb")

        # Create the table metadata structures
        table_md = _export_metadata(table_metadata, -1)
        error = sbdf_c.sbdf_tm_create(table_md, &table_meta)
        if error != sbdf_c.SBDF_OK:
            raise SBDFError(f"cannot create table metadata: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")
        sbdf_c.sbdf_md_destroy(table_md)

        # Create the column metadata structures
        num_columns = len(column_names)
        for i in range(num_columns):
            if i == 0:
                row_count = len(exporter_contexts[i])
            else:
                if row_count != len(exporter_contexts[i]):
                    raise SBDFError(f"column '{column_names[i]}' has inconsistent column length")
            col = str(column_names[i]).encode('utf-8')
            col_md = _export_metadata(column_metadata[i], i)
            col_vt.id = exporter_contexts[i].get_valuetype_id()
            error = sbdf_c.sbdf_cm_set_values(col, col_vt, col_md)
            if error != sbdf_c.SBDF_OK:
                raise SBDFError(f"cannot create column metadata: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")
            error = sbdf_c.sbdf_tm_add(col_md, table_meta)
            if error != sbdf_c.SBDF_OK:
                raise SBDFError(f"cannot add column metadata: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")
            sbdf_c.sbdf_md_destroy(col_md)

        # Write the file header
        error = sbdf_c.sbdf_fh_write_cur(output_file)
        if error != sbdf_c.SBDF_OK:
            raise SBDFError(f"error writing '{sbdf_file}': {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

        # Write the table metadata
        error = sbdf_c.sbdf_tm_write(output_file, table_meta)
        if error != sbdf_c.SBDF_OK:
            raise SBDFError(f"error writing '{sbdf_file}': {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")
        sbdf_c.sbdf_tm_destroy(table_meta)

        # Determine the number of rows per slice
        if rows_per_slice <= 0:
            rows_per_slice = max(10, 100000 // max(1, num_columns))

        # Slice the data
        _allocated_list_new(&saved_col_slices, num_columns)
        _allocated_list_new(&saved_value_arrays, num_columns * 2)
        while row_offset < row_count:
            rows_per_slice = min(rows_per_slice, row_count - row_offset)

            # Create the table slice
            error = sbdf_c.sbdf_ts_create(table_meta, &table_slice)
            if error != sbdf_c.SBDF_OK:
                raise SBDFError(f"error creating table slice: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

            # Add each column to the slice
            for i in range(num_columns):
                values = NULL
                context = exporter_contexts[i]
                pol_id = context.get_polars_exporter_id()
                if pol_id == _POL_EXP_DATETIME:
                    exporter = _export_vt_polars_datetime
                elif pol_id == _POL_EXP_DATE:
                    exporter = _export_vt_polars_date
                elif pol_id == _POL_EXP_TIMESPAN:
                    exporter = _export_vt_polars_timespan
                elif pol_id == _POL_EXP_TIME:
                    exporter = _export_vt_polars_time
                elif pol_id == _POL_EXP_STRING:
                    exporter = _export_vt_polars_string
                else:
                    exporter = _export_get_exporter(context.get_valuetype_id())
                error = exporter(context, row_offset, rows_per_slice, &values)
                if error != sbdf_c.SBDF_OK:
                    raise SBDFError(f"error exporting column '{column_names[i]}': "
                                    f"{sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

                # Create the value array
                value_encoding = _export_get_value_encoding(context.get_valuetype_id(), encoding_rle)
                value_array = NULL
                error = sbdf_c.sbdf_va_create(value_encoding, values, &value_array)
                if value_array != NULL:
                    _allocated_list_add(&saved_value_arrays, value_array)
                if error != sbdf_c.SBDF_OK:
                    raise SBDFError(f"error creating value array: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")
                sbdf_c.sbdf_obj_destroy(values)

                # Create a column slice
                col_slice = NULL
                error = sbdf_c.sbdf_cs_create(&col_slice, value_array)
                if col_slice != NULL:
                    _allocated_list_add(&saved_col_slices, col_slice)
                if error != sbdf_c.SBDF_OK:
                    raise SBDFError(f"error creating column slice: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

                # Create the invalid array
                error, invalid_array = _export_process_invalid_array(context, row_offset, rows_per_slice, col_slice)
                if invalid_array != NULL:
                    _allocated_list_add(&saved_value_arrays, invalid_array)
                if error != sbdf_c.SBDF_OK:
                    raise SBDFError(f"error exporting invalids: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

                # Add the column slice to the table slice
                error = sbdf_c.sbdf_ts_add(col_slice, table_slice)
                if error != sbdf_c.SBDF_OK:
                    raise SBDFError(f"error adding column slice: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

            # Write the table slice
            error = sbdf_c.sbdf_ts_write(output_file, table_slice)
            if error != sbdf_c.SBDF_OK:
                raise SBDFError(f"error writing table slice: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")
            sbdf_c.sbdf_ts_destroy(table_slice)
            _allocated_list_done(&saved_col_slices, <_allocated_dealloc_fn>sbdf_c.sbdf_cs_destroy)
            _allocated_list_done(&saved_value_arrays, <_allocated_dealloc_fn>sbdf_c.sbdf_va_destroy)

            # Next slice!
            row_offset += rows_per_slice

        # Write the end-of-table marker
        error = sbdf_c.sbdf_ts_write_end(output_file)
        if error != sbdf_c.SBDF_OK:
            raise SBDFError(f"error writing end of table: {sbdf_c.sbdf_err_get_str(error).decode('utf-8')}")

    finally:
        # Close the output file
        if output_file != NULL:
            stdio.fclose(output_file)
