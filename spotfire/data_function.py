# Copyright © 2021. TIBCO Software Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Automatically manage the protocol between Spotfire and a data function written in Python."""

import io
import os.path
import pprint
import sys
import traceback
import typing
import re

from spotfire import sbdf, _utils


def _bad_string(str_: typing.Any) -> bool:
    return not isinstance(str_, str)


class _OutputCapture:
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
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr
        self._old_stdout = None
        self._old_stderr = None

    def get_stdout(self) -> typing.Optional[str]:
        """Return the captured standard output stream.

        :return: string containing the output stream, or `None` if no output was captured
        """
        return None if self._stdout.tell() == 0 else self._stdout.getvalue()

    def get_stderr(self) -> typing.Optional[str]:
        """Return the captured standard error stream.

        :return: string containing the error stream, or `None` if no output was captured
        """
        return None if self._stderr.tell() == 0 else self._stderr.getvalue()


class AnalyticInput:
    """Represents an input to an analytic spec."""

    def __init__(self, name: str, input_type: str, file: str) -> None:
        """Create an input to an analytic spec.

        :param name: the name of the input
        :param input_type: whether the input is a ``table``, a ``column``, or a ``value``
        :param file: the filename of the SBDF file that contains the data to read into this input
        """
        self.name = name
        self.type = input_type
        self.file = file

    def __repr__(self) -> str:
        return f"{_utils.type_name(type(self))}({self.name!r}, {self.type!r}, {self.file!r})"

    def read(self, globals_dict: typing.Dict[str, typing.Any], debug_fn: typing.Callable[[str], None]) -> None:
        """Read an input from the corresponding SBDF file into the dict that comprises the set of globals.

        :param globals_dict: dict containing the global variables for the data function
        :param debug_fn: logging function for debug messages
        """
        if self.type == "NULL":
            debug_fn(f"assigning missing '{self.name}' as None")
            globals_dict[self.name] = None
            return
        debug_fn(f"assigning {self.type} '{self.name}' from file {self.file}")
        dataframe = sbdf.import_data(self.file)
        debug_fn(f"read {dataframe.shape[0]} rows {dataframe.shape[1]} columns")
        try:
            table_meta = dataframe.spotfire_table_metadata
        except AttributeError:
            table_meta = {}
        column_meta = {}
        for col in dataframe.columns:
            try:
                column_meta[col] = dataframe[col].spotfire_column_metadata
            except AttributeError:
                column_meta[col] = {}
        pretty_table = io.StringIO()
        pretty_column = io.StringIO()
        pprint.pprint(table_meta, pretty_table)
        pprint.pprint(column_meta, pretty_column)
        debug_fn(f"table metadata: \n {pretty_table.getvalue()}")
        debug_fn(f"column metadata: \n {pretty_column.getvalue()}")
        if self.type == "column":
            dataframe = dataframe[dataframe.columns[0]]
        if self.type == "value":
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
        globals_dict[self.name] = dataframe


class AnalyticOutput:
    """Represents an output from an analytic spec."""

    def __init__(self, name: str, file: str) -> None:
        """Create an output from an analytic spec.

        :param name: the name of the output
        :param file: the filename of the SBDF file that will be created by writing from this output
        """
        self.name = name
        self.file = file

    def __repr__(self) -> str:
        return f"{_utils.type_name(type(self))}({self.name!r}, {self.file!r})"

    def write(self, globals_dict: typing.Dict[str, typing.Any], debug_fn: typing.Callable[[str], None]) -> None:
        """Write an output from the dict that comprises the set of globals file into the corresponding SBDF.

        :param globals_dict: dict containing the global variables from the data function
        :param debug_fn: logging function for debug messages
        """
        debug_fn(f"returning '{self.name}' as file {self.file}")
        sbdf.export_data(globals_dict[self.name], self.file, default_column_name=self.name)


class AnalyticResult:
    """Represents the results of evaluating an AnalyticSpec object."""

    # pylint: disable=too-many-instance-attributes
    # Eight is reasonable in this case.

    def __init__(self) -> None:
        self.success = True
        self.has_stderr = False
        self.std_err_out = None
        self.summary = None
        self._exc_info = (type(None), None, None)
        self._capture = None
        self._debug_log = None

    def fail_with_exception(self, exc_info) -> None:
        """Set this result as failed with an exception."""
        self.fail()
        self._exc_info = exc_info

    def fail(self) -> None:
        """Set the result to Failed."""
        self.success = False

    def set_capture(self, capture: _OutputCapture) -> None:
        """Set the captured standard output and error of this result."""
        self._capture = capture

    def get_capture(self) -> _OutputCapture:
        """Get the captured standard output and error of this result."""
        return self._capture

    def set_debug_log(self, log: str) -> None:
        """Set the debug log that generated this result."""
        self._debug_log = log

    def get_debug_log(self) -> str:
        """Get the debug log for this result."""
        return self._debug_log

    def get_exc_info(self):
        """Get the exception information."""
        return self._exc_info


class AnalyticSpec:
    """Represents an analytic spec used to process a data function."""

    # pylint: disable=too-many-instance-attributes

    def __init__(self, analytic_type: str, inputs: typing.List[AnalyticInput], outputs: typing.List[AnalyticOutput],
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
        self.globals = dict(__builtins__=__builtins__)
        self.log = io.StringIO()
        self.compiled_script = None

    def __repr__(self) -> str:
        return f"{_utils.type_name(type(self))}({self.analytic_type!r}, \
            {self.inputs!r}, {self.outputs!r}, {self.script!r})"

    def enable_debug(self) -> None:
        """Turn on the printing of debugging messages."""
        self.debug_enabled = True

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
        """Run the script in the in the analytic spec and process the results.

        :return: whether the data function was evaluated successfully, the text output of the data function or an error
        message describing why the data function failed, and the exception information and stack trace if the data
        function raised any errors
        """
        self.debug("start evaluate")
        result = AnalyticResult()

        # noinspection PyBroadException
        try:
            with _OutputCapture() as capture:
                result.set_capture(capture)

                # parse and compile the script first
                self._compile_script(result)
                if not result.success:
                    return self._summarize(result)

                # read inputs
                self._read_inputs(result)
                if not result.success:
                    return self._summarize(result)

                # execute the script
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
            self.compiled_script = compile(self.script, '<data_function>', 'exec')
        except BaseException:
            self.debug("script can't be parsed:")
            self.debug("--- script ---")
            self.debug_write_script()
            self.debug("--- script ---")
            result.fail_with_exception(sys.exc_info())
            return

    def _read_inputs(self, result: AnalyticResult) -> None:
        """read inputs"""
        self.debug(f"reading {len(self.inputs)} input variables")
        for i, input_ in enumerate(self.inputs):
            if _bad_string(input_.name) or input_.name == "":
                self.debug(f"input {i}: bad input variable name - skipped")
                continue
            if input_.type != "NULL" and (_bad_string(input_.file) or input_.file == ""):
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

    def _execute_script(self, compiled_script: typing.Any, result: AnalyticResult) -> None:
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
            if _bad_string(output.name) or output.name == "":
                self.debug(f"output {i}: bad output variable name - skipped")
                continue
            if _bad_string(output.file) or output.file == "":
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
                if result.get_exc_info()[2] is not None:
                    # noinspection PyBroadException
                    try:
                        # If it was a syntax error, show the text with the caret
                        exc_type = _utils.type_name(result.get_exc_info()[0])
                        # pylint: disable=consider-using-in
                        if exc_type == "SyntaxError" or exc_type == "IndentationError" or exc_type == "TabError":
                            syntax_error = traceback.TracebackException(result.get_exc_info()[0],
                                                                        result.get_exc_info()[1],
                                                                        result.get_exc_info()[2])
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
                        buf.write(f"{exc_type}: {result.get_exc_info()[1]}\n\n")
                        buf.write("Traceback (most recent call last):\n")
                        # get the StackSummary
                        tb_frames = traceback.extract_tb(result.get_exc_info()[2])
                        # get the FrameSummary objects from the StackSummary
                        lines = traceback.format_list(tb_frames)

                        # trim the path from the filename
                        def shorten(match):
                            """trim the path from the exception filename"""
                            return f'File "{os.path.basename(match.group(1))}"'

                        lines = [re.sub(r'File "([^"]+)"', shorten, line, 1) for line in lines]
                        buf.writelines(lines)
                    except BaseException:
                        buf.write(f"\nCould not retrieve stacktrace: {traceback.print_exc()}")
            if result.get_capture() is not None:
                out = result.get_capture().get_stdout()
                if out is not None:
                    buf.write("\nStandard output:\n")
                    buf.write(out)
                result.std_err_out = result.get_capture().get_stderr()
                if result.std_err_out is not None:
                    result.has_stderr = True
                    buf.write("\nStandard error:\n")
                    buf.write(result.std_err_out)
            if self.debug_enabled:
                if result.get_debug_log() is not None:
                    buf.write("\nDebug log:\n")
                    buf.write(result.get_debug_log())
        except SystemError as err:
            buf.write(str(err))
        result.summary = buf.getvalue()


# Exceptions

class DataFunctionError(Exception):
    """An exception that is raised to indicate a problem with the Data Function."""
