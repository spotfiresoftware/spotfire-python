"""Tests for verifying the full data function path from analytic spec through result."""

import re
import os
import os.path
import sys
import unittest
import warnings

import pandas as pd
import pandas.testing as pdtest

from spotfire import sbdf, data_function as datafn, _utils
from spotfire.test import utils as testutils


class _PythonVersionedExpectedValue:
    """Represents a message whose contents can depend on the version of the Python interpreter that created it."""
    def __init__(self, name):
        # self._major = 0
        # self._minor = 0
        self._message = None
        self._load_version(name)

    def _load_version(self, name):
        # Read in the all-versions expected output file
        self._load_file(testutils.get_test_data_file(f"data_function/{name}.txt"))
        # Now try to find a better version for our Python interpreter
        for version in range(sys.version_info.minor, 9, -1):
            filename = testutils.get_test_data_file(f"data_function/{name}-{sys.version_info.major}.{version}.txt")
            if os.path.exists(filename):
                self._load_file(filename)
                return

    def _load_file(self, filename):
        with open(filename, encoding="utf-8") as file:
            self._message = file.read()

    def __call__(self, *args, **kwargs):
        return self._message


class DataFunctionTest(unittest.TestCase):
    """Unit tests for public functions in 'spotfire.data_function' module."""
    # pylint: disable=too-many-branches, too-many-statements, too-many-arguments, too-many-public-methods

    def _run_analytic(self, script, inputs, outputs, success, expected_result, spec_adjust=None) -> None:
        """Run a full pass through the analytic protocol, and compare the output to the expected value."""
        # pylint: disable=protected-access,too-many-locals
        with _utils.TempFiles() as temp_files:
            input_spec = []
            for k in inputs:
                if inputs[k] is None:
                    in_type = "NULL"
                    print(f"test: missing input '{k}' ")
                    input_spec.append(datafn.AnalyticInput(k, in_type, ""))
                    continue
                if isinstance(inputs[k], pd.DataFrame):
                    in_type = "table"
                else:
                    try:
                        if len(inputs[k]) == 1:
                            in_type = "value"
                        else:
                            in_type = "column"
                    except TypeError:
                        in_type = "value"
                tmp = temp_files.new_file(suffix=".sbdf")
                tmp.close()
                sbdf.export_data(inputs[k], tmp.name, k)
                print(f"test: writing input {in_type} '{k}' to file '{tmp.name}'")
                input_spec.append(datafn.AnalyticInput(k, in_type, tmp.name))
            output_spec = []
            for k in outputs:
                tmp = temp_files.new_file(suffix=".sbdf")
                tmp.close()
                output_spec.append(datafn.AnalyticOutput(k, tmp.name))
            spec = datafn.AnalyticSpec("script", input_spec, output_spec, script)
            if spec_adjust:
                spec_adjust(spec)
            print("test: created analytic spec")
            print(repr(spec))

            print("test: evaluating spec")
            actual_result = spec.evaluate()
            if actual_result._debug_log:
                print(actual_result._debug_log)
            actual_result._debug_log = None
            actual_result_str = actual_result.summary if actual_result.summary else ""
            if actual_result_str:
                print("test: --- start actual output ---")
                print(actual_result_str)
                print("test: --- end actual output ---")
            if callable(expected_result):
                expected = expected_result()
            else:
                expected = expected_result
            if expected:
                print("test: --- start expected output ---")
                print(expected)
                print("test: --- end expected output ---")
                self.assertEqual(self._process_log_message(expected), self._process_log_message(actual_result_str))
            else:
                print("test: no expected output")
                self.assertEqual(len(actual_result_str), 0)
            if not actual_result.success:
                print("test: data function has failed")
            self.assertEqual(actual_result.success, success)
            print("test: done evaluating spec")

            for output in output_spec:
                print(f"test: reading output variable '{output.name}' from file '{output.file}'")
                if os.path.isfile(output.file):
                    try:
                        data_frame = sbdf.import_data(output.file)
                        print(data_frame)
                        pdtest.assert_frame_equal(outputs[output.name], data_frame)
                        try:
                            print(f"test: table metadata:\n{data_frame.spotfire_table_metadata!r}")
                        except AttributeError:
                            pass
                        for col in data_frame.columns:
                            try:
                                print(f"test: column '{col}' metadata:\n{data_frame[col].spotfire_column_metadata!r}")
                            except AttributeError:
                                pass
                        self._assert_table_metadata_equal(outputs[output.name], data_frame)
                    except AssertionError:
                        raise
                    except BaseException:
                        print("\nWARNING: outputs did not match\n")
                else:
                    print("test: file doesn't exist")

    @staticmethod
    def _process_log_message(msg):
        # Remove line numbers from exception tracebacks
        msg = re.sub(", line \\d+,", ",", msg)
        # Remove temporary file names
        msg = re.sub(r"file [^ ]+\.sbdf", "file temp.sbdf", msg)

        return msg

    def _assert_table_metadata_equal(self, first, second, msg=None):
        """Test that two data frames have the same metadata."""
        # Test the table metadata
        try:
            first_meta = first.spotfire_table_metadata
        except AttributeError:
            first_meta = {}
        try:
            second_meta = second.spotfire_table_metadata
        except AttributeError:
            second_meta = {}
        self.assertEqual(first_meta, second_meta, msg)

        # Test the column metadata
        pdtest.assert_index_equal(first.columns, second.columns)
        for col in first.columns:
            try:
                first_colmeta = first[col].spotfire_column_metadata
            except AttributeError:
                first_colmeta = {}
            try:
                second_colmeta = second[col].spotfire_column_metadata
            except AttributeError:
                second_colmeta = {}
            self.assertEqual(first_colmeta, second_colmeta, msg)

    def test_value_input(self):
        """Test a value input."""
        out1_df = pd.DataFrame({"out1": [55]}, dtype="Int64")
        self._run_analytic("out1 = in1", {"in1": 55}, {"out1": out1_df}, True, None)

    def test_column_input(self):
        """Test a column input."""
        out1_df = pd.DataFrame({"in1": [1, 2, 3]}, dtype="Int64")
        self._run_analytic("out1 = in1", {"in1": [1, 2, 3]}, {"out1": out1_df}, True, None)

    def test_table_input(self):
        """Test a table input."""
        in1_df = pd.DataFrame({"x": pd.Series([22, 33], dtype="Int64"), "y": ["alpha", "bravo"]})
        self._run_analytic("out1 = in1", {"in1": pd.DataFrame(data=in1_df)}, {"out1": in1_df}, True, None)

    def test_exception(self):
        """Test a data function that raises an exception."""
        expected = _PythonVersionedExpectedValue("exception")
        self._run_analytic("raise TypeError('from test_exception')", {}, {}, False, expected)

    def test_syntax_error(self):
        """Test a data function that has a syntax error."""
        expected = _PythonVersionedExpectedValue("syntax_error")
        self._run_analytic("rais TypeError('from test_syntax_error')", {}, {}, False, expected)

    def test_syntax_error_b(self):
        """Test a data function that has a syntax error."""
        expected = _PythonVersionedExpectedValue("syntax_error_b")
        self._run_analytic("if + 42", {}, {}, False, expected)

    def test_syntax_error_c(self):
        """Run the syntax error test provided in pysrv122"""
        expected = _PythonVersionedExpectedValue("syntax_error_c")
        self._run_analytic("whille x%2 == 0:", {}, {}, False, expected)

    def test_indentation_error(self):
        """Run the syntax error test provided in pysrv122"""
        expected = _PythonVersionedExpectedValue("indentation_error")
        self._run_analytic("     print('You have entered an even number.')", {}, {}, False, expected)

    def test_print(self):
        """Test a data function that prints."""
        expected = _PythonVersionedExpectedValue("print")
        self._run_analytic("print(4*5)", {}, {}, True, expected)

    def test_simple_math(self):
        """Test doing some simple math on data frames."""
        in1_df = pd.DataFrame({"x": pd.Series([0, 1, 2, 3, 4, 5], dtype="Int64"),
                               "y": [4.5, 5.6, 6.7, 7.8, 8.9, 9.10]})
        out1_df = pd.DataFrame({"x": pd.Series([3, 4, 5, 6, 7, 8], dtype="Int64"),
                                "y": [7.5, 8.6, 9.7, 10.8, 11.9, 12.10]})
        self._run_analytic("out1 = in1 + in2", {"in1": in1_df, "in2": 3}, {"out1": out1_df}, True, None)

    def test_no_inputs(self):
        """Test a data function that has no inputs."""
        out1_df = pd.DataFrame({"out1": [4, 5, 6, 7, 8]}, dtype="Int64")
        self._run_analytic("out1 = list(range(4, 9))", {}, {"out1": out1_df}, True, None)

    def test_no_outputs(self):
        """Test a data function that has no outputs."""
        expected = _PythonVersionedExpectedValue("no_outputs")
        self._run_analytic("print(in1 * in2)", {"in1": 2, "in2": 3}, {}, True, expected)

    def test_range(self):
        """Test a data function that returns a range object."""
        out1_df = pd.DataFrame({"out1": [4, 5, 6, 7, 8]}, dtype="Int64")
        self._run_analytic("out1 = range(4, 9)", {}, {"out1": out1_df}, True, None)

    def test_set(self):
        """Test a data function that returns a set object."""
        out1_df = pd.DataFrame({"out1": [42, 100]}, dtype="Int64")
        self._run_analytic("out1 = {42, 100}", {}, {"out1": out1_df}, True, None)

    def test_exception_pysrv78(self):
        """Test That stdout is returned along with error message"""
        expected = _PythonVersionedExpectedValue("exception_pysrv78")
        self._run_analytic("""print("You should see this!")
print("And this!")
x = a*b
print("But not this.")""", {}, {}, False, expected)

    def test_warning_pysrv79(self):
        """Test that warnings are returned."""
        expected = _PythonVersionedExpectedValue("warning_pysrv79")
        self._run_analytic("""import warnings
warnings.simplefilter("always")
from warnings import warn
warn("This is a Warning", Warning)
warn("This is a UserWarning")
warn("This is a DeprecationWarning", DeprecationWarning)
warn("This is a SyntaxWarning", SyntaxWarning)
warn("This is a RuntimeWarning", RuntimeWarning)
warn("This is a FutureWarning", FutureWarning)
warn("This is a PendingDeprecationWarning", PendingDeprecationWarning)
warn("This is a ImportWarning", ImportWarning)
warn("This is a UnicodeWarning", UnicodeWarning)
warn("This is a BytesWarning", BytesWarning)
warn("This is a ResourceWarning", ResourceWarning)""", {}, {}, True, expected)

    def test_stderr_pysrv116(self):
        """Test that stdout is returned correctly with stderr"""
        expected = _PythonVersionedExpectedValue("stderr_pysrv116")
        self._run_analytic("""print("apa")
output = Exception("bepa")""", {}, {}, True, expected)

    def test_stderr_pysrv116_2(self):
        """Test that stdout is returned correctly with stderr"""
        expected = _PythonVersionedExpectedValue("stderr_pysrv116_2")
        self._run_analytic("""print("apa")
raise Exception("bepa")""", {}, {}, False, expected)

    def test_stderr_pysrv116_d(self):
        """Test that stdout is returned correctly with stderr"""
        expected = _PythonVersionedExpectedValue("stderr_pysrv116_d")
        self._run_analytic("""print("This code is really executed. (D)")
from pathlib import Path
output = int(10000000000000000000000000000000000000000000000000000000000000000)""", {}, {}, True, expected)

    def test_stderr_pysrv116_e(self):
        """Test that stdout is returned correctly with stderr"""
        expected = _PythonVersionedExpectedValue("stderr_pysrv116_e")
        self._run_analytic("""# Fifth example (like in the Description of this JIRA issue).
print("This code is really executed. (E)")
from pathlib import Path
output = Exception("apa")
print("(and this too) (E2)")""", {}, {}, True, expected)

    def test_output_not_defined(self):
        """Test when the expected outputs are not defined by the Python script."""
        expected = _PythonVersionedExpectedValue("output_not_defined")
        self._run_analytic("out2 = 1", {}, {"out1": None}, False, expected)

    def test_table_metadata(self):
        """Test that table metadata goes in and comes out."""
        in1_df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            in1_df.spotfire_table_metadata = {'bravo': ['The second letter of the phonetic alphabet.']}
        out_md_df = pd.DataFrame(in1_df.spotfire_table_metadata)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out_md_df.spotfire_table_metadata = {'a': ['Alpha']}
        expected = _PythonVersionedExpectedValue("table_metadata")
        self._run_analytic("""import pandas as pd
out_md = pd.DataFrame(in1.spotfire_table_metadata)
out_md.spotfire_table_metadata = {'a': ['Alpha']}""", {"in1": in1_df}, {"out_md": out_md_df}, True, expected)

    def test_column_metadata(self):
        """Test that column metadata goes in and comes out."""
        in1_df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
        in1_df['a'].spotfire_column_metadata = {'a': ['Alpha']}
        out1_df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0]})
        out1_df['a'].spotfire_column_metadata = {'a': ['Alpha']}
        out1_df['b'].spotfire_column_metadata = {'b': ['Bravo']}
        self._run_analytic("""import pandas as pd
import spotfire
b = pd.Series([1.0, 2.0, 3.0], name='b')
out1 = pd.concat([in1, b], axis=1)
spotfire.copy_metadata(in1, out1)
out1['b'].spotfire_column_metadata = {'b': ['Bravo']}""", {'in1': in1_df}, {'out1': out1_df}, True, None)

    def test_column_rename(self):
        """Test that a column renamed in a data function processes correctly."""
        in1_series = pd.Series([1.0, 2.0, 3.0], name="a")
        out1_df = pd.DataFrame({"b": [1.0, 2.0, 3.0]})
        self._run_analytic("""out1 = in1
out1 = out1.rename('b')""", {"in1": in1_series}, {"out1": out1_df}, True, None)

    def test_missing_input(self):
        """Test an unsupplied (NULL) input is registered as None"""
        expected = _PythonVersionedExpectedValue("missing_input")
        self._run_analytic("""print(in1)""", {"in1": None}, {}, True, expected)

    def test_nested_exception(self):
        """Test a nested exception is properly displayed"""
        expected = _PythonVersionedExpectedValue("nested_exception")
        self._run_analytic("""try:
    raise ValueError("root exception")
except Exception as e:
    raise TypeError("parent exception") from e""", {}, {}, False, expected)

    @staticmethod
    def _debug_log(spec):
        print("test: enabling debug")
        spec.enable_debug()

    def test_debug_log(self):
        """Test that the debug log can be enabled"""
        in1_df = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            in1_df.spotfire_table_metadata = {"tbl_1": [1]}
        in1_df["a"].spotfire_column_metadata = {"col_a_1": [10]}
        expected = _PythonVersionedExpectedValue("debug_log")
        self._run_analytic("in1", {"in1": in1_df}, {}, True, expected, spec_adjust=self._debug_log)

    def test_debug_log_omit(self):
        """Test that blank metadata is omitted from the debug log"""
        # All columns have no metadata
        in1_df = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
        expected = _PythonVersionedExpectedValue("debug_log_omit_1")
        self._run_analytic("in1", {"in1": in1_df}, {}, True, expected, spec_adjust=self._debug_log)

        # Some columns have no metadata
        in2_df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [6, 7, 8, 9, 10]})
        in2_df['b'].spotfire_column_metadata = {"col_b_1": [11]}
        expected = _PythonVersionedExpectedValue("debug_log_omit_2")
        self._run_analytic("in2", {"in2": in2_df}, {}, True, expected, spec_adjust=self._debug_log)

    def test_debug_log_truncate(self):
        """Test that column metadata is truncated properly"""
        in1_dict = {}
        for i in range(10000):
            in1_dict[f"num{i}"] = [i, i+1, i+2]
        in1_df = pd.DataFrame(in1_dict)
        for i in range(10000):
            in1_df[f"num{i}"].spotfire_column_metadata = {f"col_num{i}_1": [i]}
        expected = _PythonVersionedExpectedValue("debug_log_truncate")
        self._run_analytic("in1", {"in1": in1_df}, {}, True, expected, spec_adjust=self._debug_log)

    @staticmethod
    def _script_filename(spec, filename):
        print(f"test: setting script filename to '{filename}'")
        spec.set_script_filename(filename)

    def test_script_filename(self):
        """Test that setting a script filename works"""
        expected = _PythonVersionedExpectedValue("script_filename")
        self._run_analytic("raise ValueError('nope')", {}, {}, False, expected,
                           spec_adjust=lambda x: self._script_filename(x, "subdir/value_error.py"))

    def test_spotfire_inputs_dunder(self):
        """Test that the ``__spotfire_inputs__`` object works"""
        in1_df = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
        out_df = pd.DataFrame({"names": ["in1", "in2", "in3"], "types": ["table", "column", "value"]})
        self._run_analytic("""import pandas as pd
names = []
types = []
for i in __spotfire_inputs__:
  names.append(i.name)
  types.append(i.type)
out = pd.DataFrame({'names': names, 'types': types})""", {"in1": in1_df, "in2": [1, 2, 3, 4, 5], "in3": 0},
                           {"out": out_df}, True, None)

    def test_spotfire_outputs_dunder(self):
        """Test that the ``__spotfire_outputs__`` object works"""
        a_df = pd.DataFrame({"a": ["a", "b", "c", "d", "e"]})
        b_df = pd.DataFrame({"b": ["x"]})
        c_df = pd.DataFrame({"c": ["x"]})
        d_df = pd.DataFrame({"d": ["x"]})
        e_df = pd.DataFrame({"e": ["x"]})
        self._run_analytic("""a = [x.name for x in __spotfire_outputs__]
b = c = d = e = 'x'""", {}, {"a": a_df, "b": b_df, "c": c_df, "d": d_df, "e": e_df}, True, None)
