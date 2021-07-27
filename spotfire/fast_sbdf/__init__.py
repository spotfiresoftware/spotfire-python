# Contributions to SBDF reader functionality provided by PDF Solutions, Inc. (C) 2021

"""
TODOS:
* Return table/column metadata as well as the table data
* Support Decimal type
* Support _ValueArrayEncodingId.RUN_LENGTH array type
* Contemplate making an SBDF writer
"""
from contextlib import ExitStack
from pathlib import Path
from typing import Any, BinaryIO, Dict, Hashable, List, Tuple, Union, cast

import numpy as np
import pandas as pd

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


from .array import (
    PackedArray,
    PackedBitArray,
    PackedPlainArray,
    next_bytes_as_packed_array,
    unpack_bit_array,
    unpack_packed_array,
)
from .base import SectionTypeId, ValueTypeId, next_bytes_as_int, next_bytes_as_str
from .metadata import Metadatum, next_bytes_as_column_metadata, next_bytes_as_metadata


def _next_bytes_as_section_id(file: BinaryIO) -> int:
    """Reads section type id from file."""
    magic_number = next_bytes_as_int(file)
    if magic_number != 0xDF:
        raise ValueError("Section magic number 1 not found")
    magic_number = next_bytes_as_int(file)
    if magic_number != 0x5B:
        raise ValueError("Section magic number 2 not found")
    section_id = next_bytes_as_int(file)
    return section_id


def import_data(  # noqa: C901
    sbdf_file: Union[str, Path],
    strings_as_categories: bool = False,
    skip_strings: bool = False,
    progress_bar: bool = True,
) -> pd.DataFrame:
    """Import data from an SBDF file and create a pandas DataFrame.

    TODO: document keyword arguments
    """
    # prevent edge cases for skip_strings option
    if skip_strings and strings_as_categories:
        raise ValueError("Strings cannot be both skipped and treated as categories")

    # establish a master context manager for the duration of reading the file
    with ExitStack() as read_context:
        # open the SBDF file, managing context using the master context
        file = read_context.enter_context(Path(sbdf_file).open("rb"))

        # if we have tqdm, create and add progress bar managed by master read context
        pbar = None
        if tqdm is not None:
            pbar = read_context.enter_context(
                tqdm(desc="Reading File", unit="row", disable=not progress_bar)
            )

        # read file header
        section_id = _next_bytes_as_section_id(file)
        assert section_id == SectionTypeId.FILEHEADER
        version_major = next_bytes_as_int(file)
        version_minor = next_bytes_as_int(file)
        if (version_major, version_minor) != (1, 0):
            v = f"{version_major}.{version_minor}"
            msg = f"Only version 1.0 supported, but version {v} encountered."
            raise ValueError(msg)

        # read table metadata
        section_id = _next_bytes_as_section_id(file)
        assert section_id == SectionTypeId.TABLEMETADATA
        table_metadata = {  # noqa F841
            md.name: md.value for md in next_bytes_as_metadata(file)
        }
        # TODO: parse table metadata into a form that can be returned

        # read column metadata
        n_columns = next_bytes_as_int(file, n_bytes=4)
        column_metadata_fields: Tuple[Metadatum, ...] = next_bytes_as_metadata(
            file, skip_values=True
        )
        column_metadatas: Tuple[Dict[str, Any], ...] = tuple(
            {
                md.name: md.value
                for md in next_bytes_as_column_metadata(file, column_metadata_fields)
            }
            for _ in range(n_columns)
        )
        # TODO: parse column metadata into a form that can be returned

        column_names: Tuple[Hashable, ...] = tuple(
            md_dict["Name"] for md_dict in column_metadatas
        )
        column_types = tuple(
            ValueTypeId(md_dict["DataType"][0]) for md_dict in column_metadatas
        )

        # read table content as arrays packed into bytes objects
        rows_per_slice: List[int] = []
        table_slices: List[Dict[Hashable, PackedArray]] = []
        table_slice_nulls: List[Dict[Hashable, PackedBitArray]] = []
        while True:
            current_slice: Dict[Hashable, PackedArray] = dict()
            current_slice_nulls: Dict[Hashable, PackedBitArray] = dict()
            # read next table slice
            section_id = _next_bytes_as_section_id(file)
            if section_id == SectionTypeId.TABLEEND:
                break
            if section_id != SectionTypeId.TABLESLICE:
                raise ValueError(f"Expected table slice ID, got {section_id} instead")
            slice_n_columns = next_bytes_as_int(file, n_bytes=4)
            assert slice_n_columns == n_columns
            # read each column slice in the table slice
            for column_name in column_names:
                section_id = _next_bytes_as_section_id(file)
                assert section_id == SectionTypeId.COLUMNSLICE
                col_vals = next_bytes_as_packed_array(file)
                # handle column properties (ignoring all but IsInvalid)
                n_properties = next_bytes_as_int(file, n_bytes=4)
                for _ in range(n_properties):
                    property_name = next_bytes_as_str(file)
                    property_value = cast(
                        PackedBitArray, next_bytes_as_packed_array(file)
                    )
                    # we only care about the "IsInvalid" property, which defines nulls
                    if property_name == "IsInvalid":
                        current_slice_nulls[column_name] = property_value
                current_slice[column_name] = col_vals
            n_row_in_slice = next(iter(current_slice.values())).n
            rows_per_slice.append(n_row_in_slice)
            if pbar is not None:
                pbar.update(n_row_in_slice)
            table_slices.append(current_slice)
            table_slice_nulls.append(current_slice_nulls)

    # concatenate column slices and missing mask slices into single packed objects
    col_name_iter = column_names
    if tqdm is not None:
        col_name_iter = tqdm(
            col_name_iter,
            desc="Concatenating Column Slice Data",
            unit="col",
            disable=not progress_bar,
        )
    packed_full_columns = {}
    packed_missing_masks = {}
    for col_name in col_name_iter:
        chunks = tuple(ts.pop(col_name) for ts in table_slices)
        array_type = type(chunks[0]) if len(chunks) > 0 else PackedPlainArray
        packed_full_columns[col_name] = array_type.concatenate(chunks)  # type: ignore
        packed_missing_masks[col_name] = PackedBitArray.concatenate(
            tuple(
                tsn.pop(col_name, PackedBitArray.empty(n))
                for tsn, n in zip(table_slice_nulls, rows_per_slice)
            )
        )

    # unpack columns from bytes objects into numpy arrays
    col_name_type_iter = zip(column_names, column_types)
    if tqdm is not None:
        col_name_type_iter = tqdm(
            col_name_type_iter,
            desc="Unpacking Data",
            unit="col",
            disable=not progress_bar,
            total=n_columns,
        )
    pandas_data = {}
    for col_name, col_type in col_name_type_iter:
        # skip strings if setting enabled
        if skip_strings and col_type == ValueTypeId.STRING:
            del packed_full_columns[col_name]
            pandas_data[col_name] = pd.Categorical.from_codes(
                codes=np.zeros(sum(rows_per_slice), dtype=np.uint8),
                categories=["<SKIPPED>"],
            )
            continue
        # unpack column to array otherwise
        packed = packed_full_columns.pop(col_name)
        if isinstance(packed, PackedPlainArray):
            col_array = unpack_packed_array(packed, strings_as_categories)
        elif isinstance(packed, PackedBitArray):
            col_array = unpack_bit_array(packed)
        else:
            raise RuntimeError(
                "Unable to parse file correctly, we thought we had a packed "
                "array, but we didn't!"
            )
        pandas_data[col_name] = col_array

    # unpack and apply missing masks
    col_name_type_iter = zip(column_names, column_types)
    if tqdm is not None:
        col_name_type_iter = tqdm(
            col_name_type_iter,
            desc="Handling Missing Values",
            unit="col",
            disable=not progress_bar,
            total=n_columns,
        )
    for col_name, col_type in col_name_type_iter:
        missing_mask = unpack_bit_array(packed_missing_masks.pop(col_name))
        if missing_mask.any():
            col_array = pandas_data[col_name]
            missing_value = (
                None
                if col_type
                in (ValueTypeId.BINARY, ValueTypeId.DECIMAL, ValueTypeId.STRING)
                else np.nan
            )
            needs_copy = (
                not col_array.flags.writeable if hasattr(col_array, "flags") else False
            )
            # convert numpy-native binary array to Python object array for nullability
            dtype = "O" if col_type == ValueTypeId.BINARY else None
            col_array = pd.Series(col_array, copy=needs_copy, dtype=dtype)
            col_array.loc[missing_mask] = missing_value
            col_array = col_array.values
            pandas_data[col_name] = col_array

    # create dataframe and return
    df = pd.DataFrame(pandas_data)
    return df
