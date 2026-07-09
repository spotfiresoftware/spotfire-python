# Copyright © 2026. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Accessor helpers for Spotfire metadata on DataFrames.

Metadata is stored in ``df.attrs`` at the DataFrame level (never per-column).
This survives copy, drop, rename, concat, groupby, and inplace operations
in pandas 3.  Only ``merge()`` loses ``df.attrs``.

For backward compatibility, the old monkey-patched ``df.spotfire_table_metadata``
pattern is also checked (with a deprecation warning).

For the old ``df['col'].spotfire_column_metadata`` pattern, a Series accessor
is registered that raises a clear error — this pattern is silently broken
under pandas 3 Copy-on-Write.

This module is the single abstraction point for metadata storage on
pandas DataFrames.
"""

import copy
import warnings

_TABLE_METADATA_KEY = 'spotfire_table_metadata'
_COLUMN_METADATA_KEY = 'spotfire_column_metadata'
_SPOTFIRE_TYPES_KEY = 'spotfire_types'
_ALL_KEYS = (_TABLE_METADATA_KEY, _COLUMN_METADATA_KEY, _SPOTFIRE_TYPES_KEY)

# Keys whose values grow with column count and need CoW optimization.
# Table metadata is excluded: it is small and passed to Cython's
# ``_export_metadata(dict md, ...)`` which rejects dict subclasses.
_COW_KEYS = (_COLUMN_METADATA_KEY, _SPOTFIRE_TYPES_KEY)


class _CowDict(dict):
    """Copy-on-Write dict for pandas 3 ``deepcopy(df.attrs)`` performance.

    Pandas 3 calls ``deepcopy(df.attrs)`` on every ``df[col]`` access.
    With large metadata dicts (one entry per column), the recursive deep
    copy is O(n) per access, making column loops O(n^2).

    This subclass applies Copy-on-Write: ``__deepcopy__`` returns ``self``
    (O(1) — zero cost on read), and the ``_metadata`` setters detach by
    shallow-copying on first write when the dict is shared.  This gives
    the speed of ``return self`` with the isolation of a full copy.
    """

    _shared = False

    def __deepcopy__(self, memo):
        self._shared = True
        return self

    def __copy__(self):
        self._shared = True
        return self

    def is_shared(self):
        """Return whether this dict has been handed out via deepcopy."""
        return self._shared

    def detach(self):
        """Create an independent shallow copy and clear the shared flag."""
        clone = _CowDict(self)
        clone._shared = False  # pylint: disable=protected-access
        return clone


def _detach_if_shared(dataframe, key):
    """If the dict for *key* is shared, replace it with an independent shallow copy."""
    val = dataframe.attrs.get(key)
    if val is not None and isinstance(val, _CowDict) and val.is_shared():
        val = val.detach()
        dataframe.attrs[key] = val
    return val


def _get(dataframe, key, default=None):
    """Read a metadata key from ``df.attrs``, with legacy ``__dict__`` fallback."""
    val = dataframe.attrs.get(key)
    if val is not None:
        return val

    # Fallback: legacy monkey-patched attribute in __dict__
    val = dataframe.__dict__.get(key)
    if val is not None:
        warnings.warn(
            f"Accessing metadata via df.{key} is deprecated. "
            f"Use the spotfire.get_table_metadata() / spotfire.set_table_metadata() "
            f"functions instead.",
            DeprecationWarning,
            stacklevel=3
        )
        return val

    return default


def _set(dataframe, key, value):
    """Write a metadata key to ``df.attrs``."""
    if key in _COW_KEYS and isinstance(value, dict) and not isinstance(value, _CowDict):
        value = _CowDict(value)
    dataframe.attrs[key] = value


# --- Public API ---

def get_table_metadata(dataframe):
    """Return the table-level Spotfire metadata dict, or ``{}`` if none."""
    return _get(dataframe, _TABLE_METADATA_KEY, {})


def set_table_metadata(dataframe, metadata):
    """Set the table-level Spotfire metadata dict."""
    _set(dataframe, _TABLE_METADATA_KEY, metadata)


def get_column_metadata(dataframe, col):
    """Return the Spotfire metadata dict for *col*, or ``{}`` if none."""
    return _get(dataframe, _COLUMN_METADATA_KEY, {}).get(col, {})


def set_column_metadata(dataframe, col, metadata):
    """Set the Spotfire metadata dict for *col*."""
    col_meta = _detach_if_shared(dataframe, _COLUMN_METADATA_KEY)
    if col_meta is None:
        col_meta = _CowDict()
        _set(dataframe, _COLUMN_METADATA_KEY, col_meta)
    col_meta[col] = metadata


def get_spotfire_type(dataframe, col):
    """Return the Spotfire type name for *col*, or ``None`` if not set."""
    return _get(dataframe, _SPOTFIRE_TYPES_KEY, {}).get(col)


def set_spotfire_type(dataframe, col, typename):
    """Set the Spotfire type name for *col*."""
    types = _detach_if_shared(dataframe, _SPOTFIRE_TYPES_KEY)
    if types is None:
        types = _CowDict()
        _set(dataframe, _SPOTFIRE_TYPES_KEY, types)
    types[col] = typename


def get_all_spotfire_types(dataframe):
    """Return a dict mapping column name -> Spotfire type name for all columns that have one."""
    return dict(_get(dataframe, _SPOTFIRE_TYPES_KEY, {}))


def copy_all_metadata(source, destination):
    """Copy all Spotfire metadata from *source* to *destination*."""
    for key in _ALL_KEYS:
        val = _get(source, key)
        if val:
            _set(destination, key, copy.deepcopy(val))


# --- Deprecation helpers for old per-column patterns ---

def _register_deprecated_accessors():
    """Register pandas accessor that raises clear error for old per-column metadata pattern.

    ``df['col'].spotfire_column_metadata = {...}`` is silently broken under pandas 3
    Copy-on-Write (writes are discarded). This accessor intercepts READ attempts
    and raises a helpful error pointing to the new API.
    """
    try:
        import pandas as pd  # pylint: disable=import-outside-toplevel

        @pd.api.extensions.register_series_accessor('spotfire_column_metadata')
        class _DeprecatedColumnMetadata:  # pylint: disable=too-few-public-methods
            def __init__(self, series):
                raise AttributeError(
                    "df['col'].spotfire_column_metadata is not supported under pandas 3 "
                    "Copy-on-Write (writes are silently discarded). "
                    "Use spotfire.get_column_metadata(df, 'col') and "
                    "spotfire.set_column_metadata(df, 'col', metadata) instead."
                )
    except Exception:  # pylint: disable=broad-exception-caught
        pass


_register_deprecated_accessors()
