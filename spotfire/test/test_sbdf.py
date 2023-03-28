"""Tests for importing and exporting data to SBDF files."""

import datetime
import decimal
import unittest
import tempfile
import pkg_resources

import pandas
import pandas.testing
import geopandas

import spotfire
from spotfire import sbdf
from spotfire.test import utils


class SbdfTest(unittest.TestCase):
    """Unit tests for public functions in 'spotfire.sbdf' module."""
    # pylint: disable=too-many-public-methods

    def test_read_0(self):
        """Reading simple SBDF files should work."""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/0.sbdf"))
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
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/1.sbdf"))
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
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/100.sbdf"))
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
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/10001.sbdf"))
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

    def test_read_write_geodata(self):
        """Test that geo-encoded data is properly converted to/from GeoDataFrame"""
        gdf = sbdf.import_data(utils.get_test_data_file("sbdf/NACountries.sbdf"))
        self.assertIsInstance(gdf, pandas.DataFrame)
        self.assertIsInstance(gdf, geopandas.GeoDataFrame)

        # GeoPandas >= 0.7.0
        if pkg_resources.parse_version(geopandas.__version__) >= pkg_resources.parse_version("0.7.0"):
            self.assertEqual(gdf.crs.to_epsg(), 4326)
            self.assertEqual(gdf.crs.to_string(), "EPSG:4326")
            with tempfile.TemporaryDirectory() as tempdir:
                sbdf.export_data(gdf, f"{tempdir}/test.sbdf")
                gdf2 = sbdf.import_data(f"{tempdir}/test.sbdf")
                self.assertEqual(gdf2.crs.to_epsg(), 4326)
                self.assertEqual(gdf2.crs.to_string(), "EPSG:4326")
        else:
            # GeoPandas < 0.7.0 compatibility
            self.assertEqual(gdf.crs, "+init=EPSG:4326")
            with tempfile.TemporaryDirectory() as tempdir:
                sbdf.export_data(gdf, f"{tempdir}/test.sbdf")
                gdf2 = sbdf.import_data(f"{tempdir}/test.sbdf")
                self.assertEqual(gdf2.crs, "+init=EPSG:4326")

    def test_write_unicode(self):
        """Test that unicode string arrays are properly written"""
        udf = sbdf.import_data(utils.get_test_data_file("sbdf/unicode.sbdf"))
        with tempfile.TemporaryDirectory() as tempdir:
            sbdf.export_data(udf, f"{tempdir}/test.sbdf")
            udf2 = sbdf.import_data(f"{tempdir}/test.sbdf")
            for i in range(3):
                self.assertEqual(udf.at[i, "x"], udf2.at[i, "x"])

    def test_read_write_alltypes(self):
        """Test that all data types can be properly roundtripped read/write"""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/alltypes.sbdf"))
        with tempfile.TemporaryDirectory() as tempdir:
            sbdf.export_data(dataframe, f"{tempdir}/test.sbdf")
            df2 = sbdf.import_data(f"{tempdir}/test.sbdf")
            pandas.testing.assert_frame_equal(dataframe, df2)

    def test_write_nullable_dtypes(self):
        """We should be able to write all nullable column dtypes."""
        dataframe = pandas.DataFrame({
            'b': pandas.Series([True, False, pandas.NA], dtype='boolean'),
            'i': pandas.Series([1, pandas.NA, 3], dtype='Int32'),
            'l': pandas.Series([pandas.NA, 5, 6], dtype='Int64'),
            'f': pandas.Series([7., 8., pandas.NA], dtype='Float32'),
            'd': pandas.Series([10., pandas.NA, 12.], dtype='Float64')
        })
        with tempfile.TemporaryDirectory() as tempdir:
            sbdf.export_data(dataframe, f"{tempdir}/test.sbdf")
            df2 = sbdf.import_data(f"{tempdir}/test.sbdf")
            self.assertTrue(pandas.isna(df2.at[2, 'b']))
            self.assertTrue(pandas.isna(df2.at[1, 'i']))
            self.assertTrue(pandas.isna(df2.at[0, 'l']))
            self.assertTrue(pandas.isna(df2.at[2, 'f']))
            self.assertTrue(pandas.isna(df2.at[1, 'd']))

    def test_get_spotfire_types(self):
        """All types should be reported properly"""
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
        """Setting SBDF types should work properly"""
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
        """Verify all types properly export and re-import with the proper Spotfire type"""
        dataframe = sbdf.import_data(utils.get_test_data_file("sbdf/alltypes.sbdf"))
        with tempfile.TemporaryDirectory() as tempdir:
            sbdf.export_data(dataframe, f"{tempdir}/output.sbdf")
            new_df = sbdf.import_data(f"{tempdir}/output.sbdf")
        pandas.testing.assert_frame_equal(dataframe, new_df)
        pandas.testing.assert_series_equal(spotfire.get_spotfire_types(dataframe), spotfire.get_spotfire_types(new_df))

    def test_invalid_export_type(self):
        """Verify invalid export types are ignored"""
        dataframe = pandas.DataFrame({"x": [1, 2, 3]})

        # setting invalid type via function should fail
        with self.assertWarnsRegex(Warning, "Spotfire type 'Unknown' for column 'x' not recognized"):
            spotfire.set_spotfire_types(dataframe, {"x": "Unknown"})

        # force set it and see expect it to be ignored
        dataframe["x"].attrs["spotfire_type"] = "Unknown"
        _, newdf_types = self.roundtrip_dataframe(dataframe)
        self.assertEqual(newdf_types["x"], "LongInteger")

    def test_import_export_string(self):
        """Verify string column conversions"""
        data = ["apple", "banana", "cherry"]
        default_type = "String"
        pass_types = ["String", "Boolean"]
        fail_types = ["DateTime", "Date", "Time", "TimeSpan", "Currency",
                      "Integer", "LongInteger", "SingleReal", "Real", "Binary"]
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_binary(self):
        """Verify binary column conversions"""
        data = [b"apple", b"banana", b"cherry"]
        default_type = "Binary"
        pass_types = ["String", "Binary", "Boolean"]
        fail_types = ["DateTime", "Date", "Time", "TimeSpan", "Currency",
                      "Integer", "LongInteger", "SingleReal", "Real"]
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_boolean(self):
        """Verify boolean column conversions"""
        data = [True, False]
        default_type = "Boolean"
        pass_types = ["String", "Boolean", "Integer", "LongInteger", "SingleReal", "Real"]
        fail_types = ["DateTime", "Date", "Time", "TimeSpan", "Binary", "Currency"]
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_integer(self):
        """Verify integer column conversions"""
        data = [1, 2, 3]
        default_type = "LongInteger"
        pass_types = ["String", "Boolean", "Integer", "LongInteger", "SingleReal", "Real"]
        fail_types = ["DateTime", "Date", "Time", "TimeSpan", "Binary", "Currency"]
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_float(self):
        """Verify float column conversions"""
        data = [1., 2., 3.5]
        default_type = "Real"
        pass_types = ["String", "Boolean", "Integer", "LongInteger", "SingleReal", "Real"]
        fail_types = ["DateTime", "Date", "Time", "TimeSpan", "Binary", "Currency"]
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_datetime(self):
        """Verify datetime column conversions"""
        data = [datetime.datetime.now(), datetime.datetime(1979, 10, 23, 5, 32, 00)]
        default_type = "DateTime"
        pass_types = ["String", "DateTime", "Boolean"]
        fail_types = ["Binary", "Currency", "Date", "Time", "TimeSpan", "Integer", "LongInteger", "SingleReal", "Real"]
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_date(self):
        """Verify date column conversions"""
        data = [datetime.datetime.now().date(), datetime.datetime(1979, 10, 23, 5, 32, 00).date()]
        default_type = "Date"
        pass_types = ["String", "Date", "Boolean"]
        fail_types = ["Binary", "Currency", "DateTime", "Time", "TimeSpan", "Integer",
                      "LongInteger", "SingleReal", "Real"]
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_time(self):
        """Verify time column conversions"""
        data = [datetime.datetime.now().time(), datetime.datetime(1979, 10, 23, 5, 32, 00).time()]
        default_type = "Time"
        pass_types = ["String", "Time", "Boolean"]
        fail_types = ["Binary", "Currency", "DateTime", "Date", "TimeSpan", "Integer",
                      "LongInteger", "SingleReal", "Real"]
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_timespan(self):
        """Verify time column conversions"""
        data = [datetime.timedelta(milliseconds=12345678900), datetime.timedelta(milliseconds=98765432100)]
        default_type = "TimeSpan"
        pass_types = ["String", "TimeSpan", "Boolean"]
        fail_types = ["Binary", "Currency", "DateTime", "Date", "Time", "Integer", "LongInteger", "SingleReal", "Real"]
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_currency(self):
        """Verify currency/decimal column conversions"""
        data = [decimal.Decimal("123.45"), decimal.Decimal("67.890")]
        default_type = "Currency"
        pass_types = ["String", "Currency", "Boolean"]
        fail_types = ["Binary", "DateTime", "Date", "Time", "TimeSpan", "Integer", "LongInteger", "SingleReal", "Real"]
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def test_import_export_missing(self):
        """Verify column with all missing values can be coerced to anything"""
        data = [None, None, None]
        default_type = None
        pass_types = ["String", "DateTime", "Date", "Time", "TimeSpan", "Binary", "Currency",
                      "Boolean", "Integer", "LongInteger", "SingleReal", "Real"]
        fail_types = []
        self.verify_import_export_types(data, default_type, pass_types, fail_types)

    def verify_import_export_types(self, data, default_type, pass_types, fail_types):
        """Helper function that takes a column of data and roundtrips export/import
           and verifies that the data is the expected type"""
        self.assertEqual(len(pass_types) + len(fail_types), 12,
                         f"Only {len(pass_types) + len(fail_types)} SBDF types tested.  Should be all 12!")
        dataframe = pandas.DataFrame({"x": data})

        # validate expected default case (auto-detected type)
        if default_type:
            _, new_df_types = self.roundtrip_dataframe(dataframe)
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
                _, new_df_types = self.roundtrip_dataframe(dataframe)
                self.assertEqual(new_df_types["x"], df_type)

        # validate expected failure cases
        for df_type in fail_types:
            with self.subTest(df_type=df_type):
                spotfire.set_spotfire_types(dataframe, {"x": df_type})
                with self.assertRaises(sbdf.SBDFError):
                    self.roundtrip_dataframe(dataframe)

    @staticmethod
    def roundtrip_dataframe(dataframe):
        """Write out a dataframe to SBDF and immediately read it back in to a new one"""
        with tempfile.TemporaryDirectory() as tempdir:
            sbdf.export_data(dataframe, f"{tempdir}/output.sbdf")
            new_df = sbdf.import_data(f"{tempdir}/output.sbdf")
            new_df_types = spotfire.get_spotfire_types(new_df)
            return new_df, new_df_types

    def test_column_promotion(self):
        """Verify promotion of large valued Integer columns correctly promote to LongInteger"""
        dataframe = pandas.DataFrame({
            'large': [500400300200, 500400300201, pandas.NA, 500400300203],
            'small': [0, 1, pandas.NA, 3]
        })
        spotfire.set_spotfire_types(dataframe, {'large': 'Integer', 'small': 'Integer'})
        _, exported_types = self.roundtrip_dataframe(dataframe)
        self.assertEqual(exported_types['large'], 'LongInteger')
        self.assertEqual(exported_types['small'], 'Integer')

    def test_non_str_column_name(self):
        """Verify non-string column names export properly"""
        dataframe = pandas.DataFrame({
            3.14159: ['pi', 'tau/2']
        })
        with tempfile.TemporaryDirectory() as tempdir:
            sbdf.export_data(dataframe, f"{tempdir}/output.sbdf")
            df2 = sbdf.import_data(f"{tempdir}/output.sbdf")
            for i, col in enumerate(df2.columns):
                self.assertEqual(type(col), str, f"df2.columns[{i}] = {repr(col)}")
