from typing import BinaryIO, List

import numpy as np
import pandas as pd

try:
    import numba
except ImportError:
    numba = None

from .base import (
    DATETIME_EPOCH_NUMPY,
    ValueArrayEncodingId,
    ValueTypeId,
    _next_bytes_as_int,
)


def _next_bytes_as_array(
    file: BinaryIO, strings_as_categories: bool = False, skip_strings: bool = False
) -> np.ndarray:
    encoding = ValueArrayEncodingId(_next_bytes_as_int(file))
    value_type = ValueTypeId(_next_bytes_as_int(file))
    if encoding == ValueArrayEncodingId.PLAIN_ARRAY:
        n = _next_bytes_as_int(file, n_bytes=4)
        return _next_bytes_as_ndarray(
            file, value_type, n, strings_as_categories, skip_strings
        )
    elif encoding == ValueArrayEncodingId.RUN_LENGTH:
        raise NotImplementedError()
    elif encoding == ValueArrayEncodingId.BIT_ARRAY:
        # unpacks a binary array stored as bits, dropping padding
        n_bits = _next_bytes_as_int(file, n_bytes=4)
        n_bytes = n_bits // 8 + int(1 if n_bits % 8 > 0 else 0)
        packed_bits = np.frombuffer(file.read(n_bytes), dtype=np.uint8)
        return np.unpackbits(packed_bits)[:n_bits]
    else:
        raise ValueError(f"Unknown encoding id {encoding}")


def _next_bytes_as_ndarray(
    file: BinaryIO,
    value_type: ValueTypeId,
    n: int,
    strings_as_categories: bool = False,
    skip_strings: bool = False,
) -> np.ndarray:
    if value_type == ValueTypeId.BOOL:
        return np.frombuffer(file.read(1 * n), dtype=np.bool_)
    if value_type == ValueTypeId.INT:
        return np.frombuffer(file.read(4 * n), dtype=np.int32)
    if value_type == ValueTypeId.LONG:
        return np.frombuffer(file.read(8 * n), dtype=np.int64)
    if value_type == ValueTypeId.FLOAT:
        return np.frombuffer(file.read(4 * n), dtype=np.float32)
    if value_type == ValueTypeId.DOUBLE:
        return np.frombuffer(file.read(8 * n), dtype=np.float64)
    if value_type == ValueTypeId.DATETIME:
        timedelta = _next_bytes_as_ndarray(file, ValueTypeId.TIMESPAN, n)
        return DATETIME_EPOCH_NUMPY + timedelta
    if value_type == ValueTypeId.DATE:
        np_datetime = _next_bytes_as_ndarray(file, ValueTypeId.DATETIME, n)
        return pd.to_datetime(np_datetime).date
    if value_type == ValueTypeId.TIME:
        np_datetime = _next_bytes_as_ndarray(file, ValueTypeId.DATETIME, n)
        return pd.to_datetime(np_datetime).time
    if value_type == ValueTypeId.TIMESPAN:
        return np.frombuffer(file.read(8 * n), dtype="timedelta64[ms]")
    if value_type == ValueTypeId.STRING:
        byte_size = _next_bytes_as_int(file, n_bytes=4)
        array_bytes = file.read(byte_size)
        if skip_strings:
            return pd.Series(None, index=range(n))
        list_of_bytes = _unpack_byte_array(array_bytes, n)
        res = pd.Categorical(np.array(list_of_bytes, np.str_))
        if not strings_as_categories:
            res = res.astype("object")
        return res
    if value_type == ValueTypeId.BINARY:
        byte_size = _next_bytes_as_int(file, n_bytes=4)
        array_bytes = file.read(byte_size)
        res = _unpack_byte_array(array_bytes, n)
        res = np.array(res, "object")
        return res
    if value_type == ValueTypeId.DECIMAL:
        # not implemented
        pass
    if value_type == ValueTypeId.INTERNAL_BYTE:
        # not implemented
        pass
    raise NotImplementedError(f"Reading value type {value_type} not yet implemented.")


def _unpack_byte_array(b: bytes, n: int) -> List[bytes]:
    """Unpacks SBDF array of variable-length binary objects (including UTF-8 encoded strings)"""
    bytes_index = 0
    values = []
    for _ in range(n):
        # unpack C#-style 7-bit packed integer specifying length of next chunk
        # see: https://docs.microsoft.com/en-us/dotnet/api/system.io.binarywriter.write7bitencodedint
        current_byte: int = b[bytes_index]
        bytes_index += 1
        if current_byte < 0x80:
            n_bytes = current_byte
        else:
            n_bytes = 0
            shift = 0
            while True:
                n_bytes |= (current_byte & 0x7F) << shift
                if (current_byte & 0x80) != 0x80:
                    break
                shift += 7
                current_byte = b[bytes_index]
                bytes_index += 1

        # read next chunk
        values.append(b[bytes_index : bytes_index + n_bytes])
        bytes_index += n_bytes
    return values


# if numba available, use it to compile _unpack_byte_array
if numba is not None:
    # pass signature to trigger JIT compilation
    signature = (numba.core.types.Bytes(numba.uint8, 1, "C"), numba.int64)
    try:
        # try to cache JIT compilation
        _unpack_byte_array = numba.njit(signature, cache=True)(_unpack_byte_array)
    except RuntimeError:
        _unpack_byte_array = numba.njit(signature)(_unpack_byte_array)
