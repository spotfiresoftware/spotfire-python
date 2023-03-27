# Copyright © 2022. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

from libc.stdio cimport FILE

cdef extern from "all.h" nogil:
    # errors.h
    const char* sbdf_err_get_str(int)
    cdef enum:
        SBDF_OK
        SBDF_ERROR_ARGUMENT_NULL
        SBDF_ERROR_OUT_OF_MEMORY
        SBDF_ERROR_UNKNOWN_TYPEID
        SBDF_ERROR_IO
        SBDF_ERROR_UNKNOWN_VALUEARRAY_ENCODING
        SBDF_ERROR_ARRAY_LENGTH_MUST_BE_1
        SBDF_ERROR_METADATA_NOT_FOUND
        SBDF_ERROR_METADATA_ALREADY_EXISTS
        SBDF_ERROR_INCORRECT_METADATA
        SBDF_ERROR_METADATA_READONLY
        SBDF_ERROR_INCORRECT_COLUMNMETADATA
        SBDF_ERROR_VALUETYPES_MUST_BE_EQUAL
        SBDF_ERROR_UNEXPECTED_SECTION_ID
        SBDF_ERROR_PROPERTY_ALREADY_EXISTS
        SBDF_ERROR_PROPERTY_NOT_FOUND
        SBDF_ERROR_INCORRECT_PROPERTY_TYPE
        SBDF_ERROR_ROW_COUNT_MISMATCH
        SBDF_ERROR_UNKNOWN_VERSION
        SBDF_ERROR_COLUMN_COUNT_MISMATCH
        SBDF_ERROR_MAGIC_NUMBER_MISSING
        SBDF_ERROR_INVALID_SIZE
        SBDF_TABLEEND
        SBDF_ERROR_UNKNOWN_ERROR

    # valuetypeid.h
    cdef enum:
        SBDF_UNKNOWNTYPEID
        SBDF_BOOLTYPEID
        SBDF_INTTYPEID
        SBDF_LONGTYPEID
        SBDF_FLOATTYPEID
        SBDF_DOUBLETYPEID
        SBDF_DATETIMETYPEID
        SBDF_DATETYPEID
        SBDF_TIMETYPEID
        SBDF_TIMESPANTYPEID
        SBDF_STRINGTYPEID
        SBDF_BINARYTYPEID
        SBDF_DECIMALTYPEID

    # valuetype.h
    struct sbdf_valuetype:
        int id
    int sbdf_vt_cmp(sbdf_valuetype, sbdf_valuetype)
    sbdf_valuetype sbdf_vt_bool()
    sbdf_valuetype sbdf_vt_int()
    sbdf_valuetype sbdf_vt_long()
    sbdf_valuetype sbdf_vt_float()
    sbdf_valuetype sbdf_vt_double()
    sbdf_valuetype sbdf_vt_datetime()
    sbdf_valuetype sbdf_vt_date()
    sbdf_valuetype sbdf_vt_time()
    sbdf_valuetype sbdf_vt_timespan()
    sbdf_valuetype sbdf_vt_string()
    sbdf_valuetype sbdf_vt_binary()
    sbdf_valuetype sbdf_vt_decimal()

    # sbdfstring.h
    char* sbdf_str_create(const char*)
    char* sbdf_str_create_len(const char*, int)
    void sbdf_str_destroy(char*)
    int sbdf_str_len(const char*)
    int sbdf_str_cmp(const char*, const char*)
    char* sbdf_str_copy(const char*)
    int sbdf_convert_utf8_to_iso88591(const char*, char*)
    int sbdf_convert_iso88591_to_utf8(const char*, char*)

    # bytearray.h
    unsigned char* sbdf_ba_create(const unsigned char*, int)
    void sbdf_ba_destroy(unsigned char*)
    int sbdf_ba_get_len(const unsigned char*)
    int sbdf_ba_memcmp(const unsigned char*, const unsigned char *)

    # object.h
    struct sbdf_object:
        sbdf_valuetype type
        int count
        void* data
    int sbdf_obj_create_arr(sbdf_valuetype, int, const void*, const int*, sbdf_object**)
    void sbdf_obj_destroy(sbdf_object*)
    int sbdf_obj_create(sbdf_valuetype, const void*, const int*, sbdf_object**)
    int sbdf_obj_copy(const sbdf_object*, sbdf_object**)
    bint sbdf_obj_eq(const sbdf_object*, const sbdf_object*)

    # metadata.h
    struct sbdf_metadata_head:
        sbdf_metadata* first
        int modifiable
    struct sbdf_metadata:
        sbdf_metadata* next
        char* name
        sbdf_object* value
        sbdf_object* default_value
    int sbdf_md_create(sbdf_metadata_head**)
    int sbdf_md_add_str(const char*, const char*, const char*, sbdf_metadata_head*)
    int sbdf_md_add_int(const char*, int, int, sbdf_metadata_head*)
    int sbdf_md_add(const char*, const sbdf_object*, const sbdf_object*, sbdf_metadata_head*)
    int sbdf_md_remove(const char*, sbdf_metadata_head*)
    int sbdf_md_get(const char*, const sbdf_metadata_head*, sbdf_object**)
    int sbdf_md_get_dflt(const char*, const sbdf_metadata_head*, sbdf_object**)
    void sbdf_md_destroy(sbdf_metadata_head*)
    int sbdf_md_cnt(const sbdf_metadata_head*)
    bint sbdf_md_exists(const char*, const sbdf_metadata_head*)
    int sbdf_md_copy(const sbdf_metadata_head*, sbdf_metadata_head*)
    int sbdf_md_set_immutable(sbdf_metadata_head*)
    int sbdf_md_compare_names(const sbdf_metadata**, const sbdf_metadata**)

    # tablemetadata.h
    struct sbdf_tablemetadata:
        sbdf_metadata_head* table_metadata
        int no_columns
        sbdf_metadata_head** column_metadata
    int sbdf_tm_create(sbdf_metadata_head*, sbdf_tablemetadata**)
    void sbdf_tm_destroy(sbdf_tablemetadata*)
    int sbdf_tm_add(sbdf_metadata_head*, sbdf_tablemetadata*)

    # columnmetadata.h
    int sbdf_cm_set_values(const char*, sbdf_valuetype, sbdf_metadata_head*)
    int sbdf_cm_get_type(sbdf_metadata_head*, sbdf_valuetype*)
    int sbdf_cm_get_name(sbdf_metadata_head*, char**)
    char* SBDF_COLUMNMETADATA_NAME
    char* SBDF_COLUMNMETADATA_DATATYPE

    # valuearray.h
    enum:
        SBDF_PLAINARRAYENCODINGTYPEID
        SBDF_RUNLENGTHENCODINGTYPEID
        SBDF_BITARRAYENCODINGTYPEID
    struct sbdf_valuearray:
        pass
    int sbdf_va_create(int, const sbdf_object*, sbdf_valuearray**)
    int sbdf_va_create_plain(const sbdf_object*, sbdf_valuearray**)
    int sbdf_va_create_rle(const sbdf_object*, sbdf_valuearray**)
    int sbdf_va_create_bit(const sbdf_object*, sbdf_valuearray**)
    void sbdf_va_destroy(sbdf_valuearray*)
    int sbdf_va_create_dflt(const sbdf_object*, sbdf_valuearray**)
    int sbdf_va_get_values(sbdf_valuearray*, sbdf_object**)
    int sbdf_va_row_cnt(sbdf_valuearray*)

    # columnslice.h
    char* SBDF_ISINVALID_VALUEPROPERTY
    char* SBDF_ERRORCODE_VALUEPROPERTY
    char* SBDF_REPLACEDVALUE_VALUEPROPERTY
    struct sbdf_columnslice:
        sbdf_valuearray* values
        int prop_cnt
        char** property_names
        sbdf_valuearray** properties
        int owned
    int sbdf_cs_create(sbdf_columnslice**, sbdf_valuearray*)
    int sbdf_cs_add_property(sbdf_columnslice*, const char*, sbdf_valuearray*)
    int sbdf_cs_get_property(sbdf_columnslice*, const char*, sbdf_valuearray**)
    int sbdf_cs_row_cnt(sbdf_columnslice*)
    void sbdf_cs_destroy(sbdf_columnslice*)
    void sbdf_cs_destroy_all(sbdf_columnslice*)

    # tableslice.h
    struct sbdf_tableslice:
        sbdf_tablemetadata* table_metadata
        int no_columns
        sbdf_columnslice** columns
        int owned
    int sbdf_ts_create(sbdf_tablemetadata*, sbdf_tableslice**)
    int sbdf_ts_add(sbdf_columnslice*, sbdf_tableslice*)
    void sbdf_ts_destroy(sbdf_tableslice*)

cdef extern from "all_io.h" nogil:
    # fileheader.h
    int sbdf_fh_write_cur(FILE*)
    int sbdf_fh_read(FILE*, int*, int*)

    # tablemetadata_io.h
    int sbdf_tm_read(FILE*, sbdf_tablemetadata**)
    int sbdf_tm_write(FILE*, const sbdf_tablemetadata*)

    # tableslice_io.h
    int sbdf_ts_read(FILE*, const sbdf_tablemetadata*, char*, sbdf_tableslice**)
    int sbdf_ts_write(FILE*, const sbdf_tableslice*)
    int sbdf_ts_skip(FILE*, const sbdf_tablemetadata*)
    int sbdf_ts_write_end(FILE*)
