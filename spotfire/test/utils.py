"""Utility classes for integrating unit test results into Jenkins."""


import sys
import xml.dom.minidom
import xmlrunner


# noinspection PyProtectedMember
class PythonVersionModifiedResult(xmlrunner.result._XMLTestResult):  # pylint: disable=protected-access
    """A subclass of XMLTestResult that prefixes the classes with a short string containing the version of Python."""

    def generate_reports(self, test_runner):
        """Generate reports."""
        all_results = self._get_info_by_testcase()

        doc = xml.dom.minidom.Document()
        testsuite = doc.createElement('testsuites')
        doc.appendChild(testsuite)
        parent_element = testsuite

        xml_content = ""
        for suite, tests in all_results.items():
            suite_name = suite
            if test_runner.outsuffix:
                # not checking with 'is not None', empty means no suffix.
                suite_name = '%s-%s' % (suite, test_runner.outsuffix)

            # Build the XML file
            testsuite = PythonVersionModifiedResult._report_testsuite(suite_name, tests, doc, parent_element,
                                                                      self.properties)
            for test_case in testsuite.getElementsByTagName("testcase"):
                test_case.setAttribute("classname", PYTHON_VERSION + "." + test_case.getAttribute("classname"))
            xml_content = doc.toprettyxml(indent='  ', encoding=test_runner.encoding)

        # Assume that test_runner.output is a stream
        test_runner.output.write(xml_content)


PYTHON_VERSION = "py%d%d" % (sys.version_info.major, sys.version_info.minor)
