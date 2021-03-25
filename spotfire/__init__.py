# Copyright © 2021. TIBCO Software Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""User visible utility functions."""

import warnings

import pandas as pd


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
            destination.spotfire_table_metadata = source.spotfire_table_metadata
        for col in source.columns:
            try:
                source1 = source[col]
                destination1 = destination[col]
                destination1.spotfire_column_metadata = source1.spotfire_column_metadata
            except AttributeError:
                pass
    # Handle Series
    elif isinstance(source, pd.Series):
        destination.spotfire_column_metadata = source.spotfire_column_metadata
