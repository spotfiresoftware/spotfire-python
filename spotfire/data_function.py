# Copyright © 2021. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Automatically manage the protocol between Spotfire and a data function written in Python."""

import io
import os.path
import pprint
import sys
import traceback
import types
import typing
import re

from spotfire import sbdf, _utils


_ExceptionInfo = typing.Union[
    tuple[type[BaseException], BaseException, types.TracebackType],
    tuple[None, None, None]
]
_Globals = dict[str, typing.Any]
_LogFunction = typing.Callable[[str], None]


_COLUMN_METADATA_TRUNCATE_THRESHOLD = 80000


def _bad_string(str_: typing.Any) -> bool:
    return not isinstance(str_, str)


class _OutputCapture:
    _old_stdout: typing.Optional[typing.TextIO]
    _old_stderr: typing.Optional[typing.TextIO]

    def __init__(self) -> None:
        self._entered = False
        self._stdout = io.StringIO()
        self._stderr = io.StringIO()
        self._old_stdout = None
        self._old_stderr = None

    def __enter__(self):
        if self._entered:
            raise ValueError("cannot reenter output capture")
        self._entered = True
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._entered:
            raise ValueError("cannot exit unentered output capture")
        self._entered = False
        if self._old_stdout:
            sys.stdout = self._old_stdout
        if self._old_stderr:
            sys.stderr = self._old_stderr
        self._old_stdout = None
        self._old_stderr = None

    def get_stdout(self) -> typing.Optional[str]:
        """Return the captured standard output stream.

        :return: string containing the output stream, or `None` if no output was captured
        """
        if self._stdout.tell():
            return self._stdout.getvalue()
        return None

    def get_stderr(self) -> typing.Optional[str]:
        """Return the captured standard error stream.

        :return: string containing the error stream, or `None` if no output was captured
        """
        if self._stderr.tell():
            return self._stderr.getvalue()
        return None


class AnalyticInput:
    """Represents an input to an analytic spec."""

    def __init__(self, name: str, input_type: str, file: str) -> None:
        """Create an input to an analytic spec.

        :param name: the name of the input
        :param input_type: whether the input is a ``table``, a ``column``, or a ``value``
        :param file: the filename of the SBDF file that contains the data to read into this input
        """
        self._name = name
        self._type = input_type
        self._file = file

    def __repr__(self) -> str:
        return f"{_utils.type_name(type(self))}({self._name!r}, {self._type!r}, {self._file!r})"

    @property
    def name(self) -> str:
        """Get the name of this input."""
        return self._name

    @property
    def type(self) -> str:
        """Get the type of this input.  Will be one of ``table``, ``column``, or ``value``."""
        return self._type

    @property
    def file(self) -> str:
        """Get the filename of the SBDF file to deserialize this input from."""
        return self._file

    def read(self, globals_dict: _Globals, debug_fn: _LogFunction) -> None:
        """Read an input from the corresponding SBDF file into the dict that comprises the set of globals.

        :param globals_dict: dict containing the global variables for the data function
        :param debug_fn: logging function for debug messages
        """
        # pylint: disable=too-many-branches

        if self._type == "NULL":
            debug_fn(f"assigning missing '{self._name}' as None")
            globals_dict[self._name] = None
            return
        debug_fn(f"assigning {self._type} '{self._name}' from file {self._file}")
        dataframe = sbdf.import_data(self._file)
        debug_fn(f"read {dataframe.shape[0]} rows {dataframe.shape[1]} columns")

        # Table metadata
        try:
            if dataframe.spotfire_table_metadata:
                table_meta = f"\n {pprint.pformat(dataframe.spotfire_table_metadata)}"
            else:
                table_meta = " (no table metadata present)"
        except AttributeError:
            table_meta = " (no table metadata present)"
        debug_fn(f"table metadata:{table_meta}")

        # Column metadata
        column_blank = False
        pretty_column = io.StringIO()
        for col in dataframe.columns:
            try:
                if pretty_column.tell() > _COLUMN_METADATA_TRUNCATE_THRESHOLD:
                    pretty_column.write("\n (truncated due to length)")
                    break
                if dataframe[col].spotfire_column_metadata:
                    pretty_column.write(f"\n {col}: {pprint.pformat(dataframe[col].spotfire_column_metadata)}")
                else:
                    column_blank = True
            except AttributeError:
                column_blank = True
        if pretty_column.tell():
            column_meta = pretty_column.getvalue()
        else:
            column_meta = " (no column metadata present)"
            column_blank = False
        if column_blank:
            column_meta += "\n (columns without metadata have been omitted)"
        debug_fn(f"column metadata:{column_meta}")

        # Argument type
        if self._type == "column":
            dataframe = dataframe[dataframe.columns[0]]
        if self._type == "value":
            value = dataframe.at[0, dataframe.columns[0]]
            if type(value).__module__ == "numpy":
                dataframe = value.tolist()
            elif type(value).__module__ == "pandas._libs.tslibs.timedeltas":
                dataframe = value.to_pytimedelta()
            elif type(value).__module__ == "pandas._libs.tslibs.timestamps":
                dataframe = value.to_pydatetime()
            elif type(value).__module__ == "pandas._libs.tslibs.nattype":
                dataframe = None
            else:
                dataframe = value

        # Store to global dict
        globals_dict[self._name] = dataframe


class AnalyticOutput:
    """Represents an output from an analytic spec."""

    def __init__(self, name: str, file: str) -> None:
        """Create an output from an analytic spec.

        :param name: the name of the output
        :param file: the filename of the SBDF file that will be created by writing from this output
        """
        self._name = name
        self._file = file

    def __repr__(self) -> str:
        return f"{_utils.type_name(type(self))}({self._name!r}, {self._file!r})"

    @property
    def name(self) -> str:
        """Get the name of this output."""
        return self._name

    @property
    def file(self) -> str:
        """Get the filename of the SBDF file to serialize this output to."""
        return self._file

    def write(self, globals_dict: _Globals, debug_fn: _LogFunction) -> None:
        """Write an output from the dict that comprises the set of globals file into the corresponding SBDF.

        :param globals_dict: dict containing the global variables from the data function
        :param debug_fn: logging function for debug messages
        """
        debug_fn(f"returning '{self._name}' as file {self._file}")
        sbdf.export_data(globals_dict[self._name], self._file, default_column_name=self._name)


class AnalyticResult:
    """Represents the results of evaluating an AnalyticSpec object."""
    std_err_out: typing.Optional[str]
    summary: typing.Optional[str]
    _exc_info: _ExceptionInfo
    _debug_log: typing.Optional[str]

    def __init__(self, capture: _OutputCapture) -> None:
        self.success = True
        self.has_stderr = False
        self.std_err_out = None
        self.summary = None
        self._exc_info = (None, None, None)
        self._capture = capture
        self._debug_log = None

    def fail_with_exception(self, exc_info: _ExceptionInfo) -> None:
        """Set this result as failed with an exception."""
        self.fail()
        self._exc_info = exc_info

    def fail(self) -> None:
        """Set the result to Failed."""
        self.success = False

    def get_capture(self) -> _OutputCapture:
        """Get the captured standard output and error of this result."""
        return self._capture

    def set_debug_log(self, log: str) -> None:
        """Set the debug log that generated this result."""
        self._debug_log = log

    def get_debug_log(self) -> typing.Optional[str]:
        """Get the debug log for this result."""
        return self._debug_log

    def get_exc_info(self) -> _ExceptionInfo:
        """Get the exception information."""
        return self._exc_info


class AnalyticSpec:
    """Represents an analytic spec used to process a data function."""
    # pylint: disable=too-many-instance-attributes
    globals: _Globals
    compiled_script: typing.Optional[types.CodeType]

    def __init__(self, analytic_type: str, inputs: list[AnalyticInput], outputs: list[AnalyticOutput],
                 script: str) -> None:
        """Create an analytic spec.

        :param analytic_type: the type of data function being specified; currently only ``script`` is supported
        :param inputs: list of AnalyticInput objects describing inputs to this data function
        :param outputs: list of AnalyticOutput objects describing outputs from this data function
        :param script: the Python script code this data function will run
        """
        self.analytic_type = analytic_type
        self.inputs = inputs if isinstance(inputs, list) else []
        self.outputs = outputs if isinstance(outputs, list) else []
        self.script = script
        self.debug_enabled = False
        self.script_filename = '<data_function>'
        self.globals = {
            '__builtins__': __builtins__,
            '__spotfire_inputs__': tuple(inputs),
            '__spotfire_outputs__': tuple(outputs),
        }
        self.log = io.StringIO()
        self.compiled_script = None

    def __repr__(self) -> str:
        return f"{_utils.type_name(type(self))}({self.analytic_type!r}, \
            {self.inputs!r}, {self.outputs!r}, {self.script!r})"

    def enable_debug(self) -> None:
        """Turn on the printing of debugging messages."""
        self.debug_enabled = True

    def set_script_filename(self, filename: str) -> None:
        """Set the filename of the script when this spec object is used for script debugging.

        :param filename: the filename of the script
        """
        self.script_filename = filename

    def debug(self, message: str) -> None:
        """Output a debugging message to the log if debug is enabled.

        :param message: the debugging message to print
        """
        if self.debug_enabled:
            self.log.write(f"debug: {message}\n")

    def debug_write_script(self) -> None:
        """Output the current script to the debugging log."""
        if self.debug_enabled:
            self.log.write(self.script)
            self.log.write("\n")

    def evaluate(self) -> AnalyticResult:
        """Run the script in the analytic spec and process the results.

        :return: whether the data function was evaluated successfully, the text output of the data function or an error
        message describing why the data function failed, and the exception information and stack trace if the data
        function raised any errors
        """
        self.debug("start evaluate")

        # noinspection PyBroadException
        try:
            with _OutputCapture() as capture:
                result = AnalyticResult(capture)

                # parse and compile the script first
                self._compile_script(result)
                if not result.success:
                    return self._summarize(result)

                # read inputs
                self._read_inputs(result)
                if not result.success:
                    return self._summarize(result)

                # execute the script
                if self.compiled_script:
                    self._execute_script(self.compiled_script, result)
                if not result.success:
                    return self._summarize(result)

                # write outputs
                self._write_outputs(result)
                if not result.success:
                    return self._summarize(result)

                self.debug("end evaluate")

                result.success = True

            # summarize the evaluation
            self._summarize(result)
        except BaseException:
            self.debug("There was an unhandled exception during evaluation.")
            result.fail_with_exception(sys.exc_info())
            self._summarize(result)
        # return the result object.
        return result

    def _compile_script(self, result: AnalyticResult) -> None:
        """"Parse and compile the script"""
        # noinspection PyBroadException
        try:
            self.compiled_script = compile(self.script, self.script_filename, 'exec')
        except BaseException:
            self.debug("script can't be parsed:")
            self.debug("--- script ---")
            self.debug_write_script()
            self.debug("--- script ---")
            result.fail_with_exception(sys.exc_info())

    def _read_inputs(self, result: AnalyticResult) -> None:
        """read inputs"""
        self.debug(f"reading {len(self.inputs)} input variables")
        for i, input_ in enumerate(self.inputs):
            if _bad_string(input_.name) or not input_.name:
                self.debug(f"input {i}: bad input variable name - skipped")
                continue
            if input_.type != "NULL" and (_bad_string(input_.file) or not input_.file):
                self.debug(f"input '{input_.name}': bad file name - skipped")
                continue
            if input_.type != "NULL" and not os.path.isfile(input_.file):
                self.debug(f"input '{input_.name}': non-existent file - skipped")
                continue
            try:
                input_.read(self.globals, self.debug)
            except sbdf.SBDFError as exc:
                self.debug(f"error reading input variable '{input_.name}' from file '{input_.file}': {str(exc)}")
                result.fail_with_exception(sys.exc_info())
                return
        self.debug(f"done reading {len(self.inputs)} input variables")
        return

    def _execute_script(self, compiled_script: types.CodeType, result: AnalyticResult) -> None:
        """execute the script"""
        # pylint: disable=exec-used
        self.debug("executing script")
        self.debug("--- script ---")
        self.debug_write_script()
        self.debug("--- script ---")
        if _bad_string(self.analytic_type):
            self.analytic_type = "script"
        self.debug(f"analytic_type is '{self.analytic_type}'")
        if self.analytic_type == "script":
            # noinspection PyBroadException
            try:
                exec(compiled_script, self.globals)
            except BaseException:
                result.fail_with_exception(sys.exc_info())
                return
        elif self.analytic_type == "aggregationScript":
            self.debug("aggregation scripts are not supported")
            raise DataFunctionError("Aggregation scripts are not supported.")
        self.debug("done executing script")
        return

    def _write_outputs(self, result: AnalyticResult) -> None:
        """write outputs"""
        self.debug(f"writing {len(self.outputs)} output variables")
        for i, output in enumerate(self.outputs):
            if _bad_string(output.name) or not output.name:
                self.debug(f"output {i}: bad output variable name - skipped")
                continue
            if _bad_string(output.file) or not output.file:
                self.debug(f"output '{output.name}': bad file name - skipped")
                continue
            if output.name not in self.globals:
                self.debug(f"output variable '{output.name}' not defined in globals")
                raise DataFunctionError(f"Output variable '{output.name}' was not defined")
            # noinspection PyBroadException
            try:
                output.write(self.globals, self.debug)
            except BaseException:
                result.fail_with_exception(sys.exc_info())
        self.debug(f"done writing {len(self.outputs)} output variables")

    def _summarize(self, result: AnalyticResult) -> AnalyticResult:
        """Perform final summary actions and return the result object."""
        result.set_debug_log(self.log.getvalue())
        self._create_summary(result)
        return result

    def _create_summary(self, result: AnalyticResult) -> None:
        """Format the result as a string that can be displayed to the user and provide access to stderr."""
        buf = io.StringIO()
        # noinspection PyBroadException
        # pylint: disable=too-many-nested-blocks
        try:
            if not result.success:
                buf.write("Error executing Python script:\n\n")
                exc_info = result.get_exc_info()
                if exc_info[0] and exc_info[1] and exc_info[2]:
                    # noinspection PyBroadException
                    try:
                        # If it was a syntax error, show the text with the caret
                        exc_type = _utils.type_name(exc_info[0])
                        if exc_type in ("SyntaxError", "IndentationError", "TabError"):
                            syntax_error = traceback.TracebackException(exc_info[0], exc_info[1], exc_info[2])
                            buf.write(f'  File "{syntax_error.filename}", line {syntax_error.lineno}\n')
                            buf.write(f"    {syntax_error.text}")
                            # sometimes the offset is wrong, placing the caret before or after the text.
                            spacer = syntax_error.offset - 1
                            if exc_type == "IndentationError":
                                spacer += 1
                            if len(syntax_error.text) == syntax_error.offset:
                                spacer -= 1
                            offset = " " * spacer
                            buf.write(f"    {offset}^\n")
                        buf.write(f"{exc_type}: {exc_info[1]}\n\n")
                        self._create_traceback(buf, exc_info[1])
                    except BaseException:
                        buf.write(f"\nCould not retrieve stacktrace: {traceback.format_exc()}")
            if result.get_capture() is not None:
                out = result.get_capture().get_stdout()
                if out:
                    buf.write("\nStandard output:\n")
                    buf.write(out)
                result.std_err_out = result.get_capture().get_stderr()
                if result.std_err_out:
                    result.has_stderr = True
                    buf.write("\nStandard error:\n")
                    buf.write(result.std_err_out)
            if self.debug_enabled:
                debug_log = result.get_debug_log()
                if debug_log:
                    buf.write("\nDebug log:\n")
                    buf.write(debug_log)
        except SystemError as err:
            buf.write(str(err))
        result.summary = buf.getvalue()

    def _create_traceback(self, buf, exc_val):
        """Format a traceback as a string that can be displayed to the user."""
        # print the header
        buf.write("Traceback (most recent call last):\n")

        # get the StackSummary
        tb_frames = traceback.extract_tb(exc_val.__traceback__)
        # get the FrameSummary objects from the StackSummary
        lines = traceback.format_list(tb_frames)

        # trim the path from the filename
        def shorten(match):
            """trim the path from the exception filename"""
            return f'File "{os.path.basename(match.group(1))}"'

        lines = [re.sub(r'File "([^"]+)"', shorten, line, count=1) for line in lines]

        # print the lines
        buf.writelines(lines)

        # recurse if we have a cause
        if exc_val.__cause__:
            buf.write("\nThe following exception was the direct cause of the above exception:\n\n")
            exc_cause_type = _utils.type_name(type(exc_val.__cause__))
            self._create_traceback(buf, exc_val.__cause__)
            buf.write(f"{exc_cause_type}: {exc_val.__cause__}\n")


# Exceptions

class DataFunctionError(Exception):
    """An exception that is raised to indicate a problem with the Data Function."""
