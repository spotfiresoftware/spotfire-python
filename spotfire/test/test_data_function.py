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


class DataFunctionTest(unittest.TestCase):
    """Unit tests for public functions in 'spotfire.data_function' module."""
    # pylint: disable=too-many-branches, too-many-statements, too-many-arguments, too-many-public-methods, line-too-long
    def _run_analytic(self, script, inputs, outputs, success, expected_result):
        """Run a full pass through the analytic protocol, and compare the output to the expected value."""
        # pylint: disable=protected-access,too-many-locals
        with _utils.TempFiles() as temp_files:
            input_spec = []
            for k in inputs:
                if inputs[k] is None:
                    in_type = "NULL"
                    print(f"test: missing input '{k}' ")
                    input_spec.append(datafn.AnalyticInput(k, in_type, None))
                    continue
                if isinstance(inputs[k], pd.DataFrame):
                    in_type = "table"
                else:
                    try:
                        in_type = "value" if len(inputs[k]) == 1 else "column"
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
            # spec.enable_debug()
            print("test: created analytic spec")
            print(repr(spec))

            print("test: evaluating spec")
            actual_result = spec.evaluate()
            if actual_result._debug_log:
                print(actual_result._debug_log)
            actual_result._debug_log = None
            actual_result_str = actual_result.summary
            if actual_result_str:
                print("test: --- start actual result ---")
                print(actual_result_str)
                print("test: --- end actual result ---")
            if callable(expected_result):
                expected = expected_result()
            else:
                expected = expected_result
            if expected:
                print("test: --- start expected result ---")
                print(expected)
                print("test: --- end expected result ---")
            self.assertEqual(re.sub(", line \\d+,", ",", expected), re.sub(", line \\d+,", ",", actual_result_str))
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
        self._run_analytic("out1 = in1", {"in1": 55}, {"out1": out1_df}, True, "")

    def test_column_input(self):
        """Test a column input."""
        out1_df = pd.DataFrame({"in1": [1, 2, 3]}, dtype="Int64")
        self._run_analytic("out1 = in1", {"in1": [1, 2, 3]}, {"out1": out1_df}, True, "")

    def test_table_input(self):
        """Test a table input."""
        in1_df = pd.DataFrame({"x": pd.Series([22, 33], dtype="Int64"), "y": ["alpha", "bravo"]})
        self._run_analytic("out1 = in1", {"in1": pd.DataFrame(data=in1_df)}, {"out1": in1_df}, True, "")

    def test_exception(self):
        """Test a data function that raises an exception."""
        self._run_analytic("raise TypeError('from test_exception')", {}, {}, False, """Error executing Python script:

TypeError: from test_exception

Traceback (most recent call last):
  File "data_function.py", line 324, in _execute_script
    exec(compiled_script, self.globals)
  File "<data_function>", line 1, in <module>
""")

    def test_syntax_error(self):
        """Test a data function that has a syntax error."""
        def expected():
            # pylint: disable=no-else-return
            if sys.version_info.major == 3 and sys.version_info.minor < 8:
                return """Error executing Python script:

  File "<data_function>", line 1
    rais TypeError('from test_syntax_error')
                 ^
SyntaxError: invalid syntax (<data_function>, line 1)

Traceback (most recent call last):
  File "data_function.py", in _compile_script
    self.compiled_script = compile(self.script, '<data_function>', 'exec')
"""
            elif sys.version_info.major == 3 and sys.version_info.minor < 11:
                return """Error executing Python script:

  File "<data_function>", line 1
    rais TypeError('from test_syntax_error')
         ^
SyntaxError: invalid syntax (<data_function>, line 1)

Traceback (most recent call last):
  File "data_function.py", in _compile_script
    self.compiled_script = compile(self.script, '<data_function>', 'exec')
"""
            else:
                return """Error executing Python script:

  File "<data_function>", line 1
    rais TypeError('from test_syntax_error')
         ^
SyntaxError: invalid syntax (<data_function>, line 1)

Traceback (most recent call last):
  File "data_function.py", in _compile_script
    self.compiled_script = compile(self.script, '<data_function>', 'exec')
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

        self._run_analytic("rais TypeError('from test_syntax_error')", {}, {}, False, expected)

    def test_syntax_error_b(self):
        """Test a data function that has a syntax error."""
        def expected():
            # pylint: disable=no-else-return
            if sys.version_info.major == 3 and sys.version_info.minor < 10:
                return """Error executing Python script:

  File "<data_function>", line 1
    if + 42
          ^
SyntaxError: invalid syntax (<data_function>, line 1)

Traceback (most recent call last):
  File "data_function.py", in _compile_script
    self.compiled_script = compile(self.script, '<data_function>', 'exec')
"""
            elif sys.version_info.major == 3 and sys.version_info.minor < 11:
                return """Error executing Python script:

  File "<data_function>", line 1
    if + 42
          ^
SyntaxError: expected ':' (<data_function>, line 1)

Traceback (most recent call last):
  File "data_function.py", in _compile_script
    self.compiled_script = compile(self.script, '<data_function>', 'exec')
"""
            else:
                return """Error executing Python script:

  File "<data_function>", line 1
    if + 42
          ^
SyntaxError: expected ':' (<data_function>, line 1)

Traceback (most recent call last):
  File "data_function.py", in _compile_script
    self.compiled_script = compile(self.script, '<data_function>', 'exec')
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

        self._run_analytic("if + 42", {}, {}, False, expected)

    def test_syntax_error_c(self):
        """Run the syntax error test provided in pysrv122"""
        def expected():
            # pylint: disable=no-else-return
            if sys.version_info.major == 3 and sys.version_info.minor < 11:
                return """Error executing Python script:

  File "<data_function>", line 1
    whille x%2 == 0:
           ^
SyntaxError: invalid syntax (<data_function>, line 1)

Traceback (most recent call last):
  File "data_function.py", in _compile_script
    self.compiled_script = compile(self.script, '<data_function>', 'exec')
"""
            else:
                return """Error executing Python script:

  File "<data_function>", line 1
    whille x%2 == 0:
           ^
SyntaxError: invalid syntax (<data_function>, line 1)

Traceback (most recent call last):
  File "data_function.py", in _compile_script
    self.compiled_script = compile(self.script, '<data_function>', 'exec')
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

        self._run_analytic("whille x%2 == 0:", {}, {}, False, expected)

    def test_indentation_error(self):
        """Run the syntax error test provided in pysrv122"""
        def expected():
            # pylint: disable=no-else-return
            if sys.version_info.major == 3 and sys.version_info.minor < 11:
                return """Error executing Python script:

  File "<data_function>", line 1
         print('You have entered an even number.')
         ^
IndentationError: unexpected indent (<data_function>, line 1)

Traceback (most recent call last):
  File "data_function.py", in _compile_script
    self.compiled_script = compile(self.script, '<data_function>', 'exec')
"""
            else:
                return """Error executing Python script:

  File "<data_function>", line 1
         print('You have entered an even number.')
         ^
IndentationError: unexpected indent (<data_function>, line 1)

Traceback (most recent call last):
  File "data_function.py", in _compile_script
    self.compiled_script = compile(self.script, '<data_function>', 'exec')
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

        self._run_analytic("     print('You have entered an even number.')", {}, {}, False, expected)

    def test_print(self):
        """Test a data function that prints."""
        self._run_analytic("print(4*5)", {}, {}, True, """
Standard output:
20
""")

    def test_simple_math(self):
        """Test doing some simple math on data frames."""
        in1_df = pd.DataFrame({"x": pd.Series([0, 1, 2, 3, 4, 5], dtype="Int64"),
                               "y": [4.5, 5.6, 6.7, 7.8, 8.9, 9.10]})
        out1_df = pd.DataFrame({"x": pd.Series([3, 4, 5, 6, 7, 8], dtype="Int64"),
                                "y": [7.5, 8.6, 9.7, 10.8, 11.9, 12.10]})
        self._run_analytic("out1 = in1 + in2", {"in1": in1_df, "in2": 3}, {"out1": out1_df}, True, "")

    def test_no_inputs(self):
        """Test a data function that has no inputs."""
        out1_df = pd.DataFrame({"out1": [4, 5, 6, 7, 8]}, dtype="Int64")
        self._run_analytic("out1 = list(range(4, 9))", {}, {"out1": out1_df}, True, "")

    def test_no_outputs(self):
        """Test a data function that has no outputs."""
        self._run_analytic("print(in1 * in2)", {"in1": 2, "in2": 3}, {}, True, """
Standard output:
6
""")

    def test_range(self):
        """Test a data function that returns a range object."""
        out1_df = pd.DataFrame({"out1": [4, 5, 6, 7, 8]}, dtype="Int64")
        self._run_analytic("out1 = range(4, 9)", {}, {"out1": out1_df}, True, "")

    def test_set(self):
        """Test a data function that returns a set object."""
        out1_df = pd.DataFrame({"out1": [42, 100]}, dtype="Int64")
        self._run_analytic("out1 = {42, 100}", {}, {"out1": out1_df}, True, "")

    def test_exception_pysrv78(self):
        """Test That stdout is returned along with error message"""
        self._run_analytic("""print("You should see this!")
print("And this!")
x = a*b
print("But not this.")""", {}, {}, False, """Error executing Python script:

NameError: name 'a' is not defined

Traceback (most recent call last):
  File "data_function.py", line 324, in _execute_script
    exec(compiled_script, self.globals)
  File "<data_function>", line 3, in <module>

Standard output:
You should see this!
And this!
""")

    def test_warning_pysrv79(self):
        """Test that warnings are returned."""
        def expected():
            # pylint: disable=no-else-return
            if sys.version_info.major == 3 and sys.version_info.minor < 8:
                return """
Standard error:
<string>:4: Warning: This is a Warning
<string>:5: UserWarning: This is a UserWarning
<string>:6: DeprecationWarning: This is a DeprecationWarning
<string>:7: SyntaxWarning: This is a SyntaxWarning
<string>:8: RuntimeWarning: This is a RuntimeWarning
<string>:9: FutureWarning: This is a FutureWarning
<string>:10: PendingDeprecationWarning: This is a PendingDeprecationWarning
<string>:11: ImportWarning: This is a ImportWarning
<string>:12: UnicodeWarning: This is a UnicodeWarning
<string>:13: BytesWarning: This is a BytesWarning
<string>:14: ResourceWarning: This is a ResourceWarning
"""
            else:
                return """
Standard error:
<data_function>:4: Warning: This is a Warning
<data_function>:5: UserWarning: This is a UserWarning
<data_function>:6: DeprecationWarning: This is a DeprecationWarning
<data_function>:7: SyntaxWarning: This is a SyntaxWarning
<data_function>:8: RuntimeWarning: This is a RuntimeWarning
<data_function>:9: FutureWarning: This is a FutureWarning
<data_function>:10: PendingDeprecationWarning: This is a PendingDeprecationWarning
<data_function>:11: ImportWarning: This is a ImportWarning
<data_function>:12: UnicodeWarning: This is a UnicodeWarning
<data_function>:13: BytesWarning: This is a BytesWarning
<data_function>:14: ResourceWarning: This is a ResourceWarning
"""

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
        self._run_analytic("""print("apa")
output = Exception("bepa")""", {}, {}, True, """
Standard output:
apa
""")

    def test_stderr_pysrv116_2(self):
        """Test that stdout is returned correctly with stderr"""
        self._run_analytic("""print("apa")
raise Exception("bepa")""", {}, {}, False, """Error executing Python script:

Exception: bepa

Traceback (most recent call last):
  File "data_function.py", line 324, in _execute_script
    exec(compiled_script, self.globals)
  File "<data_function>", line 2, in <module>

Standard output:
apa
""")

    def test_stderr_pysrv116_d(self):
        """Test that stdout is returned correctly with stderr"""
        self._run_analytic("""print("This code is really executed. (D)")
from pathlib import Path
output = int(10000000000000000000000000000000000000000000000000000000000000000)""", {}, {}, True, """
Standard output:
This code is really executed. (D)
""")

    def test_stderr_pysrv116_e(self):
        """Test that stdout is returned correctly with stderr"""
        self._run_analytic("""# Fifth example (like in the Description of this JIRA issue).
print("This code is really executed. (E)")
from pathlib import Path
output = Exception("apa")
print("(and this too) (E2)")""", {}, {}, True, """
Standard output:
This code is really executed. (E)
(and this too) (E2)
""")

    def test_output_not_defined(self):
        """Test when the expected outputs are not defined by the Python script."""

        self._run_analytic("out2 = 1", {}, {"out1": None}, False, """Error executing Python script:

spotfire.data_function.DataFunctionError: Output variable 'out1' was not defined

Traceback (most recent call last):
  File "data_function.py", line 255, in evaluate
    self._write_outputs(result)
  File "data_function.py", line 346, in _write_outputs
    raise DataFunctionError(f"Output variable '{output.name}' was not defined")
""")

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

        def expected():
            # pylint: disable=no-else-return
            if sys.version_info.major == 3 and sys.version_info.minor < 8:
                return """
Standard error:
<string>:3: UserWarning: Pandas doesn't allow columns to be created via a new attribute name - see https://pandas.pydata.org/pandas-docs/stable/indexing.html#attribute-access
"""
            else:
                return """
Standard error:
<data_function>:3: UserWarning: Pandas doesn't allow columns to be created via a new attribute name - see https://pandas.pydata.org/pandas-docs/stable/indexing.html#attribute-access
"""

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
out1['b'].spotfire_column_metadata = {'b': ['Bravo']}""", {'in1': in1_df}, {'out1': out1_df}, True, "")

    def test_column_rename(self):
        """Test that a column renamed in a data function processes correctly."""
        in1_series = pd.Series([1.0, 2.0, 3.0], name="a")
        out1_df = pd.DataFrame({"b": [1.0, 2.0, 3.0]})
        self._run_analytic("""out1 = in1
out1 = out1.rename('b')""", {"in1": in1_series}, {"out1": out1_df}, True, "")

    def test_missing_input(self):
        """Test an unsupplied (NULL) input is registered as None"""
        self._run_analytic("""print(in1)""", {"in1": None}, {}, True, """
Standard output:
None
""")

    def test_nested_exception(self):
        """Test a nested exception is properly displayed"""
        self._run_analytic("""try:
    raise ValueError("root exception")
except Exception as e:
    raise TypeError("parent exception") from e""", {}, {}, False, """Error executing Python script:

TypeError: parent exception

Traceback (most recent call last):
  File "data_function.py", in _execute_script
    exec(compiled_script, self.globals)
  File "<data_function>", in <module>

The following exception was the direct cause of the above exception:

Traceback (most recent call last):
  File "<data_function>", in <module>
ValueError: root exception
""")
