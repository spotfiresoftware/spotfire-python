"""Tests for importing and exporting data to SBDF files."""

from pathlib import Path
import datetime
import decimal
import unittest
import tempfile
import typing
import os

import pandas as pd
import pandas.testing as pdtest
import numpy as np
import geopandas as gpd
import matplotlib.pyplot
import seaborn
import PIL.Image
from packaging import version

import spotfire

try:
    import polars as pl  # type: ignore[import-not-found]
except ImportError:
    pl = None  # type: ignore[assignment]
from spotfire import sbdf
from spotfire.test import utils


class SbdfTest(unittest.TestCase):
    """Unit tests for public functions in 'spotfire.sbdf' module."""
    # pylint: disable=too-many-public-methods

    def test_read_0(self):
        """Reading simple SBDF files should work."""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/0.sbdf"))
        self._assert_dataframe_shape(dataframe, 0, ["Boolean", "Integer", "Long", "Float",
                                                    "Double", "DateTime", "Date", "Time",
                                                    "TimeSpan", "String", "Decimal", "Binary"])

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
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/1.sbdf"))
        self._assert_dataframe_shape(dataframe, 1, ["Boolean", "Integer", "Long", "Float",
                                                    "Double", "DateTime", "Date", "Time",
                                                    "TimeSpan", "String", "Decimal", "Binary"])

        self.assertEqual(dataframe.at[0, "Boolean"], False)
        self.assertEqual(dataframe.at[0, "Integer"], 69)
        self.assertTrue(pd.isnull(dataframe.at[0, "Long"]))
        self.assertEqual(dataframe.at[0, "Float"], 12.)
        self.assertEqual(dataframe.at[0, "Double"], 116.18)
        self.assertTrue(pd.isnull(dataframe.at[0, "DateTime"]))
        self.assertEqual(dataframe.at[0, "Date"], datetime.date(1583, 1, 2))
        self.assertEqual(dataframe.at[0, "Time"], datetime.time(0, 22, 20))
        self.assertEqual(dataframe.at[0, "TimeSpan"], datetime.timedelta(0, 504, 300000))
        self.assertEqual(dataframe.at[0, "String"], "The")
        self.assertTrue(pd.isnull(dataframe.at[0, "Binary"]))

    def test_read_100(self):
        """Reading simple SBDF files should work."""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/100.sbdf"))
        self._assert_dataframe_shape(dataframe, 100, ["Boolean", "Integer", "Long", "Float",
                                                      "Double", "DateTime", "Date", "Time",
                                                      "TimeSpan", "String", "Decimal", "Binary"])

        self.assertEqual(dataframe.get("Boolean")[0:6].tolist(),  # type: ignore[index]
                         [False, True, None, False, True, None])
        self.assertEqual(dataframe.get("Integer")[0:6].dropna().tolist(),  # type: ignore[index]
                         [69.0, 73.0, 75.0, 79.0])
        self.assertEqual(dataframe.get("Long")[0:6].dropna().tolist(), [72.0, 74.0, 78.0, 80.0])  # type: ignore[index]
        for i, j in zip(dataframe.get("Float")[0:9].dropna().tolist(),  # type: ignore[index]
                        [12.0, 12.333333, 13.0, 13.333333, 13.666667, 14.0, 14.333333]):
            self.assertAlmostEqual(i, j)
        for i, j in zip(dataframe.get("Double")[0:9].dropna().tolist(),  # type: ignore[index]
                        [116.18, 122.46, 125.6, 128.74, 131.88, 135.02]):
            self.assertAlmostEqual(i, j)
        self.assertEqual(dataframe.get("String")[0:5].tolist(),  # type: ignore[index]
                         ["The", "quick", None, None, "jumps"])
        self.assertEqual(dataframe.get("Decimal")[0:4].tolist(),  # type: ignore[index]
                         [decimal.Decimal("1438.1565"), None, None, decimal.Decimal("1538.493")])

    def test_read_10001(self):
        """Reading simple SBDF files should work."""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/10001.sbdf"))
        self._assert_dataframe_shape(dataframe, 10001, ["Boolean", "Integer", "Long", "Float",
                                                        "Double", "DateTime", "Date", "Time",
                                                        "TimeSpan", "String", "Decimal", "Binary"])

        # Check the values in the first row
        self.assertEqual(dataframe.at[0, "Boolean"], False)
        self.assertEqual(dataframe.at[0, "Integer"], 69)
        self.assertTrue(pd.isnull(dataframe.at[0, "Long"]))
        self.assertEqual(dataframe.at[0, "Float"], 12.)
        self.assertEqual(dataframe.at[0, "Double"], 116.18)
        self.assertTrue(pd.isnull(dataframe.at[0, "DateTime"]))
        self.assertEqual(dataframe.at[0, "Date"], datetime.date(1583, 1, 2))
        self.assertEqual(dataframe.at[0, "Time"], datetime.time(0, 22, 20))
        self.assertEqual(dataframe.at[0, "TimeSpan"], datetime.timedelta(0, 504, 300000))
        self.assertEqual(dataframe.at[0, "String"], "The")
        self.assertEqual(dataframe.at[0, "Binary"], None)

        # Check the values in the last row
        self.assertEqual(dataframe.at[10000, "Boolean"], True)
        self.assertTrue(pd.isnull(dataframe.at[10000, "Integer"]))
        self.assertEqual(dataframe.at[10000, "Long"], 19118)
        self.assertAlmostEqual(dataframe.at[10000, "Float"], 3042.33325195313)  # type: ignore[misc, arg-type]
        self.assertAlmostEqual(dataframe.at[10000, "Double"], 28661.92)  # type: ignore[misc, arg-type]
        self.assertEqual(dataframe.at[10000, "DateTime"], datetime.datetime(1583, 11, 1, 0, 0))
        self.assertEqual(dataframe.at[10000, "Date"], datetime.date(1583, 11, 1))
        self.assertEqual(dataframe.at[10000, "Time"], datetime.time(21, 25, 40))
        self.assertTrue(pd.isnull(dataframe.at[10000, "TimeSpan"]))
        self.assertEqual(dataframe.at[10000, "String"], "kiwis")
        self.assertEqual(dataframe.at[10000, "Binary"], b"\x7c\x7d\x7e\x7f")

    def test_read_write_geodata(self):
        """Test that geo-encoded data is properly converted to/from ``GeoDataFrame``."""
        gdf = sbdf.import_data(utils.get_test_data_file("sbdf/NACountries.sbdf"))
        self.assertIsInstance(gdf, pd.DataFrame)
        self.assertIsInstance(gdf, gpd.GeoDataFrame)

        # GeoPandas >= 0.7.0
        if version.Version(gpd.__version__) >= version.Version("0.7.0"):
            self.assertEqual(gdf.crs.to_epsg(), 4326)
            self.assertEqual(gdf.crs.to_string(), "EPSG:4326")
            gdf2 = self._roundtrip_dataframe(gdf)
            self.assertEqual(gdf2.crs.to_epsg(), 4326)
            self.assertEqual(gdf2.crs.to_string(), "EPSG:4326")
        else:
            # GeoPandas < 0.7.0 compatibility
            self.assertEqual(gdf.crs, "+init=EPSG:4326")
            gdf2 = self._roundtrip_dataframe(gdf)
            self.assertEqual(gdf2.crs, "+init=EPSG:4326")

    def test_write_unicode(self):
        """Test that unicode string arrays are properly written."""
        udf = sbdf.import_data(utils.get_test_data_file("sbdf/unicode.sbdf"))
        udf2 = self._roundtrip_dataframe(udf)
        for i in range(3):
            self.assertEqual(udf.at[i, "x"], udf2.at[i, "x"])

    def test_read_write_alltypes(self):
        """Test that all data types can be properly round-tripped read/write."""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/alltypes.sbdf"))
        df2 = self._roundtrip_dataframe(dataframe)
        pdtest.assert_frame_equal(dataframe, df2)

    def test_write_nullable_dtypes(self):
        """We should be able to write all nullable column dtypes."""
        dataframe = pd.DataFrame({
            'b': pd.Series([True, False, pd.NA], dtype='boolean'),
            'i': pd.Series([1, pd.NA, 3], dtype='Int32'),
            'l': pd.Series([pd.NA, 5, 6], dtype='Int64'),
            'f': pd.Series([7., 8., pd.NA], dtype='Float32'),
            'd': pd.Series([10., pd.NA, 12.], dtype='Float64')
        })
        df2 = self._roundtrip_dataframe(dataframe)
        self.assertTrue(pd.isna(df2.at[2, 'b']))
        self.assertTrue(pd.isna(df2.at[1, 'i']))
        self.assertTrue(pd.isna(df2.at[0, 'l']))
        self.assertTrue(pd.isna(df2.at[2, 'f']))
        self.assertTrue(pd.isna(df2.at[1, 'd']))

    def test_get_spotfire_types(self):
        """All types should be reported properly."""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/alltypes.sbdf"))
        type_names = spotfire.get_spotfire_types(dataframe)
        self.assertEqual(type_names["ColumnBoolean"], "Boolean")
        self.assertEqual(type_names["ColumnDate"], "Date")
        self.assertEqual(type_names["ColumnDateTime"], "DateTime")
        self.assertEqual(type_names["ColumnDecimal"], "Currency")
        self.assertEqual(type_names["ColumnDouble"], "Real")
        self.assertEqual(type_names["ColumnFloat"], "SingleReal")
        self.assertEqual(type_names["ColumnInteger"], "Integer")
        self.assertEqual(type_names["ColumnLong"], "LongInteger")
        self.assertEqual(type_names["ColumnString"], "String")
        self.assertEqual(type_names["ColumnTime"], "Time")
        self.assertEqual(type_names["ColumnTimeSpan"], "TimeSpan")
        self.assertEqual(type_names["ColumnCMTNA"], "Integer")

    def test_set_spotfire_types(self):
        """Setting SBDF types should work properly."""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/alltypes.sbdf"))
        # set a single column by name
        spotfire.set_spotfire_types(dataframe, {"ColumnLong": "Integer"})
        self.assertEqual(spotfire.get_spotfire_types(dataframe)["ColumnLong"], "Integer")

        # set multiple columns by name
        spotfire.set_spotfire_types(dataframe, {"ColumnString": "Boolean", "ColumnTime": "Date"})
        self.assertEqual(spotfire.get_spotfire_types(dataframe)["ColumnString"], "Boolean")
        self.assertEqual(spotfire.get_spotfire_types(dataframe)["ColumnTime"], "Date")

        # set invalid column name
        with self.assertWarnsRegex(Warning, "Column 'BadColumnName' not found in data"):
            spotfire.set_spotfire_types(dataframe, {"BadColumnName": "Integer"})

        # set invalid column type
        with self.assertWarnsRegex(Warning, "Spotfire type 'BadType' for column 'ColumnLong' not recognized"):
            spotfire.set_spotfire_types(dataframe, {"ColumnLong": "BadType"})

        # one invalid column name, other changes should be committed
        types = spotfire.get_spotfire_types(dataframe)
        self.assertEqual(types["ColumnString"], "Boolean")
        self.assertEqual(types["ColumnDate"], "Date")
        with self.assertWarnsRegex(Warning, "Column 'BadColumnName' not found in data"):
            spotfire.set_spotfire_types(dataframe, {"ColumnString": "Integer", "BadColumnName": "Integer",
                                                    "ColumnDate": "DateTime"})
        types = spotfire.get_spotfire_types(dataframe)
        self.assertEqual(types["ColumnString"], "Integer")
        self.assertEqual(types["ColumnDate"], "DateTime")

        # one invalid column type, other changes should be committed
        types = spotfire.get_spotfire_types(dataframe)
        self.assertEqual(types["ColumnString"], "Integer")
        self.assertEqual(types["ColumnLong"], "Integer")
        self.assertEqual(types["ColumnInteger"], "Integer")
        with self.assertWarnsRegex(Warning, "Spotfire type 'BadType' for column 'ColumnLong' not recognized"):
            spotfire.set_spotfire_types(dataframe, {"ColumnString": "String", "ColumnLong": "BadType",
                                                    "ColumnInteger": "LongInteger"})
        types = spotfire.get_spotfire_types(dataframe)
        self.assertEqual(types["ColumnString"], "String")
        self.assertEqual(types["ColumnLong"], "Integer")
        self.assertEqual(types["ColumnInteger"], "LongInteger")

    def test_import_export_alltypes(self):
        """Verify all types properly export and re-import with the proper Spotfire type."""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/alltypes.sbdf"))
        new_df = self._roundtrip_dataframe(dataframe)
        pdtest.assert_frame_equal(dataframe, new_df)
        pdtest.assert_series_equal(spotfire.get_spotfire_types(dataframe), spotfire.get_spotfire_types(new_df))

    def test_invalid_export_type(self):
        """Verify invalid export types are ignored."""
        dataframe = pd.DataFrame({"x": [1, 2, 3]})

        # setting invalid type via function should fail
        with self.assertWarnsRegex(Warning, "Spotfire type 'Unknown' for column 'x' not recognized"):
            spotfire.set_spotfire_types(dataframe, {"x": "Unknown"})

        # force set it and see expect it to be ignored
        dataframe["x"].attrs["spotfire_type"] = "Unknown"
        new_df = self._roundtrip_dataframe(dataframe)
        new_df_types = spotfire.get_spotfire_types(new_df)
        self.assertEqual(new_df_types["x"], "LongInteger")

    def test_import_export_string(self):
        """Verify string column conversions."""
        data = ["apple", "banana", "cherry"]
        default_type = "String"
        pass_types = ["String", "Boolean"]
        fail_types = ["DateTime", "Date", "Time", "TimeSpan", "Currency",
                      "Integer", "LongInteger", "SingleReal", "Real", "Binary"]
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_binary(self):
        """Verify binary column conversions."""
        data = [b"apple", b"banana", b"cherry"]
        default_type = "Binary"
        pass_types = ["String", "Binary", "Boolean"]
        fail_types = ["DateTime", "Date", "Time", "TimeSpan", "Currency",
                      "Integer", "LongInteger", "SingleReal", "Real"]
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_boolean(self):
        """Verify boolean column conversions."""
        data = [True, False]
        default_type = "Boolean"
        pass_types = ["String", "Boolean", "Integer", "LongInteger", "SingleReal", "Real"]
        fail_types = ["DateTime", "Date", "Time", "TimeSpan", "Binary", "Currency"]
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_integer(self):
        """Verify integer column conversions."""
        data = [1, 2, 3]
        default_type = "LongInteger"
        pass_types = ["String", "Boolean", "Integer", "LongInteger", "SingleReal", "Real"]
        fail_types = ["DateTime", "Date", "Time", "TimeSpan", "Binary", "Currency"]
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_float(self):
        """Verify float column conversions."""
        data = [1., 2., 3.5]
        default_type = "Real"
        pass_types = ["String", "Boolean", "Integer", "LongInteger", "SingleReal", "Real"]
        fail_types = ["DateTime", "Date", "Time", "TimeSpan", "Binary", "Currency"]
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_datetime(self):
        """Verify datetime column conversions."""
        data = [datetime.datetime.now(), datetime.datetime(1979, 10, 23, 5, 32, 00)]
        default_type = "DateTime"
        pass_types = ["String", "DateTime", "Boolean"]
        fail_types = ["Binary", "Currency", "Date", "Time", "TimeSpan", "Integer", "LongInteger", "SingleReal", "Real"]
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_date(self):
        """Verify date column conversions."""
        data = [datetime.datetime.now().date(), datetime.datetime(1979, 10, 23, 5, 32, 00).date()]
        default_type = "Date"
        pass_types = ["String", "Date", "Boolean"]
        fail_types = ["Binary", "Currency", "DateTime", "Time", "TimeSpan", "Integer",
                      "LongInteger", "SingleReal", "Real"]
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_time(self):
        """Verify time column conversions."""
        data = [datetime.datetime.now().time(), datetime.datetime(1979, 10, 23, 5, 32, 00).time()]
        default_type = "Time"
        pass_types = ["String", "Time", "Boolean"]
        fail_types = ["Binary", "Currency", "DateTime", "Date", "TimeSpan", "Integer",
                      "LongInteger", "SingleReal", "Real"]
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_timespan(self):
        """Verify time column conversions."""
        data = [datetime.timedelta(milliseconds=12345678900), datetime.timedelta(milliseconds=98765432100)]
        default_type = "TimeSpan"
        pass_types = ["String", "TimeSpan", "Boolean"]
        fail_types = ["Binary", "Currency", "DateTime", "Date", "Time", "Integer", "LongInteger", "SingleReal", "Real"]
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_currency(self):
        """Verify currency/decimal column conversions."""
        data = [decimal.Decimal("123.45"), decimal.Decimal("67.890")]
        default_type = "Currency"
        pass_types = ["String", "Currency", "Boolean"]
        fail_types = ["Binary", "DateTime", "Date", "Time", "TimeSpan", "Integer", "LongInteger", "SingleReal", "Real"]
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_missing(self):
        """Verify column with all missing values can be coerced to anything."""
        data = [None, None, None]
        default_type = None
        pass_types = ["String", "DateTime", "Date", "Time", "TimeSpan", "Binary", "Currency",
                      "Boolean", "Integer", "LongInteger", "SingleReal", "Real"]
        fail_types: typing.List[str] = []
        self._verify_import_export_types(data, default_type, pass_types, fail_types)

    def _verify_import_export_types(self, data, default_type: typing.Optional[str], pass_types: typing.List[str],
                                    fail_types: typing.List[str]):
        """Helper function that takes a column of data and round trips export/import
           and verifies that the data is the expected type."""
        self.assertEqual(len(pass_types) + len(fail_types), 12,
                         f"Only {len(pass_types) + len(fail_types)} SBDF types tested.  Should be all 12!")
        dataframe = pd.DataFrame({"x": data})

        # validate expected default case (auto-detected type)
        if default_type:
            new_df = self._roundtrip_dataframe(dataframe)
            new_df_types = spotfire.get_spotfire_types(new_df)
            self.assertEqual(new_df_types["x"], default_type)
        # if default is None expect failure
        else:
            with tempfile.TemporaryDirectory() as tempdir:
                with self.assertRaises(sbdf.SBDFError):
                    sbdf.export_data(dataframe, f"{tempdir}/output.sbdf")

        # validate expected passing cases
        for df_type in pass_types:
            with self.subTest(df_type=df_type):
                spotfire.set_spotfire_types(dataframe, {"x": df_type})
                new_df = self._roundtrip_dataframe(dataframe)
                new_df_types = spotfire.get_spotfire_types(new_df)
                self.assertEqual(new_df_types["x"], df_type)

        # validate expected failure cases
        for df_type in fail_types:
            with self.subTest(df_type=df_type):
                spotfire.set_spotfire_types(dataframe, {"x": df_type})
                with self.assertRaises(sbdf.SBDFError):
                    self._roundtrip_dataframe(dataframe)

    def test_column_promotion(self):
        """Verify promotion of large valued ``Integer`` columns correctly promote to ``LongInteger``."""
        dataframe = pd.DataFrame({
            'large': [500400300200, 500400300201, pd.NA, 500400300203],
            'small': [0, 1, pd.NA, 3]
        })
        spotfire.set_spotfire_types(dataframe, {'large': 'Integer', 'small': 'Integer'})
        new_df = self._roundtrip_dataframe(dataframe)
        exported_types = spotfire.get_spotfire_types(new_df)
        self.assertEqual(exported_types['large'], 'LongInteger')
        self.assertEqual(exported_types['small'], 'Integer')

    def test_non_str_column_name(self):
        """Verify non-string column names export properly."""
        dataframe = pd.DataFrame({
            3.14159: ['pi', 'tau/2']
        })
        df2 = self._roundtrip_dataframe(dataframe)
        for i, col in enumerate(df2.columns):
            self.assertEqual(type(col), str, f"df2.columns[{i}] = {repr(col)}")

    def test_tz_aware_datetime(self):
        """Verify timezone aware datetime objects export properly."""
        now = datetime.datetime.now()
        now_utc = now.astimezone(datetime.timezone.utc)
        now_local = now.astimezone()
        dataframe = pd.DataFrame({
            'naive': [now],
            'utc':   [now_utc],
            'local': [now_local]
        })
        df2 = self._roundtrip_dataframe(dataframe)
        for col in df2.columns:
            val = df2.at[0, col]
            # Instead of self.assertAlmostEqual(val, now, delta=timedelta(...))
            if isinstance(val, (datetime.datetime, pd.Timestamp)):
                self.assertLessEqual(abs(val - now), datetime.timedelta(milliseconds=1))
            else:
                self.assertEqual(val, now) # SBDF has millisecond resolution

    def test_numpy_datetime_resolution(self):
        """Verify that different NumPy resolutions for datetime64 dtypes export properly."""
        target = datetime.datetime(2020, 1, 1)
        inputs = {
            's': 1577836800,
            'ms': 1577836800000,
            'us': 1577836800000000,
            'ns': 1577836800000000000,
        }
        for resolution, timestamp in inputs.items():
            with self.subTest(resolution=resolution):
                array = np.array([[0], [timestamp]]).astype(f"datetime64[{resolution}]")
                dataframe = pd.DataFrame(array, columns=["x"])
                df2 = self._roundtrip_dataframe(dataframe)
                val = df2.at[1, 'x']
                self.assertEqual(val, target)

    def test_numpy_timedelta_resolution(self):
        """Verify that different NumPy resolutions for timedelta64 dtypes export properly."""
        target = datetime.timedelta(seconds=38400)
        inputs = {
            's': 38400,
            'ms': 38400000,
            'us': 38400000000,
            'ns': 38400000000000,
        }
        for resolution, timestamp in inputs.items():
            with self.subTest(resolution=resolution):
                array = np.array([[0], [timestamp]]).astype(f"timedelta64[{resolution}]")
                dataframe = pd.DataFrame(array, columns=["x"])
                df2 = self._roundtrip_dataframe(dataframe)
                val = df2.at[1, 'x']
                self.assertEqual(val, target)

    def test_image_matplot(self):
        """Verify Matplotlib figures export properly."""
        matplotlib.pyplot.clf()
        fig, _ = matplotlib.pyplot.subplots()
        df2 = self._roundtrip_dataframe(fig)
        self._assert_dataframe_shape(df2, 1, ['x'])
        image = df2.at[0, "x"]
        if isinstance(image, (bytes, bytearray)):
            self._assert_is_png_image(image)
        else:
            self.fail(f"Expected PNG bytes, got {type(image)}: {image!r}")

    def test_image_seaborn(self):
        """Verify Seaborn grids export properly."""
        matplotlib.pyplot.clf()
        dataframe = pd.DataFrame({'x': range(10), 'y': range(10, 0, -1)})
        grid = seaborn.FacetGrid(dataframe)
        df2 = self._roundtrip_dataframe(grid)
        self._assert_dataframe_shape(df2, 1, ['x'])
        image = df2.at[0, "x"]
        if isinstance(image, (bytes, bytearray)):
            self._assert_is_png_image(image)
        else:
            self.fail(f"Expected PNG bytes, got {type(image)}: {image!r}")

    def test_image_pil(self):
        """Verify PIL images export properly."""
        image = PIL.Image.new("RGB", (100, 100))
        df2 = self._roundtrip_dataframe(image)
        self._assert_dataframe_shape(df2, 1, ['x'])
        val = df2.at[0, "x"]
        if isinstance(val, (bytes, bytearray)):
            self._assert_is_png_image(val)
        else:
            self.fail(f"Expected PNG bytes, got {type(val)}: {val!r}")

    def test_export_dict_of_lists(self):
        """Exporting a dict of lists should produce a valid SBDF file."""
        data = {"ints": [1, 2, 3], "floats": [1.1, 2.2, 3.3], "strings": ["a", "b", "c"]}
        result = self._roundtrip_dataframe(data)
        self.assertEqual(len(result), 3)
        self.assertEqual(result["ints"].dropna().astype(int).tolist(), [1, 2, 3])
        self.assertAlmostEqual(result["floats"][0], 1.1)
        self.assertEqual(result["strings"].tolist(), ["a", "b", "c"])

    def test_export_list(self):
        """Exporting a plain Python list should produce a single-column SBDF file."""
        result = self._roundtrip_dataframe([10, 20, 30])
        self.assertEqual(len(result), 3)
        self.assertEqual(result.columns[0], "x")
        self.assertEqual(result["x"].dropna().astype(int).tolist(), [10, 20, 30])

    def test_export_import_unicode_path(self):
        """Test export and import with a Unicode file path."""
        dataframe = pd.DataFrame({"col": [1, 2, 3], "txt": ["a", "b", "c"]})
        with tempfile.TemporaryDirectory() as tempdir:
            unicode_filename = Path(tempdir) / "日本語ファイル" / "test.sbdf"
            os.makedirs(os.path.dirname(unicode_filename), exist_ok=True)
            # Export to Unicode path
            sbdf.export_data(dataframe, str(unicode_filename))

            # Import from Unicode path
            imported = sbdf.import_data(str(unicode_filename))

            # Check roundtrip
            pd.testing.assert_frame_equal(imported[["col", "txt"]], dataframe, check_dtype=False)
            # Check dtype of the column
            self.assertEqual(dataframe["col"].dtype, "int64")
            self.assertEqual(dataframe["txt"].dtype, "object")

    @staticmethod
    def _roundtrip_dataframe(dataframe: typing.Any) -> pd.DataFrame:
        """Write out a dataframe to SBDF and immediately read it back in to a new one."""
        with tempfile.TemporaryDirectory() as tempdir:
            sbdf.export_data(dataframe, f"{tempdir}/output.sbdf")
            return sbdf.import_data(f"{tempdir}/output.sbdf")

    def _assert_dataframe_shape(self, dataframe: pd.DataFrame, rows: int, column_names: list[str]) -> None:
        """Assert that a dataframe has a specific number of rows and the given column names."""
        self.assertEqual(len(dataframe), rows, msg="number of rows")
        self.assertEqual(len(dataframe.columns), len(column_names), msg="number of columns")
        for i, col in enumerate(column_names):
            self.assertEqual(dataframe.columns[i], col, msg=f"column #{i} name")

    def _assert_is_png_image(self, expr: bytes) -> None:
        """Assert that a bytes object represents PNG image data."""
        self.assertEqual(expr[0:8], b'\x89PNG\x0d\x0a\x1a\x0a')


@unittest.skipIf(pl is None, "polars not installed")
class SbdfPolarsTest(unittest.TestCase):
    """Unit tests for Polars DataFrame support in 'spotfire.sbdf' module."""
    # pylint: disable=too-many-public-methods

    def test_write_polars_basic(self):
        """Exporting a Polars DataFrame with common types should produce a valid SBDF file."""
        polars_df = pl.DataFrame({
            "flag": [True, False, True],
            "count": [1, 2, 3],
            "value": [1.1, 2.2, 3.3],
            "label": ["a", "b", "c"],
        })
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/output.sbdf"
            sbdf.export_data(polars_df, path)
            result = sbdf.import_data(path)
        self.assertEqual(len(result), 3)
        self.assertEqual(list(result.columns), ["flag", "count", "value", "label"])
        self.assertEqual(result["flag"].tolist(), [True, False, True])
        self.assertEqual(result["count"].dropna().astype(int).tolist(), [1, 2, 3])
        self.assertAlmostEqual(result["value"][0], 1.1)
        self.assertEqual(result["label"].tolist(), ["a", "b", "c"])

    def test_write_polars_nulls(self):
        """Exporting a Polars DataFrame with null values should preserve nulls."""
        polars_df = pl.DataFrame({
            "ints": [1, None, 3],
            "floats": [1.0, None, 3.0],
            "strings": ["x", None, "z"],
        })
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/output.sbdf"
            sbdf.export_data(polars_df, path)
            result = sbdf.import_data(path)
        self.assertTrue(pd.isnull(result["ints"][1]))
        self.assertTrue(pd.isnull(result["floats"][1]))
        self.assertTrue(pd.isnull(result["strings"][1]))

    def test_write_polars_series(self):
        """Exporting a Polars Series should produce a valid SBDF file."""
        series = pl.Series("vals", [10, 20, 30])
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/output.sbdf"
            sbdf.export_data(series, path)
            result = sbdf.import_data(path)
        self.assertEqual(len(result), 3)
        self.assertEqual(result.columns[0], "vals")
        self.assertEqual(result["vals"].dropna().astype(int).tolist(), [10, 20, 30])

    def test_import_as_polars(self):
        """Importing an SBDF file with output_format=OutputFormat.POLARS should return a native Polars DataFrame."""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/1.sbdf"), output_format=sbdf.OutputFormat.POLARS)
        self.assertIsInstance(dataframe, pl.DataFrame)
        self.assertNotIsInstance(dataframe, pd.DataFrame)
        self.assertIn("Boolean", dataframe.columns)
        self.assertIn("Integer", dataframe.columns)
        # Verify nulls are preserved natively
        self.assertIsNone(dataframe["Long"][0])

    def test_write_polars_categorical(self):
        """Exporting a Polars Categorical column should export as String."""
        polars_df = pl.DataFrame({"cat": pl.Series(["a", "b", "a"]).cast(pl.Categorical)})
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/output.sbdf"
            sbdf.export_data(polars_df, path)
            result = sbdf.import_data(path)
        self.assertEqual(result["cat"].tolist(), ["a", "b", "a"])

    def test_write_polars_uint64_warns(self):
        """Exporting a Polars UInt64 column should emit a warning about overflow risk."""
        polars_df = pl.DataFrame({"big": pl.Series([1, 2, 3], dtype=pl.UInt64)})
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/output.sbdf"
            with self.assertWarns(sbdf.SBDFWarning):
                sbdf.export_data(polars_df, path)

    def test_write_polars_datetime_tz(self):
        """Exporting a timezone-aware Polars Datetime column should warn about timezone loss."""
        polars_df = pl.DataFrame({
            "ts": pl.Series([datetime.datetime(2024, 1, 1)]).dt.replace_time_zone("UTC")
        })
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/output.sbdf"
            with self.assertWarns(sbdf.SBDFWarning):
                sbdf.export_data(polars_df, path)

    def test_polars_roundtrip(self):
        """A Polars DataFrame should survive an export/import roundtrip."""
        original = pl.DataFrame({
            "integers": [1, 2, 3],
            "floats": [1.5, 2.5, 3.5],
            "strings": ["foo", "bar", "baz"],
        })
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/roundtrip.sbdf"
            sbdf.export_data(original, path)
            result = sbdf.import_data(path, output_format=sbdf.OutputFormat.POLARS)
        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(result["strings"].to_list(), ["foo", "bar", "baz"])
        self.assertAlmostEqual(result["floats"][0], 1.5)

    def test_invalid_output_format(self):
        """Passing an unknown output_format should raise SBDFError immediately."""
        polars_df = pl.DataFrame({"x": [1, 2, 3]})
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/output.sbdf"
            sbdf.export_data(polars_df, path)
            with self.assertRaises(sbdf.SBDFError):
                sbdf.import_data(path, output_format="numpy")  # type: ignore[call-overload]

    def test_write_polars_empty(self):
        """Exporting an empty Polars DataFrame should produce a valid (empty) SBDF file."""
        polars_df = pl.DataFrame({"a": pl.Series([], dtype=pl.Int32),
                                  "b": pl.Series([], dtype=pl.Utf8)})
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/empty.sbdf"
            sbdf.export_data(polars_df, path)
            result = sbdf.import_data(path)
        self.assertEqual(len(result), 0)
        self.assertIn("a", result.columns)
        self.assertIn("b", result.columns)

    def test_write_polars_series_nulls(self):
        """Exporting a Polars Series with null values should preserve those nulls."""
        series = pl.Series("vals", [1, None, 3], dtype=pl.Int32)
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/series_nulls.sbdf"
            sbdf.export_data(series, path)
            result = sbdf.import_data(path)
        self.assertTrue(pd.isnull(result["vals"][1]))
        self.assertEqual(int(result["vals"][0]), 1)
        self.assertEqual(int(result["vals"][2]), 3)

    def test_polars_categorical_warns(self):
        """Exporting a Polars Categorical column should emit a SBDFWarning."""
        polars_df = pl.DataFrame({"cat": pl.Series(["x", "y", "x"]).cast(pl.Categorical)})
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/cat_warn.sbdf"
            with self.assertWarns(sbdf.SBDFWarning):
                sbdf.export_data(polars_df, path)

    def test_write_polars_null_dtype(self):
        """Exporting a Polars all-null Series (dtype=Null) should produce an all-invalid column."""
        polars_df = pl.DataFrame({"nothing": pl.Series([None, None, None])})
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/null_dtype.sbdf"
            sbdf.export_data(polars_df, path)
            result = sbdf.import_data(path)
        self.assertEqual(len(result), 3)
        self.assertTrue(pd.isnull(result["nothing"][0]))
        self.assertTrue(pd.isnull(result["nothing"][1]))
        self.assertTrue(pd.isnull(result["nothing"][2]))

    def test_write_polars_float_nan(self):
        """NaN in a Polars float column should be treated as invalid (missing), not a real value."""
        polars_df = pl.DataFrame({"vals": pl.Series([1.0, float("nan"), 3.0])})
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/float_nan.sbdf"
            sbdf.export_data(polars_df, path)
            result = sbdf.import_data(path)
        self.assertAlmostEqual(result["vals"][0], 1.0)
        self.assertTrue(pd.isnull(result["vals"][1]))
        self.assertAlmostEqual(result["vals"][2], 3.0)

    # Date conversion correctness test

    def test_date_view_equals_astype(self):
        """The in-place epoch-shift + view conversion used in _import_build_polars_dataframe
        should produce the same datetime64[D] values as the reference astype() path for a
        range of dates spanning the SBDF epoch, dates before the Unix epoch, the Unix epoch
        itself, a recent date, and the maximum representable date."""
        sbdf_epoch_ms = 62135596800000  # ms from datetime(1,1,1) to datetime(1970,1,1)
        test_dates = [
            datetime.date(1, 1, 1),      # SBDF epoch — largest negative offset from Unix
            datetime.date(1969, 12, 31), # one day before Unix epoch
            datetime.date(1970, 1, 1),   # Unix epoch — must give day 0
            datetime.date(1970, 1, 2),   # one day after Unix epoch
            datetime.date(2024, 1, 15),  # arbitrary recent date
            datetime.date(9999, 12, 31), # maximum Python date
        ]
        for test_date in test_dates:
            # Reproduce the raw SBDF int64 value exactly as the C importer would produce it.
            sbdf_ms = int(
                (test_date - datetime.date(1, 1, 1)) / datetime.timedelta(milliseconds=1)
            )
            arr = np.array([sbdf_ms], dtype=np.int64)

            # Apply the same in-place conversion used in _import_build_polars_dataframe.
            arr -= sbdf_epoch_ms
            arr //= 86400000
            view_result = arr.view('datetime64[D]')[0]

            # Reference: convert the Python date directly via astype.
            ref_result = np.array([test_date], dtype=object).astype('datetime64[D]')[0]

            self.assertEqual(
                view_result, ref_result,
                msg=f"Mismatch for {test_date}: view={view_result}, astype={ref_result}"
            )

    # Metadata warning tests

    def test_polars_import_meta_warning(self):
        """import_data with output_format=OutputFormat.POLARS should warn that metadata is not preserved."""
        with self.assertWarnsRegex(sbdf.SBDFWarning, "metadata"):
            sbdf.import_data(utils.get_test_data_file("sbdf/1.sbdf"), output_format=sbdf.OutputFormat.POLARS)

    def test_polars_df_export_meta_warn(self):
        """export_data with a Polars DataFrame should warn that metadata is not preserved."""
        polars_df = pl.DataFrame({"x": [1, 2, 3]})
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/meta_warn.sbdf"
            with self.assertWarnsRegex(sbdf.SBDFWarning, "metadata"):
                sbdf.export_data(polars_df, path)

    def test_polars_series_meta_export(self):
        """export_data with a Polars Series should warn that metadata is not preserved."""
        series = pl.Series("x", [1, 2, 3])
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/meta_warn_series.sbdf"
            with self.assertWarnsRegex(sbdf.SBDFWarning, "metadata"):
                sbdf.export_data(series, path)

    # Metadata public-API error tests

    def test_copy_metadata_polars_error(self):
        """copy_metadata should raise TypeError with a Polars-specific message."""
        polars_df = pl.DataFrame({"x": [1, 2, 3]})
        with self.assertRaisesRegex(TypeError, "Polars"):
            spotfire.copy_metadata(polars_df, polars_df)

    def test_get_types_polars_error(self):
        """get_spotfire_types should raise TypeError with a Polars-specific message."""
        polars_df = pl.DataFrame({"x": [1, 2, 3]})
        with self.assertRaisesRegex(TypeError, "Polars"):
            spotfire.get_spotfire_types(polars_df)  # type: ignore[arg-type]

    def test_set_types_polars_error(self):
        """set_spotfire_types should raise TypeError with a Polars-specific message."""
        polars_df = pl.DataFrame({"x": [1, 2, 3]})
        with self.assertRaisesRegex(TypeError, "Polars"):
            spotfire.set_spotfire_types(polars_df, {"x": "Integer"})  # type: ignore[arg-type]

    def test_polars_string_multichunk(self):
        """Verify Polars String exports spanning multiple SBDF row slices give correct values.

        The Arrow buffer path in _export_extract_string_obj_arrow uses raw C pointer
        arithmetic (values_buf + offsets[idx]).  A second chunk (start=100_000, count=1)
        verifies the offset into the values buffer is computed correctly when start > 0.
        """
        n = 100_001
        labels = ["a"] * n
        labels[-1] = "sentinel"
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/multichunk.sbdf"
            with self.assertWarns(sbdf.SBDFWarning):
                sbdf.export_data(pl.DataFrame({"s": labels}), path)
            result = sbdf.import_data(path)
        self.assertEqual(len(result), n)
        self.assertEqual(result.at[0, "s"], "a")
        self.assertEqual(result.at[n - 1, "s"], "sentinel")

    # Cross-path equivalence tests

    @staticmethod
    def _all_dtypes_polars_df():
        """Build a canonical Polars DataFrame covering all 11 non-Decimal SBDF types.

        Each column has exactly one null at a distinct row index (rotating 0–4) so every
        row contains both valid and null values.  Non-null values cover negatives, pre-epoch
        timestamps, edge times, and raw bytes to exercise the full value range.
        """
        dt = datetime.datetime
        d = datetime.date
        t = datetime.time
        td = datetime.timedelta
        return pl.DataFrame([
            pl.Series("bool_col",     [None, True, False, True, False],
                      dtype=pl.Boolean),
            pl.Series("int32_col",    [1, None, -2, 3, -4],
                      dtype=pl.Int32),
            pl.Series("int64_col",    [1, 2_000_000_000, None, -3_000_000_000, 4],
                      dtype=pl.Int64),
            pl.Series("float32_col",  [1.5, -2.5, 3.5, None, 5.5],
                      dtype=pl.Float32),
            pl.Series("float64_col",  [1.0, -2.0, 3.0, -4.0, None],
                      dtype=pl.Float64),
            pl.Series("datetime_col", [None,
                                       dt(2020, 1, 1, 12, 0, 0),
                                       dt(1969, 7, 20, 20, 17, 0),
                                       dt(2024, 12, 31, 23, 59, 59),
                                       dt(1583, 1, 2, 0, 0, 0)],
                      dtype=pl.Datetime("ms")),
            pl.Series("date_col",     [d(2020, 1, 1), None, d(1969, 7, 20),
                                       d(2024, 12, 31), d(1583, 1, 2)],
                      dtype=pl.Date),
            pl.Series("time_col",     [t(12, 0, 0), t(0, 0, 0), None, t(23, 59, 59), t(6, 30)],
                      dtype=pl.Time),
            pl.Series("duration_col", [td(days=1), td(seconds=30), td(days=-1), None, td(hours=2)],
                      dtype=pl.Duration("ms")),
            pl.Series("string_col",   ["hello", "world", "foo", "bar", None],
                      dtype=pl.String),
            pl.Series("binary_col",   [None, b"\x00\x01", b"\xff", b"", b"\xde\xad"],
                      dtype=pl.Binary),
        ])

    @staticmethod
    def _all_dtypes_pandas_df():
        """Build the Pandas equivalent of ``_all_dtypes_polars_df()``.

        Mirrors the same 5 rows, 11 columns, and null positions using Pandas nullable
        dtypes so both DataFrames produce identical SBDF files when exported.  Float columns
        use numpy NaN (not pd.NA) to match what the Polars export path stores for missing
        floating-point values.

        Note: ``polars.DataFrame.to_pandas()`` requires pyarrow, which is not part of the
        required dependencies.  This helper provides the same data without that dependency.
        """
        dt = datetime.datetime
        d = datetime.date
        t = datetime.time
        td = datetime.timedelta
        return pd.DataFrame({
            "bool_col":     pd.array([None, True, False, True, False],  dtype="boolean"),
            "int32_col":    pd.array([1, None, -2, 3, -4],              dtype="Int32"),
            "int64_col":    pd.array([1, 2_000_000_000, None, -3_000_000_000, 4], dtype="Int64"),
            "float32_col":  np.array([1.5, -2.5, 3.5, np.nan, 5.5],    dtype="float32"),
            "float64_col":  np.array([1.0, -2.0, 3.0, -4.0, np.nan],   dtype="float64"),
            "datetime_col": pd.array([pd.NaT,
                                      dt(2020, 1, 1, 12, 0, 0),
                                      dt(1969, 7, 20, 20, 17, 0),
                                      dt(2024, 12, 31, 23, 59, 59),
                                      dt(1583, 1, 2, 0, 0, 0)],        dtype="datetime64[ms]"),
            "date_col":     [d(2020, 1, 1), None, d(1969, 7, 20), d(2024, 12, 31), d(1583, 1, 2)],
            "time_col":     [t(12, 0, 0), t(0, 0, 0), None, t(23, 59, 59), t(6, 30)],
            "duration_col": pd.array([td(days=1), td(seconds=30), td(days=-1), pd.NaT, td(hours=2)],
                                     dtype="timedelta64[ms]"),  # type: ignore[call-overload]
            "string_col":   ["hello", "world", "foo", "bar", None],
            "binary_col":   [None, b"\x00\x01", b"\xff", b"", b"\xde\xad"],
        })

    def test_all_dtypes_polars_export(self):
        """Exporting via the native Polars path and the Pandas path should produce identical data.

        The Polars DataFrame and an equivalent Pandas DataFrame (same values, same nulls) are
        each exported to a separate SBDF file.  Both files are then imported back as Pandas and
        compared element-wise, covering all 11 non-Decimal SBDF types with one null per column.
        """
        pl_df = self._all_dtypes_polars_df()
        pd_df = self._all_dtypes_pandas_df()
        with tempfile.TemporaryDirectory() as tempdir:
            polars_path = f"{tempdir}/via_polars.sbdf"
            pandas_path = f"{tempdir}/via_pandas.sbdf"
            sbdf.export_data(pl_df, polars_path)
            sbdf.export_data(pd_df, pandas_path)
            pd_from_polars = sbdf.import_data(polars_path)
            pd_from_pandas = sbdf.import_data(pandas_path)
        pdtest.assert_frame_equal(
            pd_from_polars, pd_from_pandas,
            check_dtype=False, check_exact=False, rtol=1e-5,
        )

    def _assert_import_paths_equivalent(self, polars_result, pandas_result):
        """Assert that a Polars import result and a Pandas import result contain identical data.

        Uses ``Series.to_list()`` (no pyarrow required) to materialise Polars values as Python
        objects and compares them against the corresponding Pandas column values.  Null
        positions are verified with ``Series.is_null()`` / ``Series.isna()``, and non-null
        float values are compared with a relative tolerance to absorb float32 representation
        differences.
        """
        self.assertEqual(list(polars_result.columns), list(pandas_result.columns))
        for col in polars_result.columns:
            pl_series = polars_result[col]
            pd_series = pandas_result[col]
            pl_nulls = pl_series.is_null().to_list()
            pd_nulls = pd_series.isna().tolist()
            self.assertEqual(pl_nulls, pd_nulls, f"column '{col}': null positions differ")
            pl_vals = [v for v in pl_series.to_list() if v is not None]
            pd_vals = [v for v in pd_series.dropna().tolist() if v is not None]
            self.assertEqual(len(pl_vals), len(pd_vals),
                             f"column '{col}': non-null value counts differ")
            dtype_name = pl_series.dtype.__class__.__name__
            if dtype_name in ("Float32", "Float64"):
                for pl_val, pdv in zip(pl_vals, pd_vals):
                    self.assertAlmostEqual(float(pl_val), float(pdv), places=4,
                                          msg=f"column '{col}': value mismatch")
            else:
                self.assertEqual(pl_vals, pd_vals, f"column '{col}': values differ")

    def test_all_dtypes_polars_import(self):
        """Importing the same SBDF via the Polars and Pandas paths should yield equivalent data.

        The same SBDF file is imported twice — once as a native Polars DataFrame and once as a
        Pandas DataFrame — then compared column by column using ``Series.to_list()`` (no
        pyarrow required).  Covers all 11 non-Decimal SBDF types with one null per column.
        """
        pl_df = self._all_dtypes_polars_df()
        with tempfile.TemporaryDirectory() as tempdir:
            path = f"{tempdir}/source.sbdf"
            sbdf.export_data(pl_df, path)
            polars_result = sbdf.import_data(path, output_format=sbdf.OutputFormat.POLARS)
            pandas_result = sbdf.import_data(path)
        self._assert_import_paths_equivalent(polars_result, pandas_result)
