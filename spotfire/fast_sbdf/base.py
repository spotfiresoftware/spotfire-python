# Contributions to SBDF reader functionality provided by PDF Solutions, Inc. (C) 2021

import datetime
import decimal
import struct
from enum import IntEnum
from typing import BinaryIO

import numpy as np
import pandas as pd

from spotfire.sbdf import _ValueType

DATETIME_EPOCH = datetime.datetime(1, 1, 1)
DATETIME_EPOCH_NUMPY = np.datetime64(DATETIME_EPOCH, "ms")
PANDAS_MIN_DATETIME = np.datetime64(np.datetime64(pd.Timestamp.min, "ms"))
PANDAS_MAX_DATETIME = np.datetime64(np.datetime64(pd.Timestamp.max, "ms"))
DECIMAL_EXPONENT_BIAS = 12320


def next_bytes_as_int(file: BinaryIO, n_bytes=1) -> int:
    """Reads next bytes of data from file as an int8 or int32."""
    if n_bytes == 1:
        return struct.unpack("B", file.read(n_bytes))[0]
    if n_bytes == 4:
        return struct.unpack("<i", file.read(n_bytes))[0]
    raise ValueError("Only 1 or 4 bytes understood.")


def next_bytes_as_binary(file: BinaryIO) -> bytes:
    """Reads next 4 bytes as bytecount int32, then reads that number of bytes."""
    n_bytes = next_bytes_as_int(file, n_bytes=4)
    assert n_bytes >= 0
    return file.read(n_bytes)


def next_bytes_as_str(file: BinaryIO) -> str:
    """Reads next bytes as binary, then decodes to UTF string."""
    return next_bytes_as_binary(file).decode()


def next_bytes_as_decimal(file: BinaryIO) -> decimal.Decimal:
    bytes = file.read(N_BYTES_OF_FIXED_SIZE_VALUE_TYPE[ValueTypeId.DECIMAL])
    return _ValueType._to_python_decimal(bytes)


class SectionTypeId(IntEnum):
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


class ValueTypeId(IntEnum):
    UNKNOWN = 0x00
    BOOL = 0x01  # C type is char
    INT = 0x02  # C type is 32-bit int
    LONG = 0x03  # C type is 64-bit int
    FLOAT = 0x04  # C type is float
    DOUBLE = 0x05  # C type is double
    DATETIME = 0x06  # C representation is milliseconds since 01/01/01, 00:00:00, stored in a 64-bit int
    DATE = 0x07  # C representation is milliseconds since 01/01/01, 00:00:00, stored in a 64-bit int
    TIME = 0x08  # C representation is milliseconds since 01/01/01, 00:00:00, stored in a 64-bit int
    TIMESPAN = 0x09  # C representation is milliseconds, stored in a 64-bit int
    STRING = 0x0A  # C representation is char-ptr
    BINARY = 0x0C  # C representation is void-ptr
    DECIMAL = 0x0D  # C representation is IEEE754 decimal128 Binary Integer Decimals
    INTERNAL_BYTE = 0xFE


class ValueArrayEncodingId(IntEnum):
    PLAIN_ARRAY = 0x1
    RUN_LENGTH = 0x2
    BIT_ARRAY = 0x3


N_BYTES_OF_FIXED_SIZE_VALUE_TYPE = {
    ValueTypeId.BOOL: 1,
    ValueTypeId.INT: 4,
    ValueTypeId.LONG: 8,
    ValueTypeId.FLOAT: 4,
    ValueTypeId.DOUBLE: 8,
    ValueTypeId.DATETIME: 8,
    ValueTypeId.DATE: 8,
    ValueTypeId.TIME: 8,
    ValueTypeId.TIMESPAN: 8,
    ValueTypeId.DECIMAL: 16,
}
