# Copyright © 2021. TIBCO Software Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Functions to import data tables into Python from SBDF files and export data from Python to SBDF files."""

import collections.abc
import datetime
import decimal
import enum
import struct
import tempfile
import typing
import warnings

import bitstring
import pandas as pd
import numpy as np

from spotfire import _utils

try:
    import geopandas as gpd
    import shapely
    import shapely.geometry.base as shp_geom
except ImportError:
    gpd = None
    shapely = None
    shp_geom = None

try:
    import matplotlib
    import matplotlib.figure
except ImportError:
    matplotlib = None

try:
    import PIL
    import PIL.Image
except ImportError:
    PIL = None

try:
    import seaborn
except ImportError:
    seaborn = None

__all__ = ["import_data", "export_data"]


# Public Functions


def import_data(sbdf_file: typing.Union[str, bytes, int]) -> pd.DataFrame:
    """Import data from an SBDF file and create a 'pandas' DataFrame.

    :param sbdf_file: the filename of the SBDF file to import
    :return: the DataFrame containing the imported data
    :raises SBDFError: if a problem is encountered during import
    """

    # Open the SBDF file
    with open(sbdf_file, "rb") as file:
        # Read the file header
        version_major, version_minor = _FileHeader.read(file)
        if version_major != _FileHeader.Major_Version or version_minor != _FileHeader.Minor_Version:
            raise SBDFError(f"unsupported file version {version_major}.{version_minor}")

        # Read the table metadata
        tmeta = _TableMetadata.read(file)

        # Process table metadata
        table_metadata_dict = _import_table_metadata(tmeta)

        # Process column metadata
        pd_data, pd_dtypes, column_metadata_dict, column_names = _import_column_metadata(tmeta)

        # Read the table slices
        _import_table_slices(file, column_names, pd_data, tmeta)

        # Construct the pandas DataFrame and return the final results
        columns = []
        for col in column_names:
            columns.append(pd.Series(pd_data[col], dtype=pd_dtypes[col], name=col))
        dataframe = pd.concat(columns, axis=1)
        for col in column_names:
            dataframe[col].spotfire_column_metadata = column_metadata_dict[col]
        if gpd is not None and table_metadata_dict.get('MapChart.IsGeocodingTable'):
            dataframe = _data_frame_to_geo_data_frame(dataframe, table_metadata_dict)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dataframe.spotfire_table_metadata = table_metadata_dict
        return dataframe


def _import_table_metadata(tmeta: '_TableMetadata') -> typing.Dict[str, typing.Any]:
    table_metadata_dict = {}
    for i in range(tmeta.table_metadata.count()):
        table_metadata_dict[tmeta.table_metadata.names[i]] = tmeta.table_metadata.values[i].data
    return table_metadata_dict


def _import_column_metadata(tmeta: '_TableMetadata') -> typing.Tuple[typing.Dict[str, typing.List],
                                                                     typing.Dict[str, str],
                                                                     typing.Dict[str, typing.Dict[str, typing.Any]],
                                                                     typing.List[str]]:
    pd_data = {}
    pd_dtypes = {}
    column_metadata_dict = {}
    column_names = []
    for i in range(tmeta.column_count()):
        cmeta = tmeta.column_metadata[i]

        # get the column name
        cm_column_name = _ColumnMetadata.get_name(cmeta)
        column_names.append(cm_column_name)

        # add a new list to hold the column
        pd_data[cm_column_name] = []

        # get the pandas dtype for constructing this column
        pd_dtypes[cm_column_name] = _ColumnMetadata.get_type(cmeta).to_dtype_name()

        # get the remaining column metadata
        cm_dict = {}
        for j in range(cmeta.count()):
            if cmeta.names[j] in (_ColumnMetadata.Property_Name, _ColumnMetadata.Property_DataType):
                continue
            cm_dict[cmeta.names[j]] = cmeta.values[j].data
        column_metadata_dict[cm_column_name] = cm_dict

    return pd_data, pd_dtypes, column_metadata_dict, column_names


def _import_table_slices(file: typing.BinaryIO, column_names: typing.List[str],
                         pd_data: typing.Dict[str, typing.List], tmeta: '_TableMetadata') -> None:
    while True:
        tslice = _TableSlice.read(file, tmeta, None)
        if tslice is None:
            break
        for i in range(tslice.column_count()):
            cslice = tslice.columns[i]
            cs_values = cslice.values.get_values()
            cs_invalid_prop = cslice.get_property(_ColumnSlice.ValueProperty_IsInvalid)
            if cs_invalid_prop is None:
                cs_invalid = [False] * cs_values.get_count()
            else:
                cs_invalid = cs_invalid_prop.get_values().data
            for value, invalid in zip(cs_values.data, cs_invalid):
                pd_data[column_names[i]].append(None if invalid else value)


def export_data(obj: typing.Any, sbdf_file: typing.Union[str, bytes, int], default_column_name: str = "x") -> None:
    """Export data to an SBDF file.

    :param obj: the data object to export
    :param sbdf_file: the filename to export the data to
    :param default_column_name: the column name to use when exporting data objects without intrinsic names (such as
                                lists or scalar values)
    :raises SBDFError: if a problem is encountered during export
    """
    columns, column_names, column_types, table_metadata, column_metadata = _export_columnize_data(obj,
                                                                                                  default_column_name)

    # Open the SBDF file
    with open(sbdf_file, "wb") as file:
        # Write the file header
        _FileHeader.write(file)

        # Write the table and column metadata
        tmeta = _export_table_metadata(table_metadata)
        row_count = _export_column_metadata(columns, column_names, column_types, column_metadata, tmeta)
        tmeta.write(file)

        # Write out the table and column slices
        _export_table_slices(columns, column_names, column_types, file, row_count, tmeta)


def _export_columnize_data(obj: typing.Any, default_column_name: str) -> \
        typing.Tuple[typing.Dict[str, typing.List[typing.Any]],
                     typing.List[str],
                     typing.Dict[str, '_ValueTypeId'],
                     typing.Dict[str, typing.List[typing.Any]],
                     typing.Dict[str, typing.Dict[str, typing.List[typing.Any]]]
                     ]:
    # pylint: disable=too-many-branches,too-many-statements
    table_metadata = {}
    column_metadata = {}
    if isinstance(obj, pd.DataFrame):
        # Extract the table and column metadata from the data frame
        try:
            table_metadata = obj.spotfire_table_metadata
        except AttributeError:
            pass
        for col in obj.columns.tolist():
            try:
                col_meta = obj[col].spotfire_column_metadata
                column_metadata[col] = col_meta
            except AttributeError:
                column_metadata[col] = {}

        # Convert geopandas geodataframe to Spotfire's native geocoding format
        if gpd is not None and isinstance(obj, gpd.GeoDataFrame):
            obj = _geo_data_frame_to_data_frame(obj, table_metadata, column_metadata)

        if len({str(x) for x in obj.keys()}) != len(obj.columns):
            raise SBDFError("obj does not have unique column names")
        # columns = obj.to_dict("list")
        columns = obj
        column_names = obj.columns.tolist()
        column_types = {str(k): _ValueTypeId.infer_from_dtype(v, f"column '{str(k)}'") for (k, v) in obj.iteritems()}
    elif isinstance(obj, pd.Series):
        # Handle series as columnar data
        series_name = default_column_name if obj.name is None else obj.name
        series_description = "series" if obj.name is None else f"series '{obj.name}'"

        # Extract the column metadata from the series
        try:
            column_metadata = {series_name: obj.spotfire_column_metadata}
        except AttributeError:
            pass

        columns = {series_name: obj.tolist()}
        column_names = [series_name]
        column_types = {series_name: _ValueTypeId.infer_from_dtype(obj, series_description)}
    elif isinstance(obj, dict):
        # Handle dicts of lists as tabular data
        if not all(isinstance(x, list) for x in obj.values()):
            raise SBDFError("obj is not a dict of lists")
        if len({str(x) for x in obj.keys()}) != len(obj):
            raise SBDFError("obj does not have unique column names")
        column_metadata = {col: {} for col in obj.keys()}
        columns = obj
        column_names = obj.keys()
        column_types = {str(k): _ValueTypeId.infer_from_type(v, f"column '{str(k)}'") for (k, v) in obj.items()}
    elif isinstance(obj, (str, bytes, bytearray)):
        # Handle strings and bytes as scalar data
        column_metadata[default_column_name] = {}
        columns = {default_column_name: [obj]}
        column_names = [default_column_name]
        column_types = {default_column_name: _ValueTypeId.infer_from_type([obj], "value")}
    elif isinstance(obj, collections.abc.Iterable):
        # Handle all iterable items as columnar data
        column_metadata[default_column_name] = {}
        columns = {default_column_name: list(obj)}
        column_names = [default_column_name]
        column_types = {default_column_name: _ValueTypeId.infer_from_type(list(obj), "list")}
    else:
        # Handle various image formats
        if matplotlib is not None and isinstance(obj, matplotlib.figure.Figure):
            obj = _pyplot_to_binary(obj)
        elif seaborn is not None and isinstance(obj, seaborn.axisgrid.Grid):
            obj = _seaborn_plot_to_binary(obj)
        elif PIL is not None and isinstance(obj, PIL.Image.Image):
            obj = _pil_image_to_binary(obj)

        # If all else fails, treat this as scalar data
        column_metadata[default_column_name] = {}
        columns = {default_column_name: [obj]}
        column_names = [default_column_name]
        column_types = {default_column_name: _ValueTypeId.infer_from_type([obj], "value")}

    return columns, column_names, column_types, table_metadata, column_metadata


def _export_table_metadata(table_metadata: typing.Dict[str, typing.Any]) -> '_TableMetadata':
    metadata = _Metadata()
    if isinstance(table_metadata, dict):
        for key, val in table_metadata.items():
            obj_val = val if isinstance(val, list) else [val]
            obj_valuetype = _ValueTypeId.infer_from_type(obj_val, "table metadata")
            obj = _SbdfObject(obj_valuetype, obj_val)
            metadata.add(key, obj)
    tmeta = _TableMetadata(metadata)
    return tmeta


def _export_column_metadata(columns: typing.Dict[str, typing.List], column_names: typing.List[str],
                            column_types: typing.Dict[str, '_ValueTypeId'],
                            column_metadata: typing.Dict[str, typing.Dict[str, typing.Any]],
                            tmeta: '_TableMetadata') -> int:
    row_count = None
    for colname in column_names:
        metadata = _Metadata()
        if isinstance(column_metadata, dict):
            colmeta = column_metadata.get(colname, {})
            if not isinstance(colmeta, dict):
                raise SBDFError("column_metadata is not a dict of dicts")
            for key, val in colmeta.items():
                obj_val = val if isinstance(val, list) else [val]
                obj_valuetype = _ValueTypeId.infer_from_type(obj_val, "column metadata")
                obj = _SbdfObject(obj_valuetype, obj_val)
                metadata.add(key, obj)
        if row_count is None:
            row_count = len(columns[colname])
        else:
            if row_count != len(columns[colname]):
                raise SBDFError(f"column '{colname}' has inconsistent column length")
        _ColumnMetadata.set_values(metadata, colname, column_types.get(str(colname)))
        tmeta.add(metadata)
    return row_count


def _export_table_slices(columns: typing.Dict[str, typing.List], column_names: typing.List[str],
                         column_types: typing.Dict[str, '_ValueTypeId'], file: typing.BinaryIO,
                         row_count: int, tmeta: '_TableMetadata') -> None:
    # max_rows_per_slice = max(10, 100000 // max(1, len(column_names)))
    max_rows_per_slice = 50000
    row_offset = 0
    while row_offset < row_count:
        slice_row_count = min(max_rows_per_slice, row_count - row_offset)
        tslice = _TableSlice(tmeta)
        for colname in column_names:
            if isinstance(columns, pd.DataFrame):
                dataslice = columns.loc[row_offset:row_offset + slice_row_count, colname]
            else:
                dataslice = columns[colname][row_offset:row_offset + slice_row_count]
            obj = _SbdfObject(column_types.get(str(colname)), dataslice)
            cslice = _ColumnSlice(_ValueArray(_ValueArrayEncoding.PLAIN_ARRAY, obj))

            if isinstance(dataslice, pd.Series):
                invalid = dataslice.isna()
                if invalid.sum() > 0:
                    obj_vt = _ValueType(column_types.get(str(colname)))
                    dataslice = dataslice.fillna(obj_vt.missing_value())
                    obj_empty = _SbdfObject(_ValueTypeId.BOOL, invalid.tolist())
                    va_empty = _ValueArray(_ValueArrayEncoding.BIT_ARRAY, obj_empty)
                    cslice.add_property(_ColumnSlice.ValueProperty_IsInvalid, va_empty)
            else:
                invalid = [pd.isnull(x) for x in obj.data]
                if any(invalid):
                    obj_vt = _ValueType(column_types.get(str(colname)))
                    obj.data = [obj_vt.missing_value() if missing else val for val, missing in zip(obj.data, invalid)]
                    obj_empty = _SbdfObject(_ValueTypeId.BOOL, invalid)
                    va_empty = _ValueArray(_ValueArrayEncoding.BIT_ARRAY, obj_empty)
                    cslice.add_property(_ColumnSlice.ValueProperty_IsInvalid, va_empty)
            tslice.add(cslice)
        tslice.write(file)
        row_offset += slice_row_count
    _TableSlice.write_end(file)


# Exceptions

class SBDFError(Exception):
    """An exception that is raised to indicate a problem during import or export of SBDF files."""


# File Headers

class _FileHeader:
    Major_Version = 1
    Minor_Version = 0
    Version_String = "1.0"

    @staticmethod
    def write(file: typing.BinaryIO) -> None:
        """writes the current sbdf fileheader to file"""
        _section_write(file, _SectionTypeId.FILEHEADER)
        _write_int8(file, _FileHeader.Major_Version)
        _write_int8(file, _FileHeader.Minor_Version)

    @staticmethod
    def read(file: typing.BinaryIO) -> typing.Tuple[int, int]:
        """reads the sbdf fileheader from file"""
        _section_expect(file, _SectionTypeId.FILEHEADER)
        major = _read_int8(file)
        minor = _read_int8(file)
        return major, minor


# Column Slices

class _ColumnSlice:
    ValueProperty_IsInvalid = "IsInvalid"
    ValueProperty_ErrorCode = "ErrorCode"
    ValueProperty_ReplacedValue = "HasReplacedValue"

    def __init__(self, values: '_ValueArray') -> None:
        """creates a column slice and stores a reference to the valuearray in it"""
        self.values = values
        self.property_names = []
        self.property_values = []

    def __repr__(self) -> str:
        return f"<{_utils.type_name(type(self))} object: {self.values!r}>"

    def add_property(self, name: str, values: '_ValueArray') -> None:
        """stores a named value property reference in the given column slice"""
        if name in self.property_names:
            raise SBDFError("the property with the given name already exists")
        self.property_names.append(name)
        self.property_values.append(values)

    def get_property(self, name: str) -> typing.Optional['_ValueArray']:
        """gets a value property reference with the given name"""
        if name in self.property_names:
            index = self.property_names.index(name)
            return self.property_values[index]
        return None

    def get_property_count(self) -> int:
        """gets the number of value properties in the column slice"""
        return len(self.property_names)

    def get_row_count(self) -> int:
        """gets the number of rows of the values in the column slice"""
        return self.values.row_count()

    def write(self, file: typing.BinaryIO) -> None:
        """writes a value array to file"""
        _section_write(file, _SectionTypeId.COLUMNSLICE)
        self.values.write(file)
        _write_int32(file, self.get_property_count())
        for i in range(self.get_property_count()):
            _write_string(file, self.property_names[i])
            self.property_values[i].write(file)

    @classmethod
    def read(cls, file: typing.BinaryIO) -> '_ColumnSlice':
        """reads a value array from file"""
        _section_expect(file, _SectionTypeId.COLUMNSLICE)
        values = _ValueArray.read(file)
        cslice = cls(values)
        val = _read_int32(file)
        for _ in range(val):
            name = _read_string(file)
            prop = _ValueArray.read(file)
            cslice.add_property(name, prop)
        return cslice

    @classmethod
    def skip(cls, file: typing.BinaryIO) -> None:
        """skips a value array in the file"""
        raise NotImplementedError  # sbdf_cs_skip


# Table Slices

class _TableSlice:
    def __init__(self, table_metadata: '_TableMetadata') -> None:
        """creates a table slice, storing a reference to the table metadata"""
        self.table_metadata = table_metadata
        self.columns = []

    def __repr__(self) -> str:
        return f"<{_utils.type_name(type(self))} object: {self.columns!r}>"

    def column_count(self) -> int:
        """get the number of columns in the table slice"""
        return len(self.columns)

    def add(self, column_slice: _ColumnSlice) -> None:
        """adds a column slice reference to the table slice"""
        self.columns.append(column_slice)

    def write(self, file: typing.BinaryIO) -> None:
        """writes a table slice to file"""
        _section_write(file, _SectionTypeId.TABLESLICE)
        no_columns = self.column_count()
        _write_int32(file, no_columns)
        for i in range(no_columns):
            self.columns[i].write(file)

    @staticmethod
    def write_end(file: typing.BinaryIO) -> None:
        """writes the end-of-table marker to the file"""
        _section_write(file, _SectionTypeId.TABLEEND)

    @classmethod
    def read(cls, file: typing.BinaryIO, table_metadata: '_TableMetadata',
             subset: typing.Optional[typing.List[bool]]) -> typing.Optional['_TableSlice']:
        """reads a table slice from file. returns None when the end of the table is reached"""
        val = _section_read(file)
        if val == _SectionTypeId.TABLEEND:
            return None
        if val != _SectionTypeId.TABLESLICE:
            raise SBDFError("unexpected section id")
        column_count = _read_int32(file)
        if column_count < 0:
            raise SBDFError("the number of elements is incorrect")
        if column_count != table_metadata.column_count():
            raise SBDFError("the number of the columnslice doesn't match the number of the columns of the metadata")
        tslice = cls(table_metadata)
        for i in range(column_count):
            if subset is None or subset[i]:
                tslice.add(_ColumnSlice.read(file))
            else:
                _ColumnSlice.skip(file)
        return tslice

    @classmethod
    def skip(cls, file: typing.BinaryIO, table_metadata: '_TableMetadata') -> None:
        """skips a table slice in file"""
        subset = []
        for _ in range(table_metadata.column_count()):
            subset.append(False)
        cls.read(file, table_metadata, subset)


# Column Metadata

class _ColumnMetadata:
    Property_Name = "Name"
    Property_DataType = "DataType"

    @staticmethod
    def set_values(metadata: '_Metadata', column_name: str, data_type) -> None:
        """sets the column metadata values name and data type for the previously allocated metadata head"""
        metadata.add_str(_ColumnMetadata.Property_Name, column_name)
        obj = _ValueType(data_type).as_sbdfobject()
        metadata.add(_ColumnMetadata.Property_DataType, obj)

    @staticmethod
    def get_name(metadata: '_Metadata') -> str:
        """gets the name of the column metadata"""
        name = metadata.get(_ColumnMetadata.Property_Name)
        if name.valuetype != _ValueTypeId.STRING:
            raise SBDFError("the metadata is incorrect")
        return name.data[0]

    @staticmethod
    def get_type(metadata: '_Metadata') -> '_ValueTypeId':
        """gets the value type of the column metadata"""
        obj = metadata.get(_ColumnMetadata.Property_DataType)
        if obj.valuetype != _ValueTypeId.BINARY or obj.get_count() != 1:
            raise SBDFError("the metadata is incorrect")
        return _ValueTypeId(obj.data[0][0])


# Table Metadata

class _TableMetadata:
    def __init__(self, table_metadata: '_Metadata') -> None:
        """creates the table metadata, storing a copy the given table information"""
        self.table_metadata = table_metadata
        self.table_metadata.set_immutable()
        self.column_metadata = []

    def __repr__(self) -> str:
        return f"<{_utils.type_name(type(self))} object: {self.table_metadata!r} {self.column_metadata!r}>"

    def column_count(self) -> int:
        """return the number of columns in this table"""
        return len(self.column_metadata)

    def add(self, column_metadata: '_Metadata') -> None:
        """adds column metadata to the table metadata"""
        self.column_metadata.append(column_metadata)

    def write(self, file: typing.BinaryIO) -> None:
        """writes table metadata to file"""
        _section_write(file, _SectionTypeId.TABLEMETADATA)
        _write_int32(file, self.table_metadata.count())
        for i in range(self.table_metadata.count()):
            _write_string(file, self.table_metadata.names[i])
            _write_int8(file, self.table_metadata.values[i].valuetype)
            _write_optional_value(file, self.table_metadata.values[i])
            _write_optional_value(file, self.table_metadata.default_values[i])
        _write_int32(file, self.column_count())
        # fold duplicate values
        cm_default = {}
        cm_types = {}
        for cmeta in self.column_metadata:
            for i in range(cmeta.count()):
                cm_name = cmeta.names[i]
                if cm_name in cm_default and cm_default[cm_name] != cmeta.default_values[i]:
                    raise SBDFError("the metadata is incorrect")
                cm_default[cm_name] = cmeta.default_values[i]
                if cmeta.values[i] is not None:
                    cm_type = cmeta.values[i].valuetype
                else:
                    cm_type = cmeta.default_values[i].valuetype
                if cm_name in cm_types and cm_types[cm_name] != cm_type:
                    raise SBDFError("the metadata is incorrect")
                cm_types[cm_name] = cm_type
        _write_int32(file, len(cm_default))
        # write names, data types, and default values
        for i in sorted(cm_default):
            _write_string(file, i)
            _ValueType(cm_types[i]).write(file)
            _write_optional_value(file, cm_default[i])
        # write column values
        for cmeta in self.column_metadata:
            for i in sorted(cm_default):
                val = cmeta.get(i)
                _write_optional_value(file, val)

    @classmethod
    def read(cls, file: typing.BinaryIO) -> '_TableMetadata':
        """reads table metadata from file"""
        _section_expect(file, _SectionTypeId.TABLEMETADATA)
        metadata_count = _read_int32(file)
        if metadata_count < 0:
            raise SBDFError("the number of elements is incorrect")
        metadata = _Metadata()
        for _ in range(metadata_count):
            name = _read_string(file)
            valtype = _ValueType.read(file)
            value_present = _read_int8(file)
            value = _SbdfObject.read(file, valtype) if value_present else None
            value_present = _read_int8(file)
            default_value = _SbdfObject.read(file, valtype) if value_present else None
            metadata.add(name, value, default_value)
        tmeta = _TableMetadata(metadata)

        column_count = _read_int32(file)
        metadata_count = _read_int32(file)
        md_name = []
        md_type = []
        md_default = []
        for i in range(metadata_count):
            md_name.append(_read_string(file))
            md_type.append(_ValueType.read(file))
            value_present = _read_int8(file)
            md_default.append(_SbdfObject.read(file, md_type[i]) if value_present else None)
        for i in range(column_count):
            metadata = _Metadata()
            for j in range(metadata_count):
                value_present = _read_int8(file)
                if value_present:
                    value = _SbdfObject.read(file, md_type[j])
                    metadata.add(md_name[j], value, md_default[j])
            tmeta.add(metadata)
        return tmeta


# Metadata

class _Metadata:
    def __init__(self) -> None:
        """creates an empty metadata structure"""
        self.modifiable = True
        self.names = []
        self.values = []
        self.default_values = []

    def __repr__(self) -> str:
        return f"<{_utils.type_name(type(self))} object: {self.names!r} -> {self.values!r}>"

    def add_str(self, name: str, value: str, default_value: str = None) -> None:
        """adds a named string metadata value and default value to out"""
        val = _SbdfObject(_ValueTypeId.STRING, [str(value)])
        if default_value is not None:
            default = _SbdfObject(_ValueTypeId.STRING, [str(default_value)])
        else:
            default = None
        self.add(name, val, default)

    def add_int(self, name: str, value: int, default_value: int = None) -> None:
        """adds a named integer metadata value and default value to out"""
        val = _SbdfObject(_ValueTypeId.INT, [value])
        if default_value is not None:
            default = _SbdfObject(_ValueTypeId.INT, [default_value])
        else:
            default = None
        self.add(name, val, default)

    def add(self, name: str, value: '_SbdfObject', default_value: '_SbdfObject' = None) -> None:
        """adds a named metadata value and default value to out"""
        if not self.modifiable:
            raise SBDFError("the metadata is readonly and may not be modified")
        if default_value is not None and value.valuetype != default_value.valuetype:
            raise SBDFError("the valuetypes of the arguments must be equal")
        if name in self.names:
            raise SBDFError("the metadata with the given name already exists")
        self.names.append(name)
        self.values.append(value)
        self.default_values.append(default_value)

    def remove(self, name: str) -> None:
        """removes the named metadata value from out"""
        if not self.modifiable:
            raise SBDFError("the metadata is readonly and may not be modified")
        if name in self.names:
            index = self.names.index(name)
            del self.names[index]
            del self.values[index]
            del self.default_values[index]

    def get(self, name: str) -> typing.Optional['_SbdfObject']:
        """gets a copy of the named metadata value"""
        if name in self.names:
            index = self.names.index(name)
            return self.values[index]
        return None

    def get_default(self, name: str) -> typing.Optional['_SbdfObject']:
        """gets a copy of the named default metadata value"""
        if name in self.names:
            index = self.names.index(name)
            return self.default_values[index]
        return None

    def count(self) -> int:
        """returns the number of metadata entries pointed to by head"""
        return len(self.names)

    def exists(self, name: str) -> bool:
        """returns True if the named metadata exists. False is returned if the metadata doesn't exist"""
        return name in self.names

    def set_immutable(self) -> None:
        """sets the metadata immutable so that it may not be modified by subsequent operations"""
        self.modifiable = False


# Objects

class _SbdfObject:
    def __init__(self, valuetype: '_ValueTypeId', data: typing.List) -> None:
        self.valuetype = valuetype
        self.data = data

    def __repr__(self) -> str:
        return f"<{_utils.type_name(type(self))} object ({self.valuetype!r}): {self.data!r}>"

    def get_count(self) -> int:
        """get the number of items in the object"""
        return len(self.data)

    def write_array(self, file: typing.BinaryIO) -> None:
        """writes the array information to the specified file. valuetype information is not written"""
        count = len(self.data)
        _write_int32(file, count)
        self._write_n(file, count, True)

    def write(self, file: typing.BinaryIO) -> None:
        """writes the object to the specified file. valuetype information is not written"""
        self._write_n(file, 1, False)

    # pylint: disable=too-many-branches
    def _write_n(self, file: typing.BinaryIO, n: int, packed: bool) -> None:
        valtype = _ValueType(self.valuetype)
        if valtype.is_array():
            byte_size = 0
            # packed: no need to write 7bit packed int32
            if packed:
                if isinstance(self.data, pd.Series) and self.valuetype is not _ValueTypeId.BINARY:
                    barr = self.data.values.astype('U')
                    _write_int32(file, sum(_get_7bit_packed_length(len(s.encode("utf-8"))) +
                                            len(s.encode("utf-8")) for s in barr))
                    for bstr in barr:
                        bstr = bstr.encode("utf-8")
                        _write_7bit_packed_int32(file, len(bstr))
                        if len(bstr):
                            _write_bytes(file, bstr)
                else:
                    saved_bytes = []
                    for i in range(n):
                        saved_bytes.append(valtype.to_bytes(self.data[i]))
                        length = len(saved_bytes[i])
                        byte_size += _get_7bit_packed_length(length) + length
                    _write_int32(file, byte_size)
                    for i in range(n):
                        length = len(saved_bytes[i])
                        _write_7bit_packed_int32(file, length)
                        if length:
                            _write_bytes(file, saved_bytes[i])
            else:
                if isinstance(self.data, pd.Series):
                    barr = self.data.values.astype('S')
                    for bstr in barr:
                        _write_7bit_packed_int32(file, len(bstr))
                        if len(bstr):
                            _write_bytes(file, bstr)
                else:
                    for i in range(n):
                        valtype_bytes = valtype.to_bytes(self.data[i])
                        length = len(valtype_bytes)
                        _write_int32(file, length)
                        if length:
                            _write_bytes(file, valtype_bytes)
        else:
            size = valtype.get_packed_size()
            if size is None:
                raise SBDFError("unknown typeid")

            if isinstance(self.data, pd.Series) and isinstance(self.data.values, np.ndarray):
                _write_bytes(file, self.data.values.tobytes())
            else:
                for i in range(n):
                    valtype_bytes = valtype.to_bytes(self.data[i])
                    _write_bytes(file, valtype_bytes)

    @classmethod
    def read_array(cls, file: typing.BinaryIO, valuetype: '_ValueType') -> '_SbdfObject':
        """reads an array object with the given value type from the specified file"""
        count = _read_int32(file)
        return cls._read_n(file, count, valuetype, True)

    @classmethod
    def read(cls, file: typing.BinaryIO, valuetype: '_ValueType') -> '_SbdfObject':
        """reads an object with the given valuetype from the file."""
        return cls._read_n(file, 1, valuetype, False)

    @classmethod
    def _read_n(cls, file: typing.BinaryIO, n: int, valuetype: '_ValueType', packed: bool) -> '_SbdfObject':
        data = []
        if valuetype.is_array():
            # read byte size and ignore it
            if packed:
                _read_int32(file)
            for _ in range(n):
                if packed:
                    length = _read_7bit_packed_int32(file)
                else:
                    length = _read_int32(file)
                if length < 0:
                    raise SBDFError("the number of elements is incorrect")
                dest = _read_bytes(file, length)
                data.append(valuetype.to_python(dest))
        else:
            size = valuetype.get_packed_size()
            if size is None:
                raise SBDFError("unknown typeid")
            for _ in range(n):
                dest = _read_bytes(file, size)
                data.append(valuetype.to_python(dest))
        return cls(valuetype.type_id, data)

    @classmethod
    def skip_array(cls, file: typing.BinaryIO, valuetype: '_ValueType') -> None:
        """skips an array with the given valuetype"""
        raise NotImplementedError  # sbdf_obj_skip_arr

    @classmethod
    def skip(cls, file: typing.BinaryIO, valuetype: '_ValueType') -> None:
        """skips an object with the given valuetype"""
        raise NotImplementedError  # sbdf_obj_skip


# Value arrays

class _ValueArrayEncoding(enum.IntEnum):
    PLAIN_ARRAY = 0x1
    RUN_LENGTH = 0x2
    BIT_ARRAY = 0x3


class _ValueArray:
    def __init__(self, array_encoding: _ValueArrayEncoding, array: typing.Optional[_SbdfObject]) -> None:
        """creates a value array from the specified values"""
        self.encoding = _ValueArrayEncoding(array_encoding)
        self.val1 = None
        self.obj1 = None
        self.obj2 = None
        self.valuetype = None
        if array is None:
            pass
        elif array_encoding == _ValueArrayEncoding.PLAIN_ARRAY:
            self._create_plain(array)
        elif array_encoding == _ValueArrayEncoding.RUN_LENGTH:
            self._create_rle(array)
        elif array_encoding == _ValueArrayEncoding.BIT_ARRAY:
            self._create_bit(array)
        else:
            raise SBDFError("unknown valuearray encoding")

    def _create_plain(self, array: _SbdfObject) -> None:
        self.valuetype = array.valuetype
        self.obj1 = array

    def _create_rle(self, array: _SbdfObject) -> None:
        raise NotImplementedError  # sbdf_va_create_rle

    def _create_bit(self, array: _SbdfObject) -> None:
        self.valuetype = _ValueTypeId.BOOL
        self.val1 = array.get_count()
        bits = bitstring.BitArray(array.data)
        while bits.len % 8 != 0:
            bits.append('0b0')
        self.obj1 = _SbdfObject(_ValueTypeId.BINARY, [bits.bytes])

    def __repr__(self) -> str:
        if self.encoding == _ValueArrayEncoding.PLAIN_ARRAY:
            arr = self.obj1
        elif self.encoding == _ValueArrayEncoding.RUN_LENGTH:
            arr = "..."
        elif self.encoding == _ValueArrayEncoding.BIT_ARRAY:
            arr = self.obj1.data[0]
        else:
            arr = "unknown encoding"
        return f"<{_utils.type_name(type(self))} object ({self.encoding!r}): {arr!r}>"

    def get_values(self) -> _SbdfObject:
        """extracts the values from the array"""
        if self.encoding == _ValueArrayEncoding.PLAIN_ARRAY:
            return self.obj1
        if self.encoding == _ValueArrayEncoding.RUN_LENGTH:
            return self._get_rle()
        if self.encoding == _ValueArrayEncoding.BIT_ARRAY:
            return self._get_bit()
        raise SBDFError("unknown valuearray encoding")

    def _get_rle(self) -> _SbdfObject:
        raise NotImplementedError  # sbdf_get_rle_values

    def _get_bit(self) -> _SbdfObject:
        obj = _SbdfObject(_ValueTypeId.BOOL, [])
        bits = bitstring.BitArray(bytes=self.obj1.data[0], length=self.val1)
        for i in bits:
            obj.data.append(i)
        return obj

    def row_count(self) -> int:
        """returns the number of rows stored in the value array"""
        if self.encoding == _ValueArrayEncoding.PLAIN_ARRAY:
            return self.obj1.get_count()
        if self.encoding == _ValueArrayEncoding.RUN_LENGTH:
            return self.val1
        if self.encoding == _ValueArrayEncoding.BIT_ARRAY:
            return self.val1
        raise SBDFError("unknown valuearray encoding")

    def write(self, file: typing.BinaryIO) -> None:
        """writes the value array to the current file position"""
        _write_int8(file, self.encoding)
        _ValueType(self.valuetype).write(file)
        if self.encoding == _ValueArrayEncoding.PLAIN_ARRAY:
            self.obj1.write_array(file)
        elif self.encoding == _ValueArrayEncoding.RUN_LENGTH:
            _write_int32(file, self.val1)
            self.obj1.write_array(file)
            self.obj2.write_array(file)
        elif self.encoding == _ValueArrayEncoding.BIT_ARRAY:
            _write_int32(file, self.val1)
            _write_bytes(file, self.obj1.data[0])
        else:
            raise SBDFError("unknown valuearray encoding")

    @classmethod
    def read(cls, file: typing.BinaryIO) -> '_ValueArray':
        """reads the value array from the current file position"""
        encoding = _read_int8(file)
        valtype = _ValueType.read(file)
        handle = cls(_ValueArrayEncoding(encoding), None)
        handle.valuetype = valtype
        if encoding == _ValueArrayEncoding.PLAIN_ARRAY:
            handle.obj1 = _SbdfObject.read_array(file, valtype)
        elif encoding == _ValueArrayEncoding.RUN_LENGTH:
            handle.val1 = _read_int32(file)
            handle.obj1 = _SbdfObject.read_array(file, _ValueType(_ValueTypeId.INTERNAL_BYTE))
            handle.obj2 = _SbdfObject.read_array(file, valtype)
        elif encoding == _ValueArrayEncoding.BIT_ARRAY:
            val = _read_int32(file)
            handle.val1 = val
            packed_size = val // 8 + (1 if val % 8 else 0)
            bits = _read_bytes(file, packed_size)
            handle.obj1 = _SbdfObject(_ValueTypeId.BINARY, [bits])
        else:
            raise SBDFError("unknown valuearray encoding")
        return handle

    @classmethod
    def skip(cls, file: typing.BinaryIO) -> None:
        """skips the value array at the current file position"""
        encoding = _read_int8(file)
        valtype = _ValueType.read(file)
        if encoding == _ValueArrayEncoding.PLAIN_ARRAY:
            _SbdfObject.skip_array(file, valtype)
        elif encoding == _ValueArrayEncoding.RUN_LENGTH:
            _SbdfObject.skip_array(file, _ValueType(_ValueTypeId.INTERNAL_BYTE))
            _SbdfObject.skip_array(file, valtype)
        elif encoding == _ValueArrayEncoding.BIT_ARRAY:
            val = _read_int32(file)
            packed_size = val // 8 + (1 if val % 8 else 0)
            file.seek(packed_size, 1)
        else:
            raise SBDFError("unknown valuearray encoding")


# Value types

class _ValueTypeId(enum.IntEnum):
    UNKNOWN = 0x00
    BOOL = 0x01      # C type is char
    INT = 0x02       # C type is 32-bit int
    LONG = 0x03      # C type is 64-bit int
    FLOAT = 0x04     # C type is float
    DOUBLE = 0x05    # C type is double
    DATETIME = 0x06  # C representation is milliseconds since 01/01/01, 00:00:00, stored in a 64-bit int
    DATE = 0x07      # C representation is milliseconds since 01/01/01, 00:00:00, stored in a 64-bit int
    TIME = 0x08      # C representation is milliseconds since 01/01/01, 00:00:00, stored in a 64-bit int
    TIMESPAN = 0x09  # C representation is milliseconds, stored in a 64-bit int
    STRING = 0x0a    # C representation is char-ptr
    BINARY = 0x0c    # C representation is void-ptr
    DECIMAL = 0x0d   # C representation is IEEE754 decimal128 Binary Integer Decimals
    INTERNAL_BYTE = 0xfe

    def to_typename_string(self) -> str:
        """convert this valuetype id to the type name used by Spotfire"""
        return {
            _ValueTypeId.BOOL: "Boolean",
            _ValueTypeId.INT: "Integer",
            _ValueTypeId.LONG: "LongInteger",
            _ValueTypeId.FLOAT: "SingleReal",
            _ValueTypeId.DOUBLE: "Real",
            _ValueTypeId.DATETIME: "DateTime",
            _ValueTypeId.DATE: "Date",
            _ValueTypeId.TIME: "Time",
            _ValueTypeId.TIMESPAN: "TimeSpan",
            _ValueTypeId.STRING: "String",
            _ValueTypeId.BINARY: "Binary",
            _ValueTypeId.DECIMAL: "Currency"
        }.get(self, "unknown")

    def to_dtype_name(self) -> str:
        """convert this valuetype id to the dtype name used by Pandas"""
        return {
            _ValueTypeId.INT: "Int32",
            _ValueTypeId.LONG: "Int64",
            _ValueTypeId.FLOAT: "float32",
            _ValueTypeId.DOUBLE: "float64"
        }.get(self, "object")

    @staticmethod
    def infer_from_type(values, value_description: str) -> '_ValueTypeId':
        """determine the proper valuetype id from the Python types in a column"""
        # Remove any None (or other none-ish things) from values
        if isinstance(values, pd.Series):
            vals = values.dropna().tolist()
        else:
            vals = [x for x in values if not pd.isnull(x)]
        # Check if any values remain
        if not vals:
            raise SBDFError(f"cannot determine type for {value_description}; all values are missing")
        # Check to make sure only one type remains
        vals_type = type(vals[0])
        if not all(isinstance(i, vals_type) for i in vals):
            raise SBDFError(f"types in {value_description} do not match")
        # Determine the right type id
        typeid = {
            bool: _ValueTypeId.BOOL,
            np.int32: _ValueTypeId.INT,
            int: _ValueTypeId.LONG,
            np.int64: _ValueTypeId.LONG,
            np.float32: _ValueTypeId.FLOAT,
            float: _ValueTypeId.DOUBLE,
            np.float64: _ValueTypeId.DOUBLE,
            datetime.datetime: _ValueTypeId.DATETIME,
            pd.Timestamp: _ValueTypeId.DATETIME,
            datetime.date: _ValueTypeId.DATE,
            datetime.time: _ValueTypeId.TIME,
            datetime.timedelta: _ValueTypeId.TIMESPAN,
            pd.Timedelta: _ValueTypeId.TIMESPAN,
            str: _ValueTypeId.STRING,
            bytes: _ValueTypeId.BINARY,
            decimal.Decimal: _ValueTypeId.DECIMAL,
        }.get(vals_type, None)
        if typeid is None:
            raise SBDFError(f"unknown type '{_utils.type_name(vals_type)}' in {value_description}")
        return typeid

    @staticmethod
    def infer_from_dtype(series: pd.Series, series_description: str) -> '_ValueTypeId':
        """determine the proper valuetype id from the Pandas dtype of a series"""
        dtype = series.dtype.name
        if dtype == "object":
            return _ValueTypeId.infer_from_type(series, series_description)
        if dtype == "category":
            return _ValueTypeId.infer_from_dtype(series.astype(series.cat.categories.dtype), series_description)
        typeid = {
            "bool": _ValueTypeId.BOOL,
            "int32": _ValueTypeId.INT,
            "Int32": _ValueTypeId.INT,
            "int64": _ValueTypeId.LONG,
            "Int64": _ValueTypeId.LONG,
            "float32": _ValueTypeId.FLOAT,
            "float64": _ValueTypeId.DOUBLE,
            "datetime64[ns]": _ValueTypeId.DATETIME,
            "timedelta64[ns]": _ValueTypeId.TIMESPAN,
            "string": _ValueTypeId.STRING,
        }.get(dtype, None)
        if typeid is None:
            raise SBDFError(f"unknown dtype '{dtype}' in {series_description}")
        return typeid


class _ValueType:
    def __init__(self, type_id: int) -> None:
        self.type_id = _ValueTypeId(type_id)

    def __repr__(self) -> str:
        return str(self.type_id)

    def __cmp__(self, other: '_ValueType') -> int:
        return self.type_id - other.type_id

    def write(self, file: typing.BinaryIO) -> None:
        """writes a valuetype to the current file position"""
        _write_int8(file, self.type_id)

    @classmethod
    def read(cls, file: typing.BinaryIO) -> '_ValueType':
        """reads a valuetype from the current file position"""
        return cls(_read_int8(file))

    def is_array(self) -> bool:
        """determines if this valuetype is an array type index"""
        return self.type_id in (_ValueTypeId.STRING, _ValueTypeId.BINARY)

    def get_packed_size(self) -> int:
        """returns the packed byte size (on disk) of a valuetype"""
        return {
            _ValueTypeId.BOOL: 1,
            _ValueTypeId.INT: 4,
            _ValueTypeId.LONG: 8,
            _ValueTypeId.FLOAT: 4,
            _ValueTypeId.DOUBLE: 8,
            _ValueTypeId.DATETIME: 8,
            _ValueTypeId.DATE: 8,
            _ValueTypeId.TIME: 8,
            _ValueTypeId.TIMESPAN: 8,
            _ValueTypeId.STRING: 0,  # size is dynamic
            _ValueTypeId.BINARY: 0,  # size is dynamic
            _ValueTypeId.DECIMAL: 16
        }.get(self.type_id, None)

    _DATETIME_EPOCH = datetime.datetime(1, 1, 1)
    _DECIMAL_EXPONENT_BIAS = 12320

    @staticmethod
    def _to_python_bool(data: bytes) -> bool:
        return struct.unpack("?", data)[0]

    @staticmethod
    def _to_python_int(data: bytes) -> int:
        return struct.unpack("<i", data)[0]

    @staticmethod
    def _to_python_long(data: bytes) -> int:
        return struct.unpack("<q", data)[0]

    @staticmethod
    def _to_python_float(data: bytes) -> float:
        return struct.unpack("<f", data)[0]

    @staticmethod
    def _to_python_double(data: bytes) -> float:
        return struct.unpack("<d", data)[0]

    @staticmethod
    def _to_python_datetime(data: bytes) -> datetime.datetime:
        timestamp = struct.unpack("<q", data)[0]
        return _ValueType._DATETIME_EPOCH + datetime.timedelta(milliseconds=timestamp)

    @staticmethod
    def _to_python_date(data: bytes) -> datetime.date:
        timestamp = struct.unpack("<q", data)[0]
        date = _ValueType._DATETIME_EPOCH + datetime.timedelta(milliseconds=timestamp)
        return date.date()

    @staticmethod
    def _to_python_time(data: bytes) -> datetime.time:
        timestamp = struct.unpack("<q", data)[0]
        date = _ValueType._DATETIME_EPOCH + datetime.timedelta(milliseconds=timestamp)
        return date.timetz()

    @staticmethod
    def _to_python_timespan(data: bytes) -> datetime.timedelta:
        timespan = struct.unpack("<q", data)[0]
        return datetime.timedelta(milliseconds=timespan)

    @staticmethod
    def _to_python_string(data: bytes) -> str:
        return data.decode("utf-8")

    @staticmethod
    def _to_python_binary(data: bytes) -> bytes:
        return data

    @staticmethod
    def _to_python_decimal(data: bytes) -> decimal.Decimal:
        bits = bitstring.BitArray(bytes=data)
        # pylint: disable=unbalanced-tuple-unpacking
        coefficient, biased_exponent_bits_high, sign_bit, biased_exponent_bits_low = \
            bits.unpack('uintle:96,pad:17,bits:7,bool,bits:7')
        # un-bias the exponent
        biased_exponent_bits = bitstring.BitArray('0b00')
        biased_exponent_bits.append(biased_exponent_bits_high)
        biased_exponent_bits.append(biased_exponent_bits_low)
        exponent = biased_exponent_bits.uintle - _ValueType._DECIMAL_EXPONENT_BIAS
        # break up the coefficient into its digits
        digits = []
        while coefficient != 0:
            digits.insert(0, coefficient % 10)
            coefficient //= 10
        # construct the decimal value
        return decimal.Decimal((1 if sign_bit else 0, tuple(digits), exponent))

    def to_python(self, data: bytes) -> typing.Any:
        """return a Python representation of the raw data"""
        return getattr(self, "_to_python_" + self.type_id.name.lower(), lambda x: None)(data)

    @staticmethod
    def _to_bytes_bool(obj: bool) -> bytes:
        return struct.pack("?", obj)

    @staticmethod
    def _to_bytes_int(obj: int) -> bytes:
        return struct.pack("<i", obj)

    @staticmethod
    def _to_bytes_long(obj: int) -> bytes:
        return struct.pack("<q", obj)

    @staticmethod
    def _to_bytes_float(obj: float) -> bytes:
        return struct.pack("<f", obj)

    @staticmethod
    def _to_bytes_double(obj: float) -> bytes:
        return struct.pack("<d", obj)

    @staticmethod
    def _to_bytes_datetime(obj: datetime.datetime) -> bytes:
        if isinstance(obj, pd.Timestamp):
            obj_dt = obj.to_pydatetime()
        else:
            obj_dt = obj
        td_after_epoch = obj_dt - _ValueType._DATETIME_EPOCH
        timespan = int(td_after_epoch / datetime.timedelta(milliseconds=1))
        return struct.pack("<q", timespan)

    @staticmethod
    def _to_bytes_date(obj: datetime.date) -> bytes:
        td_after_epoch = obj - _ValueType._DATETIME_EPOCH.date()
        timespan = int(td_after_epoch / datetime.timedelta(milliseconds=1))
        return struct.pack("<q", timespan)

    @staticmethod
    def _to_bytes_time(obj: datetime.time) -> bytes:
        obj_td = datetime.datetime.combine(datetime.datetime.min, obj) - datetime.datetime.min
        timestamp = obj_td // datetime.timedelta(milliseconds=1)
        return struct.pack("<q", timestamp)

    @staticmethod
    def _to_bytes_timespan(obj: datetime.timedelta) -> bytes:
        if isinstance(obj, pd.Timedelta):
            obj_td = obj.to_pytimedelta()
        elif pd.isnull(obj):
            obj_td = datetime.timedelta(0)
        else:
            obj_td = obj
        timespan = int(obj_td / datetime.timedelta(milliseconds=1))
        return struct.pack("<q", timespan)

    @staticmethod
    def _to_bytes_string(obj: str) -> bytes:
        return obj.encode("utf-8")

    @staticmethod
    def _to_bytes_binary(obj: bytes) -> bytes:
        return obj

    @staticmethod
    def _to_bytes_decimal(obj: decimal.Decimal) -> bytes:
        dec = obj.as_tuple()
        # bias the exponent and convert it to a 14-bit value
        biased_exponent = dec.exponent + _ValueType._DECIMAL_EXPONENT_BIAS
        biased_exponent_bits = bitstring.pack('uintle:16', biased_exponent)
        biased_exponent_bits_high = biased_exponent_bits[2:9]
        biased_exponent_bits_low = biased_exponent_bits[9:16]
        # combine the digits of the coefficient
        coefficient = 0
        for i in dec.digits:
            coefficient *= 10
            coefficient += i
        # construct the binary128 value
        return bitstring.pack('uintle:96,pad:17,bits:7,bool,bits:7', coefficient, biased_exponent_bits_high,
                              dec.sign, biased_exponent_bits_low).bytes

    # pylint: disable=no-else-return,too-many-return-statements
    def to_bytes(self, obj: typing.Any) -> bytes:
        """return a SBDF representation of the Python objects"""
        try:
            name = self.type_id
            if name == _ValueTypeId.BOOL:
                return self._to_bytes_bool(obj)
            elif name == _ValueTypeId.INT:
                return self._to_bytes_int(obj)
            elif name == _ValueTypeId.LONG:
                return self._to_bytes_long(obj)
            elif name == _ValueTypeId.FLOAT:
                return self._to_bytes_float(obj)
            elif name == _ValueTypeId.DOUBLE:
                return self._to_bytes_double(obj)
            elif name == _ValueTypeId.DATETIME:
                return self._to_bytes_datetime(obj)
            elif name == _ValueTypeId.DATE:
                return self._to_bytes_date(obj)
            elif name == _ValueTypeId.TIME:
                return self._to_bytes_time(obj)
            elif name == _ValueTypeId.TIMESPAN:
                return self._to_bytes_timespan(obj)
            elif name == _ValueTypeId.STRING:
                return self._to_bytes_string(obj)
            elif name == _ValueTypeId.BINARY:
                return obj
            elif name == _ValueTypeId.DECIMAL:
                return self._to_bytes_decimal(obj)
            else:
                return None
        except (struct.error, bitstring.CreationError, UnicodeError) as exc:
            raise SBDFError(f"cannot convert '{obj}' to Spotfire {self.type_id.to_typename_string()} \
            type; value is outside representable range") from exc

    def missing_value(self) -> typing.Any:
        """return a missing value appropriate for the value type"""
        val = None
        if self.type_id == _ValueTypeId.BOOL:
            val = False
        elif self.type_id == _ValueTypeId.INT:
            val = 0
        elif self.type_id == _ValueTypeId.LONG:
            val = 0
        elif self.type_id == _ValueTypeId.FLOAT:
            val = 0.0
        elif self.type_id == _ValueTypeId.DOUBLE:
            val = 0.0
        elif self.type_id == _ValueTypeId.DATETIME:
            val = self._DATETIME_EPOCH
        elif self.type_id == _ValueTypeId.DATE:
            val = self._DATETIME_EPOCH.date()
        elif self.type_id == _ValueTypeId.TIME:
            val = self._DATETIME_EPOCH.time()
        elif self.type_id == _ValueTypeId.TIMESPAN:
            val = datetime.timedelta(0)
        elif self.type_id == _ValueTypeId.STRING:
            val = ""
        elif self.type_id == _ValueTypeId.BINARY:
            val = b""
        elif self.type_id == _ValueTypeId.DECIMAL:
            val = decimal.Decimal()
        return val

    def as_sbdfobject(self) -> _SbdfObject:
        """return an SbdfObject that describes this ValueType"""
        return _SbdfObject(_ValueTypeId.BINARY, [struct.pack(">B", self.type_id)])


# Sections

class _SectionTypeId(enum.IntEnum):
    # An unknown section type.
    UNKNOWN = 0x0

    # A file header section.
    FILEHEADER = 0x1

    # A table metadata section, marking the beginning of a complete table.
    TABLEMETADATA = 0x2

    # A table slice section.
    TABLESLICE = 0x3

    # A column slice section.
    COLUMNSLICE = 0x4

    # Marks the end of a complete data table.
    TABLEEND = 0x5


def _section_write(file: typing.BinaryIO, section_id: _SectionTypeId) -> None:
    """writes the given section type id to file"""
    _write_int8(file, 0xdf)
    _write_int8(file, 0x5b)
    _write_int8(file, section_id)


def _section_read(file: typing.BinaryIO) -> int:
    """reads the given section type id from file"""
    val = _read_int8(file)
    if val != 0xdf:
        raise SBDFError("the SBDF magic number wasn't found")
    val = _read_int8(file)
    if val != 0x5b:
        raise SBDFError("the SBDF magic number wasn't found")
    return _read_int8(file)


def _section_expect(file: typing.BinaryIO, section_id: _SectionTypeId) -> None:
    """reads the section type id from file. raises error if different from passed id"""
    val = _section_read(file)
    if val != section_id:
        raise SBDFError("unexpected section id")


# Internals

def _write_bytes(file: typing.BinaryIO, value: bytes) -> int:
    if "b" not in file.mode:
        raise SBDFError("file not opened as binary")
    written = file.write(value)
    if written != len(value):
        raise SBDFError("i/o error")
    return written


def _read_bytes(file: typing.BinaryIO, n: int) -> bytes:
    if "b" not in file.mode:
        raise SBDFError("file not opened as binary")
    bytes_read = file.read(n)
    if len(bytes_read) != n:
        raise SBDFError("i/o error")
    return bytes_read


def _write_int8(file: typing.BinaryIO, value: int) -> None:
    to_write = struct.pack("B", value)
    _write_bytes(file, to_write)


def _read_int8(file: typing.BinaryIO) -> int:
    bytes_read = _read_bytes(file, 1)
    return struct.unpack("B", bytes_read)[0]


def _write_int32(file: typing.BinaryIO, value: int) -> None:
    to_write = struct.pack("<i", value)
    _write_bytes(file, to_write)


def _read_int32(file: typing.BinaryIO) -> int:
    bytes_read = _read_bytes(file, 4)
    return struct.unpack("<i", bytes_read)[0]


def _write_string(file: typing.BinaryIO, string: str) -> None:
    to_write = string.encode("utf-8")
    _write_int32(file, len(to_write))
    _write_bytes(file, to_write)


def _read_string(file: typing.BinaryIO) -> str:
    size = _read_int32(file)
    if size < 0:
        raise SBDFError("the number of elements is incorrect")
    bytes_read = _read_bytes(file, size)
    return bytes_read.decode("utf-8")


def _skip_string(file: typing.BinaryIO) -> None:
    size = _read_int32(file)
    if size < 0:
        raise SBDFError("the number of elements is incorrect")
    file.seek(size, 1)


def _write_7bit_packed_int32(file: typing.BinaryIO, value: int) -> None:
    while True:
        uch = bytearray(1)
        uch[0] = value & 0x7f
        if value > 0x7f:
            uch[0] |= 0x80
        if _write_bytes(file, uch) != 1:
            raise SBDFError("i/o error")
        if value > 0x7f:
            value >>= 7
        else:
            break


def _read_7bit_packed_int32(file: typing.BinaryIO) -> int:
    value = 0
    shift = 0
    while True:
        byte_read = _read_bytes(file, 1)
        byte_as_int = byte_read[0]
        value |= (byte_as_int & 0x7f) << shift
        if (byte_as_int & 0x80) == 0x80:
            shift += 7
        else:
            break
    return value


def _get_7bit_packed_length(value: int) -> int:
    length = 5
    if value < (1 << 7):
        length = 1
    elif value < (1 << 14):
        length = 2
    elif value < (1 << 21):
        length = 3
    elif value < (1 << 28):
        length = 4
    return length


def _write_optional_value(file: typing.BinaryIO, value) -> None:
    if value is None:
        _write_int8(file, 0)
    else:
        _write_int8(file, 1)
        value.write(file)


if gpd is not None:
    def _geo_data_frame_to_data_frame(gdf: gpd.GeoDataFrame,
                                      table_metadata: typing.Dict[str, typing.Any],
                                      column_metadata: typing.Dict[str, typing.Dict[str, typing.Any]]) -> \
            pd.DataFrame:
        if not isinstance(gdf.get("geometry")[0], shp_geom.BaseGeometry):
            return gdf

        # Write geocoding column metadata
        cols = ["XMin", "XMax", "YMin", "YMax", "XCenter", "YCenter", "Geometry"]
        metacols = list(gdf.columns.drop('geometry'))
        metacols.extend(cols)
        for col in metacols:
            if col not in column_metadata.keys():
                column_metadata[col] = {}
        for col in cols:
            column_metadata[col]["MapChart.ColumnTypeId"] = col
        column_metadata["Geometry"]["ContentType"] = "application/x-wkb"

        # Convert to dataframe
        geom = [shapely.wkb.dumps(x) for x in gdf["geometry"]]
        geom_series = gdf["geometry"]
        gdf = gdf.drop(columns="geometry")
        names = gdf.keys()
        dframe = pd.DataFrame(gdf.to_numpy(), columns=names)

        # Add spotfire geocoding columns
        dframe["Geometry"] = pd.Series(geom)
        xmin, ymin, xmax, ymax = zip(*[x.bounds for x in geom_series])
        xcen, ycen = zip(*[x.centroid.coords[:][0] for x in geom_series])
        dframe["XMin"] = pd.Series(xmin)
        dframe["XMax"] = pd.Series(xmax)
        dframe["YMin"] = pd.Series(ymin)
        dframe["YMax"] = pd.Series(ymax)
        dframe["XCenter"] = pd.Series(xcen)
        dframe["YCenter"] = pd.Series(ycen)

        # Write geocoding table metadata
        table_metadata["MapChart.IsGeocodingTable"] = True
        if not table_metadata.get("MapChart.IsGeocodingEnabled"):
            table_metadata["MapChart.IsGeocodingEnabled"] = True
        if all(isinstance(x, shapely.geometry.Point) for x in geom_series):
            table_metadata["MapChart.GeometryType"] = "Point"
        elif all(isinstance(x, shapely.geometry.LineString) for x in geom_series) or \
                all(isinstance(x, shapely.geometry.LinearRing) for x in geom_series):
            table_metadata["MapChart.GeometryType"] = "Line"
        elif all(isinstance(x, shapely.geometry.Polygon) for x in geom_series):
            table_metadata["MapChart.GeometryType"] = "Polygon"
        else:
            raise SBDFError("cannot convert collections of Shapely objects")
        if gdf.crs is not None:
            try:
                table_metadata["MapChart.GeographicCrs"] = gdf.crs.to_string()
            except AttributeError:
                # GeoPandas <= 0.6.3 compatibility
                if gdf.crs.startswith("+init="):
                    gdf.crs = gdf.crs[6:]
                table_metadata["MapChart.GeographicCrs"] = gdf.crs
        return dframe


    def _data_frame_to_geo_data_frame(dframe: pd.DataFrame,
                                      table_metadata: typing.Dict[str, typing.Any]) -> gpd.GeoDataFrame:
        if not isinstance(dframe.get('Geometry')[0], bytes):
            raise SBDFError("cannot convert to geoDataFrame")

        # Convert to geodataframe
        geom = [shapely.wkb.loads(x) for x in dframe["Geometry"]]
        dframe = dframe.drop(columns="Geometry")
        gdf = gpd.GeoDataFrame(dframe, geometry=geom)

        # Decide what CRS to use
        if "MapChart.GeographicCrs" in table_metadata.keys() and table_metadata["MapChart.GeographicCrs"] != "":
            proj = table_metadata["MapChart.GeographicCrs"][0]
            gdf.crs = proj
            try:
                # GeoPandas <= 0.6.3 compatibility
                if not gdf.crs.startswith("+init="):
                    gdf.crs = "+init=" + proj
            except AttributeError:
                pass

        return gdf

if matplotlib is not None:
    def _pyplot_to_binary(fig: matplotlib.figure.Figure) -> bytes:
        fig.set_canvas(matplotlib.pyplot.gcf().canvas)
        with tempfile.NamedTemporaryFile(suffix=".png") as file:
            fig.savefig(file, format="png")
            return _image_file_to_binary(file)

if seaborn is not None:
    def _seaborn_plot_to_binary(plot: seaborn.axisgrid.Grid) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".png") as file:
            plot.savefig(file)
            return _image_file_to_binary(file)

if PIL is not None:
    def _pil_image_to_binary(img: PIL.Image.Image) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".png") as file:
            img.save(file, "png")
            return _image_file_to_binary(file)


def _image_file_to_binary(file: tempfile.NamedTemporaryFile) -> bytes:
    file.seek(0)
    return file.read()
