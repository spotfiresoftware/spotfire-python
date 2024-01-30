# Copyright © 2024. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

import typing

import pandas as pd


_FilenameLike = typing.Union[str, bytes, int]

class SBDFError(Exception): ...
class SBDFWarning(Warning): ...

def spotfire_typename_to_valuetype_id(typename: str) -> typing.Optional[int]: ...
def import_data(sbdf_file: _FilenameLike): ...
def export_data(obj: typing.Any, sbdf_file: _FilenameLike, default_column_name: str = "x",
                rows_per_slice: int = 0, encoding_rle: bool = True) -> None: ...
