# Copyright © 2021. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""User visible utility functions."""

import typing
import warnings

import pandas as pd

from spotfire import sbdf


# Table and column metadata functions

def copy_metadata(source, destination) -> None:
    """Copy the table and column metadata from a Pandas object to another.

    :param source: the DataFrame or Series to copy metadata from
    :param destination: the DataFrame or Series to copy metadata to
    :raise TypeError: if the types of source and destination do not match
    """
    # Verify that types of source and destination match
    if isinstance(source, pd.DataFrame) and not isinstance(destination, pd.DataFrame):
        raise TypeError("both source and destination must be DataFrames")
    if isinstance(source, pd.Series) and not isinstance(destination, pd.Series):
        raise TypeError("both source and destination must be Series")

    # Handle DataFrames
    if isinstance(source, pd.DataFrame):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                destination.spotfire_table_metadata = source.spotfire_table_metadata
            except AttributeError:
                pass
        for col in source.columns:
            try:
                source1 = source[col]
                destination1 = destination[col]
                destination1.spotfire_column_metadata = source1.spotfire_column_metadata
            except AttributeError:
                pass
    # Handle Series
    elif isinstance(source, pd.Series):
        try:
            destination.spotfire_column_metadata = source.spotfire_column_metadata
        except AttributeError:
            pass


# Spotfire type functions

def get_spotfire_types(dataframe: pd.DataFrame) -> pd.Series:
    """Get Spotfire column type names from an imported DataFrame.

    :param dataframe: the DataFrame to get the Spotfire types of
    :returns: a Series containing the Spotfire types of each column of dataframe
    """
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe is not a DataFrame")
    spotfire_types = {}
    for col in dataframe.columns:
        if 'spotfire_type' in dataframe[col].attrs:
            spotfire_types[col] = dataframe[col].attrs['spotfire_type']
        else:
            spotfire_types[col] = None
    return pd.Series(spotfire_types)


def set_spotfire_types(dataframe: pd.DataFrame, column_types: typing.Dict[str, str]) -> None:
    """Set Spotfire column types to use when exporting a DataFrame to SBDF.  If any column name or type is invalid,
    a warning will be issued, but any other valid assignments will succeed.

    :param dataframe: the DataFrame to set the Spotfire types of
    :param column_types: dictionary that maps column names to column types
    """
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe is not a DataFrame")
    for col, spotfire_type in column_types.items():
        if col not in dataframe:
            warnings.warn(f"Column '{col}' not found in data")
            continue
        if not sbdf.spotfire_typename_to_valuetype_id(spotfire_type):
            warnings.warn(f"Spotfire type '{spotfire_type}' for column '{col}' not recognized", sbdf.SBDFWarning)
            continue
        dataframe[col].attrs['spotfire_type'] = spotfire_type
