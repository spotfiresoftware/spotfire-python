# Copyright © 2024. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

import enum
import typing

import pandas as pd

if typing.TYPE_CHECKING:
    import polars as pl


_FilenameLike = typing.Union[str, bytes, int]

class SBDFError(Exception): ...
class SBDFWarning(Warning): ...

class OutputFormat(enum.Enum):
    """Supported output formats for :func:`import_data`."""
    PANDAS: str
    POLARS: str

def spotfire_typename_to_valuetype_id(typename: str) -> typing.Optional[int]: ...
@typing.overload
def import_data(sbdf_file: _FilenameLike, output_format: typing.Literal[OutputFormat.PANDAS] = ...) -> pd.DataFrame: ...
@typing.overload
def import_data(sbdf_file: _FilenameLike, output_format: typing.Literal[OutputFormat.POLARS]) -> "pl.DataFrame": ...
def export_data(obj: typing.Any, sbdf_file: _FilenameLike, default_column_name: str = "x",
                rows_per_slice: int = 0, encoding_rle: bool = True) -> None: ...
