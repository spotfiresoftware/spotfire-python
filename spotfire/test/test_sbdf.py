"""Tests for importing and exporting data to SBDF files."""

import datetime
import decimal
import os
import unittest
import tempfile

import pandas
import geopandas

from spotfire import sbdf


class SbdfTest(unittest.TestCase):
    """Unit tests for public functions in 'spotfire.sbdf' module."""

    def test_read_0(self):
        """Reading simple SBDF files should work."""
        dataframe = sbdf.import_data(f"{os.path.dirname(__file__)}/files/sbdf/0.sbdf")
        self.assertEqual(dataframe.shape, (0, 12))

        def verify(dict_, pre, post):
            """Check all metadata entries for a given table/column."""
            self.assertEqual(dict_[f"{pre}MetaBoolean{post}"][0], True)
            self.assertEqual(dict_[f"{pre}MetaInteger{post}"][0], 3)
            self.assertEqual(dict_[f"{pre}MetaLong{post}"][0], 2)
            self.assertAlmostEqual(dict_[f"{pre}MetaFloat{post}"][0], 0.333333343267441)
            self.assertEqual(dict_[f"{pre}MetaDouble{post}"][0], 3.14)
            self.assertEqual(dict_[f"{pre}MetaDateTime{post}"][0], datetime.datetime(1583, 1, 1))
            self.assertEqual(dict_[f"{pre}MetaDate{post}"][0], datetime.date(1583, 1, 1))
            self.assertEqual(dict_[f"{pre}MetaTime{post}"][0], datetime.time(0, 0, 33))
            self.assertEqual(dict_[f"{pre}MetaTimeSpan{post}"][0], datetime.timedelta(0, 12, 300000))
            self.assertEqual(dict_[f"{pre}MetaString{post}"][0], "The")
            self.assertEqual(dict_[f"{pre}MetaDecimal{post}"][0], decimal.Decimal('33.4455'))
            self.assertEqual(dict_[f"{pre}MetaBinary{post}"][0], b"\x01")

        # Check table metadata
        verify(dataframe.spotfire_table_metadata, "SbdfTest.Table", "")
        # Check column metadata
        verify(dataframe["Boolean"].spotfire_column_metadata, "SbdfTest.Column", "0")
        verify(dataframe["Integer"].spotfire_column_metadata, "SbdfTest.Column", "1")
        verify(dataframe["Long"].spotfire_column_metadata, "SbdfTest.Column", "2")
        verify(dataframe["Float"].spotfire_column_metadata, "SbdfTest.Column", "3")
        verify(dataframe["Double"].spotfire_column_metadata, "SbdfTest.Column", "4")
        verify(dataframe["DateTime"].spotfire_column_metadata, "SbdfTest.Column", "5")
        verify(dataframe["Date"].spotfire_column_metadata, "SbdfTest.Column", "6")
        verify(dataframe["Time"].spotfire_column_metadata, "SbdfTest.Column", "7")
        verify(dataframe["TimeSpan"].spotfire_column_metadata, "SbdfTest.Column", "8")
        verify(dataframe["String"].spotfire_column_metadata, "SbdfTest.Column", "9")
        verify(dataframe["Decimal"].spotfire_column_metadata, "SbdfTest.Column", "10")
        verify(dataframe["Binary"].spotfire_column_metadata, "SbdfTest.Column", "11")

    def test_read_1(self):
        """Reading simple SBDF files should work."""
        dataframe = sbdf.import_data(f"{os.path.dirname(__file__)}/files/sbdf/1.sbdf")
        self.assertEqual(dataframe.shape, (1, 12))
        self.assertEqual(dataframe.at[0, "Boolean"], False)
        self.assertEqual(dataframe.at[0, "Integer"], 69)
        self.assertTrue(pandas.isnull(dataframe.at[0, "Long"]))
        self.assertEqual(dataframe.at[0, "Float"], 12.)
        self.assertEqual(dataframe.at[0, "Double"], 116.18)
        self.assertTrue(pandas.isnull(dataframe.at[0, "DateTime"]))
        self.assertEqual(dataframe.at[0, "Date"], datetime.date(1583, 1, 2))
        self.assertEqual(dataframe.at[0, "Time"], datetime.time(0, 22, 20))
        self.assertEqual(dataframe.at[0, "TimeSpan"], datetime.timedelta(0, 504, 300000))
        self.assertEqual(dataframe.at[0, "String"], "The")
        self.assertTrue(pandas.isnull(dataframe.at[0, "Binary"]))

    def test_read_100(self):
        """Reading simple SBDF files should work."""
        dataframe = sbdf.import_data(f"{os.path.dirname(__file__)}/files/sbdf/100.sbdf")
        self.assertEqual(dataframe.shape, (100, 12))
        self.assertEqual(dataframe.get("Boolean")[0:6].tolist(), [False, True, None, False, True, None])
        self.assertEqual(dataframe.get("Integer")[0:6].dropna().tolist(), [69.0, 73.0, 75.0, 79.0])
        self.assertEqual(dataframe.get("Long")[0:6].dropna().tolist(), [72.0, 74.0, 78.0, 80.0])
        for i, j in zip(dataframe.get("Float")[0:9].dropna().tolist(),
                        [12.0, 12.333333, 13.0, 13.333333, 13.666667, 14.0, 14.333333]):
            self.assertAlmostEqual(i, j)
        for i, j in zip(dataframe.get("Double")[0:9].dropna().tolist(),
                        [116.18, 122.46, 125.6, 128.74, 131.88, 135.02]):
            self.assertAlmostEqual(i, j)
        self.assertEqual(dataframe.get("String")[0:5].tolist(),
                         ["The", "quick", None, None, "jumps"])
        self.assertEqual(dataframe.get("Decimal")[0:4].tolist(),
                         [decimal.Decimal("1438.1565"), None, None, decimal.Decimal("1538.493")])

    def test_read_10001(self):
        """Reading simple SBDF files should work."""
        dataframe = sbdf.import_data(f"{os.path.dirname(__file__)}/files/sbdf/10001.sbdf")
        self.assertEqual(dataframe.shape, (10001, 12))
        # Check the values in the first row
        self.assertEqual(dataframe.at[0, "Boolean"], False)
        self.assertEqual(dataframe.at[0, "Integer"], 69)
        self.assertTrue(pandas.isnull(dataframe.at[0, "Long"]))
        self.assertEqual(dataframe.at[0, "Float"], 12.)
        self.assertEqual(dataframe.at[0, "Double"], 116.18)
        self.assertTrue(pandas.isnull(dataframe.at[0, "DateTime"]))
        self.assertEqual(dataframe.at[0, "Date"], datetime.date(1583, 1, 2))
        self.assertEqual(dataframe.at[0, "Time"], datetime.time(0, 22, 20))
        self.assertEqual(dataframe.at[0, "TimeSpan"], datetime.timedelta(0, 504, 300000))
        self.assertEqual(dataframe.at[0, "String"], "The")
        self.assertEqual(dataframe.at[0, "Binary"], None)
        # Check the values in the last row
        self.assertEqual(dataframe.at[10000, "Boolean"], True)
        self.assertTrue(pandas.isnull(dataframe.at[10000, "Integer"]))
        self.assertEqual(dataframe.at[10000, "Long"], 19118)
        self.assertAlmostEqual(dataframe.at[10000, "Float"], 3042.33325195313)
        self.assertAlmostEqual(dataframe.at[10000, "Double"], 28661.92)
        self.assertEqual(dataframe.at[10000, "DateTime"], datetime.datetime(1583, 11, 1, 0, 0))
        self.assertEqual(dataframe.at[10000, "Date"], datetime.date(1583, 11, 1))
        self.assertEqual(dataframe.at[10000, "Time"], datetime.time(21, 25, 40))
        self.assertTrue(pandas.isnull(dataframe.at[10000, "TimeSpan"]))
        self.assertEqual(dataframe.at[10000, "String"], "kiwis")
        self.assertEqual(dataframe.at[10000, "Binary"], b"\x7c\x7d\x7e\x7f")

    def test_read__write_geodata(self):
        """Test that geo-encoded data is properly converted to/from GeoDataFrame"""
        gdf = sbdf.import_data(f"{os.path.dirname(__file__)}/files/sbdf/NACountries.sbdf")
        self.assertIsInstance(gdf, pandas.DataFrame)
        self.assertIsInstance(gdf, geopandas.GeoDataFrame)
        self.assertEqual(gdf.crs.to_epsg(), 4326)
        self.assertEqual(gdf.crs.to_string(), "EPSG:4326")
        with tempfile.TemporaryDirectory() as tempdir:
            sbdf.export_data(gdf, tempdir + "\\test.sbdf")
            gdf2 = sbdf.import_data(tempdir + "\\test.sbdf")
            self.assertEqual(gdf2.crs.to_epsg(), 4326)
            self.assertEqual(gdf2.crs.to_string(), "EPSG:4326")
