# Contributions to SBDF reader functionality provided by PDF Solutions, Inc. (C) 2021

import datetime
import struct
from typing import Any, BinaryIO, NamedTuple, Optional, Tuple

from .base import (
    DATETIME_EPOCH,
    ValueTypeId,
    next_bytes_as_binary,
    next_bytes_as_decimal,
    next_bytes_as_int,
    next_bytes_as_str,
)


class Metadatum(NamedTuple):
    name: str
    value_type: ValueTypeId
    value: Optional[Any] = None
    default_value: Optional[Any] = None


def _next_bytes_as_value(file: BinaryIO, value_type: ValueTypeId) -> Any:
    """Reads a single scalar value from the next bytes of a file.

    Note, this should only be used for reading metadata. For reading arrays of
    data, see the `array` submodule.
    """
    if value_type == ValueTypeId.BOOL:
        return struct.unpack("?", file.read(1))[0]
    if value_type == ValueTypeId.INT:
        return struct.unpack("<i", file.read(4))[0]
    if value_type == ValueTypeId.LONG:
        return struct.unpack("<q", file.read(8))[0]
    if value_type == ValueTypeId.FLOAT:
        return struct.unpack("<f", file.read(4))[0]
    if value_type == ValueTypeId.DOUBLE:
        return struct.unpack("<d", file.read(8))[0]
    if value_type == ValueTypeId.DATETIME:
        timedelta = _next_bytes_as_value(file, ValueTypeId.TIMESPAN)
        return DATETIME_EPOCH + timedelta
    if value_type == ValueTypeId.DATE:
        return _next_bytes_as_value(file, ValueTypeId.DATETIME).date()
    if value_type == ValueTypeId.TIME:
        return _next_bytes_as_value(file, ValueTypeId.DATETIME).timetz()
    if value_type == ValueTypeId.TIMESPAN:
        ms = _next_bytes_as_value(file, ValueTypeId.LONG)
        return datetime.timedelta(milliseconds=ms)
    if value_type == ValueTypeId.STRING:
        return next_bytes_as_str(file)
    if value_type == ValueTypeId.BINARY:
        return next_bytes_as_binary(file)
    if value_type == ValueTypeId.DECIMAL:
        return next_bytes_as_decimal(file)
    if value_type == ValueTypeId.INTERNAL_BYTE:
        # not implemented
        pass
    raise NotImplementedError(f"Reading value type {value_type} not yet implemented.")


def next_bytes_as_metadata(
    file: BinaryIO, skip_values: bool = False
) -> Tuple[Metadatum, ...]:
    """Reads a metadata file section."""
    n_metadata = next_bytes_as_int(file, 4)
    assert n_metadata >= 0
    table_metadata = []
    for _ in range(n_metadata):
        name = next_bytes_as_str(file)
        value_type = ValueTypeId(next_bytes_as_int(file))
        value = None
        if not skip_values:
            is_value_present = bool(next_bytes_as_int(file))
            if is_value_present:
                value = _next_bytes_as_value(file, value_type)
        default_value = None
        is_default_value_present = bool(next_bytes_as_int(file))
        if is_default_value_present:
            default_value = _next_bytes_as_value(file, value_type)
        table_metadata.append(Metadatum(name, value_type, value, default_value))
    return tuple(table_metadata)


def next_bytes_as_column_metadata(
    file: BinaryIO, metadata_for_fields: Tuple[Metadatum, ...]
) -> Tuple[Metadatum, ...]:
    """Reads a column metadata section."""
    column_metadata = []
    for field_meta in metadata_for_fields:
        is_value_present = next_bytes_as_int(file)
        if is_value_present:
            value = _next_bytes_as_value(file, field_meta.value_type)
            md = Metadatum(
                field_meta.name, field_meta.value_type, value, field_meta.default_value
            )
            column_metadata.append(md)
    return tuple(column_metadata)
