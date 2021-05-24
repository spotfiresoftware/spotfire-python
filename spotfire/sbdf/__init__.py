"""
TODOS:
* Return table/column metadata as well as the table data
* Support Decimal type
* Support _ValueArrayEncodingId.RUN_LENGTH array type
* Contemplate making an SBDF writer
"""
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Tuple, Union

import numpy as np
import pandas as pd
from pandas.api.types import union_categoricals

from .array import _next_bytes_as_array
from .base import SectionTypeId, ValueTypeId, _next_bytes_as_int, _next_bytes_as_str
from .metadata import Metadatum, _next_bytes_as_column_metadata, _next_bytes_as_metadata


def _next_bytes_as_section_id(file: BinaryIO) -> int:
    """Reads section type id from file."""
    magic_number = _next_bytes_as_int(file)
    if magic_number != 0xDF:
        raise ValueError("Section magic number 1 not found")
    magic_number = _next_bytes_as_int(file)
    if magic_number != 0x5B:
        raise ValueError("Section magic number 2 not found")
    section_id = _next_bytes_as_int(file)
    return section_id


def import_data(
    sbdf_file: Union[str, Path],
    strings_as_categories: bool = False,
    skip_strings: bool = False,
    progress_bar: bool = True,
) -> pd.DataFrame:
    """Import data from an SBDF file and create a pandas DataFrame.

    :param sbdf_file: the file path of the SBDF file to import
    :return: the DataFrame containing the imported data
    """
    # open the SBDF file
    with Path(sbdf_file).open("rb") as file:
        # read file header
        section_id = _next_bytes_as_section_id(file)
        assert section_id == SectionTypeId.FILEHEADER
        version_major = _next_bytes_as_int(file)
        version_minor = _next_bytes_as_int(file)
        if (version_major, version_minor) != (1, 0):
            v = f"{version_major}.{version_minor}"
            msg = f"Only version 1.0 supported, but version {v} encountered."
            raise ValueError(msg)

        # read table metadata
        section_id = _next_bytes_as_section_id(file)
        assert section_id == SectionTypeId.TABLEMETADATA
        table_metadata = {  # noqa F841
            md.name: md.value for md in _next_bytes_as_metadata(file)
        }
        # TODO: parse table metadata into a form that can be returned

        # read column metadata
        n_columns = _next_bytes_as_int(file, n_bytes=4)
        column_metadata_fields: Tuple[Metadatum, ...] = _next_bytes_as_metadata(
            file, skip_values=True
        )
        column_metadatas: Tuple[Dict[str, Any], ...] = tuple(
            {
                md.name: md.value
                for md in _next_bytes_as_column_metadata(file, column_metadata_fields)
            }
            for _ in range(n_columns)
        )
        # TODO: parse column metadata into a form that can be returned

        column_names = tuple(md_dict["Name"] for md_dict in column_metadatas)
        column_types = tuple(
            ValueTypeId(md_dict["DataType"][0]) for md_dict in column_metadatas
        )
        # read tables
        pandas_data: List[List[np.ndarray]] = [[] for _ in range(n_columns)]
        while True:
            # read next table slice
            section_id = _next_bytes_as_section_id(file)
            if section_id == SectionTypeId.TABLEEND:
                break
            if section_id != SectionTypeId.TABLESLICE:
                raise ValueError(
                    f"Expected table slice ID, got {section_id} instead"
                )
            slice_n_columns = _next_bytes_as_int(file, n_bytes=4)
            assert slice_n_columns == n_columns
            # read each column slice in the table slice
            for column_index, value_type in enumerate(column_types):
                section_id = _next_bytes_as_section_id(file)
                assert section_id == SectionTypeId.COLUMNSLICE
                col_vals = _next_bytes_as_array(
                    file,
                    strings_as_categories=strings_as_categories,
                    skip_strings=skip_strings,
                )
                # handle column properties (ignoring all but IsInvalid)
                n_properties = _next_bytes_as_int(file, n_bytes=4)
                for _ in range(n_properties):
                    property_name = _next_bytes_as_str(file)
                    property_value = _next_bytes_as_array(file)
                    # we only care about the "IsInvalid" property, which defines nulls
                    if property_name == "IsInvalid":
                        invalid_mask = property_value.astype(np.bool_)
                        # use Pandas to handle type changes (e.g. int to float)
                        col_vals = pd.Series(col_vals)
                        missing_value = (
                            None if value_type == ValueTypeId.STRING else np.nan
                        )
                        col_vals.loc[invalid_mask] = missing_value
                        col_vals = col_vals.values
                pandas_data[column_index].append(col_vals)

        # concatenate column chunks
        for i, value_type in enumerate(column_types):
            if strings_as_categories and value_type == ValueTypeId.STRING:
                pandas_data[i] = union_categoricals(pandas_data[i])
            else:
                pandas_data[i] = np.concatenate(pandas_data[i])
        df = pd.DataFrame(dict(zip(column_names, pandas_data)), copy=False)
        return df
