# Contributions to SBDF reader functionality provided by PDF Solutions, Inc. (C) 2021

from typing import BinaryIO, NamedTuple, Sequence, Tuple, Union

import numpy as np
import pandas as pd

try:
    import numba
except ImportError:
    numba = None

from .base import (
    DATETIME_EPOCH_NUMPY,
    N_BYTES_OF_FIXED_SIZE_VALUE_TYPE,
    PANDAS_MAX_DATETIME,
    PANDAS_MIN_DATETIME,
    ValueArrayEncodingId,
    ValueTypeId,
    next_bytes_as_int,
)
from spotfire.sbdf import _ValueType


class PackedPlainArray(NamedTuple):
    array_bytes: bytes
    array_type: Union[ValueTypeId, ValueArrayEncodingId]
    n: int

    @classmethod
    def concatenate(cls, packed_arrays: Sequence["PackedPlainArray"]):
        if len(packed_arrays) == 0:
            return cls(b"", ValueTypeId.BOOL, 0)
        first_type = packed_arrays[0].array_type
        if not all(a.array_type == first_type for a in packed_arrays):
            raise ValueError("Not all packed arrays have same array_type.")
        array_bytes = b"".join(a.array_bytes for a in packed_arrays)
        n = sum(a.n for a in packed_arrays)
        return cls(array_bytes, first_type, n)


class PackedBitArray(NamedTuple):
    array_bytes: bytes
    read_mask: np.ndarray

    @classmethod
    def concatenate(cls, packed_arrays: Sequence["PackedBitArray"]) -> "PackedBitArray":
        if len(packed_arrays) == 0:
            return cls(b"", np.array([], dtype=np.bool_))
        array_bytes = b"".join(a.array_bytes for a in packed_arrays)
        read_mask = np.concatenate(tuple(a.read_mask for a in packed_arrays))
        return cls(array_bytes, read_mask)

    @classmethod
    def empty(cls, n_bits: int):
        n_bytes = n_bits // 8 + int(1 if n_bits % 8 > 0 else 0)
        array_bytes = b"\x00" * n_bytes
        read_mask = np.ones(8 * n_bytes, dtype=np.bool_)
        read_mask[n_bits:] = False
        return cls(array_bytes, read_mask)

    @property
    def n(self):
        return self.read_mask.sum()


PackedArray = Union[PackedBitArray, PackedPlainArray]


def next_bytes_as_packed_array(
    file: BinaryIO,
) -> Union[PackedPlainArray, PackedBitArray]:
    encoding = ValueArrayEncodingId(next_bytes_as_int(file))
    value_type = ValueTypeId(next_bytes_as_int(file))
    if encoding == ValueArrayEncodingId.PLAIN_ARRAY:
        n = next_bytes_as_int(file, n_bytes=4)
        if value_type in N_BYTES_OF_FIXED_SIZE_VALUE_TYPE.keys():
            n_bytes = n * N_BYTES_OF_FIXED_SIZE_VALUE_TYPE[value_type]
        else:
            n_bytes = next_bytes_as_int(file, n_bytes=4)
        array_bytes = file.read(n_bytes)
        return PackedPlainArray(array_bytes, value_type, n)
    elif encoding == ValueArrayEncodingId.RUN_LENGTH:
        raise NotImplementedError()
    elif encoding == ValueArrayEncodingId.BIT_ARRAY:
        # unpacks a binary array stored as bits, dropping padding
        n_bits = next_bytes_as_int(file, n_bytes=4)
        n_bytes = n_bits // 8 + int(1 if n_bits % 8 > 0 else 0)
        read_mask = np.ones(8 * n_bytes, dtype=np.bool_)
        read_mask[n_bits:] = False
        array_bytes = file.read(n_bytes)
        return PackedBitArray(array_bytes, read_mask)
    else:
        raise ValueError(f"Unknown encoding id {encoding}")


def unpack_bit_array(array: PackedBitArray) -> np.ndarray:
    packed_bits = np.frombuffer(array.array_bytes, dtype=np.uint8)
    return np.unpackbits(packed_bits)[array.read_mask].astype(np.bool_)


def unpack_packed_array(
    array: PackedPlainArray,
    strings_as_categories: bool = False,
) -> Union[np.ndarray, pd.core.arrays.categorical.Categorical]:
    if array.array_type == ValueTypeId.BOOL:
        return np.frombuffer(array.array_bytes, dtype=np.bool_)
    if array.array_type == ValueTypeId.INT:
        return np.frombuffer(array.array_bytes, dtype=np.int32)
    if array.array_type == ValueTypeId.LONG:
        return np.frombuffer(array.array_bytes, dtype=np.int64)
    if array.array_type == ValueTypeId.FLOAT:
        return np.frombuffer(array.array_bytes, dtype=np.float32)
    if array.array_type == ValueTypeId.DOUBLE:
        return np.frombuffer(array.array_bytes, dtype=np.float64)
    if array.array_type == ValueTypeId.DATETIME:
        timedelta = unpack_packed_array(
            PackedPlainArray(array.array_bytes, ValueTypeId.TIMESPAN, array.n)
        )
        np_datetime = DATETIME_EPOCH_NUMPY + timedelta
        # Pandas uses ns-based timestamps, so we need to handle missing-value
        #  placeholders falling outside the allowed range of ns-based timestamps
        under_min_mask = np_datetime < PANDAS_MIN_DATETIME
        over_max_mask = np_datetime > PANDAS_MAX_DATETIME
        exceeds_bounds_mask = under_min_mask | over_max_mask
        np_datetime[exceeds_bounds_mask] = np.datetime64("NaT", "ms")
        # after sanitizing bounds-exceeding values, we can return as a Pandas object
        return pd.to_datetime(np_datetime)
    if array.array_type == ValueTypeId.DATE:
        return unpack_packed_array(  # type: ignore
            PackedPlainArray(array.array_bytes, ValueTypeId.DATETIME, array.n)
        ).date
    if array.array_type == ValueTypeId.TIME:
        return unpack_packed_array(  # type: ignore
            PackedPlainArray(array.array_bytes, ValueTypeId.DATETIME, array.n)
        ).time
    if array.array_type == ValueTypeId.TIMESPAN:
        return np.frombuffer(array.array_bytes, dtype="timedelta64[ms]")
    if array.array_type == ValueTypeId.STRING:
        data, width = _repack_numpy_array(
            np.frombuffer(array.array_bytes, dtype=np.uint8), array.n
        )
        if width == 0:
            res = pd.Categorical.from_codes(
                codes=np.zeros(array.n, dtype=np.uint8),
                categories=[""],
            )
        else:
            fixed_with_string_array = data.view(f"U{width}")
            res = pd.Categorical(fixed_with_string_array)
        if not strings_as_categories:
            res = res.astype("object")
        return res
    if array.array_type == ValueTypeId.BINARY:
        data, width = _repack_numpy_array(
            np.frombuffer(array.array_bytes, dtype=np.uint8), array.n
        )
        if width == 0:
            return np.empty(array.n, "V0")
        return data.astype(np.uint8).view(f"V{width}")
    if array.array_type == ValueTypeId.DECIMAL:
        return np.array(
            [
                _ValueType._to_python_decimal(array.array_bytes[i : i + 16])
                for i in range(0, len(array.array_bytes), 16)
            ]
        )
    if array.array_type == ValueTypeId.INTERNAL_BYTE:
        # not implemented
        pass
    raise NotImplementedError(
        f"Reading value type {array.array_type} not yet implemented."
    )


def _repack_numpy_array(b: np.ndarray, n: int) -> Tuple[np.ndarray, np.ndarray]:
    """Repacks SBDF array of variable-length binary objects into a fixed-length
    zero-padded array.
    """
    bytes_index = 0
    indices = np.empty((n, 2), dtype=np.int64)
    for i in range(n):
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

        # save chunk indices and skip to next chunk
        indices[i, :] = (bytes_index, bytes_index + n_bytes)
        bytes_index += n_bytes

    lengths = indices[:, 1] - indices[:, 0]
    width = lengths.max()
    res = np.zeros(n * width, dtype=np.uint32)
    idx = 0
    for i in range(n):
        res[idx : idx + lengths[i]] = b[indices[i, 0] : indices[i, 1]]
        idx += width
    return res, width


# if numba available, use it to compile _unpack_byte_array
if numba is not None:
    # pass signature to trigger JIT compilation
    signature = (numba.types.Array(numba.uint8, 1, "C", readonly=True), numba.int64)
    try:
        # try to cache JIT compilation
        _repack_numpy_array = numba.njit(signature, nogil=True, cache=True)(
            _repack_numpy_array
        )
    except RuntimeError:
        _repack_numpy_array = numba.njit(signature, nogil=True)(_repack_numpy_array)
