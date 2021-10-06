# Copyright © 2021. TIBCO Software Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Pure Python implementation of a Spotfire package (.spk extension) builder tool."""

import abc
import argparse
import datetime
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import typing
import uuid
from xml.etree import ElementTree
import zipfile

from pip._vendor.packaging import version as pip_version

import spotfire
import spotfire.version

# Command line parsing helpers

CLI_PARSER = argparse.ArgumentParser(prog="python -m spotfire.spk")
CLI_SUBPARSERS = CLI_PARSER.add_subparsers(dest="subcommand")


def subcommand(args=None, parent=CLI_SUBPARSERS):
    """Decorate a function so that it is usable as a subcommand of 'python -m spotfire.spk'."""
    if args is None:
        args = []

    def decorator(func):
        """Decorate the function."""
        parser = parent.add_parser(func.__name__, help=func.__doc__)
        for arg in args:
            parser.add_argument(*arg[0], **arg[1])
        parser.set_defaults(func=func)
        return func

    return decorator


def argument(*name_or_flags, **kwargs):
    """Used by the '@subcommand()' decorator to add arguments to the created subcommand."""
    return list(name_or_flags), kwargs


# Messaging helper functions

def _message(msg: str) -> None:
    sys.stdout.write(msg)
    sys.stdout.write(os.linesep)


def _error(msg: str) -> None:
    sys.stdout.write(msg)
    sys.stdout.write(os.linesep)


# Packaging helper functions

class _SpkVersion:
    """Represents a version number as presented in Spotfire SPK package files.  Version numbers have four components
    (organized from largest scope to smallest): major, minor, service pack, and identifier."""

    def __init__(self, major: int = 1, minor: int = 0, service_pack: int = 0, identifier: int = 0) -> None:
        self._versions = [major, minor, service_pack, identifier]

    @staticmethod
    def from_str(str_: str) -> '_SpkVersion':
        """Parse a string into a version.

        :param str_: the string to parse into a version number
        """
        components = str_.split(".")
        if len(components) > 4:
            raise ValueError("Must have four components in version number.")
        return _SpkVersion(*map(int, components))

    @staticmethod
    def from_version_info(identifier: int) -> '_SpkVersion':
        """Extract the SPK version of the running Python installation."""
        spk_minor = (sys.version_info.minor * 100) + sys.version_info.micro
        spotfire_version_components = spotfire.version.__version__.split(".")
        spk_service_pack = (int(spotfire_version_components[0]) * 10000) + \
                           (int(spotfire_version_components[1]) * 100) + \
                           (int(spotfire_version_components[2]))
        version = _SpkVersion(sys.version_info.major, spk_minor, spk_service_pack, identifier)
        return version

    def __str__(self):
        # pylint: disable=consider-using-f-string
        return "%d.%d.%d.%d" % tuple(self._versions)

    def __repr__(self):
        return f"{self.__class__.__module__}.{self.__class__.__qualname__}{tuple(self._versions)!r}"

    def increment_major(self) -> None:
        """Increment the major component of the version number.  Resets all smaller components to zero."""
        self._versions[0] += 1
        self._versions[1:] = [0, 0, 0]

    def increment_minor(self) -> None:
        """Increment the minor component of the version number.  Resets all smaller components to zero."""
        self._versions[1] += 1
        self._versions[2:] = [0, 0]

    def _decrement(self, pos, wrap_around) -> None:
        while pos >= 0:
            self._versions[pos] -= 1
            if self._versions[pos] < 0:
                self._versions[pos] = wrap_around
                pos -= 1
            else:
                return
        self._versions = [0, 0, 0, 0]
        raise ValueError("Version object cannot decrement major version below zero.")

    def decrement_major(self) -> None:
        """Decrement the major component of the version number.  Resets all smaller components to zero.

        :raises ValueError: if the major component would be decremented below zero
        """
        self._versions[1:] = [0, 0, 0]
        self._decrement(0, 0)

    def decrement_minor(self, wrap_around: int = 99) -> None:
        """Decrement the minor component of the version number.  Resets all smaller components to zero.

        :param wrap_around: the value to set components that are decremented below zero
        """
        self._versions[2:] = [0, 0]
        self._decrement(1, wrap_around)

    def decrement_service_pack(self, wrap_around: int = 99) -> None:
        """Decrement the service pack component of the version number.  Resets all smaller components to zero.

        :param wrap_around: the value to set components that are decremented below zero
        """
        self._versions[3:] = [0]
        self._decrement(2, wrap_around)

    def __lt__(self, other):
        if not isinstance(other, _SpkVersion):
            return NotImplemented
        return self._versions < other._versions  # pylint: disable=protected-access


def _tee(command: typing.List[str], encoding: str = "utf-8") -> typing.List[str]:
    """Run an external command, capturing the output and displaying it to standard output.  Standard error is collapsed
    into the same stream as standard output.

    :param command: the command to run
    :param encoding: the encoding to use to convert the bytes of the command's output into str
    :return: a list of the lines of the command's output
    :raises CalledProcessError: if the command returns a non-zero exit status
    """
    output = []
    sys.stdout.flush()
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
        for line in process.stdout:
            line = line.decode(encoding)
            output.append(line)
            sys.stdout.write(line)
        return_code = process.wait()
        if return_code:
            raise subprocess.CalledProcessError(return_code, command[0])
        return output


def _brand_file(filename: str, data: typing.Dict, comment: str, line_length: int = 72) -> None:
    """Brand a file with the JSON representation of data.

    :param filename: the filename of the file to brand
    :param data: the data to brand into the file
    :param comment: the comment characters to prefix each line of the brand
    :param line_length: the number of characters that should be present on each line of the brand
    """
    data_json = json.dumps(data, separators=(',', ':'))

    # Read in the file, ignoring any current brand.
    lines = []
    with open(filename, "r", encoding="utf8") as file:
        for line in file.readlines():
            if not line.startswith(comment):
                lines.append(line)

    # Add line break to ensure brand is on a new line (PYSRV-162)
    if not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    # Now append the brand lines to what we just read in.
    brand_per_line = line_length - len(comment)
    while data_json:
        lines.append(f"{comment}{data_json[:brand_per_line]}\n")
        data_json = data_json[brand_per_line:]

    # Write out the new file.
    with open(filename, "w", encoding="utf8") as file:
        file.writelines(lines)


def _read_brand(filename: str, comment: str) -> typing.Dict:
    """Read a brand from a file.

    :param filename: the filename of the file with the brand
    :param comment: the comment characters that prefix each line of the brand
    :return: the data that is encoded in the brand
    """
    # Read in the file, pulling in only the lines with branding on them.
    lines = []
    with open(filename, "r", encoding="utf8") as file:
        for line in file.readlines():
            if line.startswith(comment):
                lines.append(line)

    # Reassemble data and parse the JSON object from the brand.
    data_json = "".join(map(lambda x: x[len(comment):].rstrip(), lines))
    return json.loads(data_json) if data_json else {}


class _PackageBuilder(metaclass=abc.ABCMeta):
    # pylint: disable=too-many-instance-attributes,consider-using-f-string
    def __init__(self) -> None:
        self.name = None
        self.version = None
        self.id = None
        self.output = None
        self.excludes = []
        self.last_scan_dir = None
        self._contents = []
        if platform.system() == "Windows":
            self._site_packages_dirname = "Lib\\site-packages"
        else:
            self._site_packages_dirname = "lib/python%d.%d/site-packages" % sys.version_info[:2]

    def add(self, filename: str, archive_name: str) -> None:
        """Add a file to the package."""
        archive_backslash = archive_name.replace("/", "\\")
        if self.excludes is not None:
            for exclude in self.excludes:
                if archive_backslash.startswith(exclude):
                    return
        self._contents.append((filename, archive_backslash))

    def scan_python_installation(self, prefix: str) -> None:
        """Scan all the files in the Python installation."""
        try:
            py_prefix = sys.base_prefix
        except AttributeError:
            py_prefix = getattr(sys, "real_prefix", sys.prefix)
        _message(f"Scanning Python installation at {py_prefix} for files to include.")

        # Scan all files in the running Python's prefix
        for root, _, filenames in os.walk(py_prefix):
            for filename in filenames:
                filename_ondisk = os.path.join(root, filename)
                filename_relative = os.path.relpath(filename_ondisk, py_prefix)
                filename_payload = f"{prefix}/{filename_relative}"
                if not filename_relative.startswith(self._site_packages_dirname):
                    # Omit any packages installed in site-packages
                    self.add(filename_ondisk, filename_payload)

    def scan_spotfire_package(self, prefix: str) -> None:
        """Scan the 'spotfire' package (and it's .dist-info directory) into site-packages."""
        _message("Scanning 'spotfire' package files.")

        # Grab the files of the 'spotfire' package.
        for root, _, filenames in os.walk(spotfire.__path__[0]):
            for filename in filenames:
                filename_ondisk = os.path.join(root, filename)
                filename_relative = os.path.relpath(filename_ondisk, spotfire.__path__[0])
                filename_payload = f"{prefix}/{self._site_packages_dirname}/spotfire/{filename_relative}"
                self.add(filename_ondisk, filename_payload)

        # Grab the .dist-info directory.
        site_packages_dir = os.path.dirname(spotfire.__path__[0])
        spotfire_dist_info_re = re.compile(r"^spotfire(-.*)?\.(dist|egg)-info$")
        for subdir in next(os.walk(site_packages_dir))[1]:
            if spotfire_dist_info_re.match(subdir):
                spotfire_dist_info_dir = os.path.join(site_packages_dir, subdir)
                for root, _, filenames in os.walk(spotfire_dist_info_dir):
                    for filename in filenames:
                        filename_ondisk = os.path.join(root, filename)
                        filename_relative = os.path.relpath(filename_ondisk, spotfire_dist_info_dir)
                        filename_payload = f"{prefix}/{self._site_packages_dirname}/{subdir}/{filename_relative}"
                        self.add(filename_ondisk, filename_payload)

    def scan_requirements_txt(self, requirements: str, constraint: str, prefix: str, prefix_direct: bool = False,
                              use_deny_list: bool = False) -> \
            typing.Tuple[typing.Callable[[], None], typing.Dict[str, str]]:
        """Scan the contents of a pip 'requirements.txt' file into site-packages.

        :param requirements: the filename of the requirements file that declares the pip packages to put in the
        SPK package
        :param constraint: the filename of the constraints file that declares the constraints pip should apply
        when resolving requirements
        :param prefix: the directory prefix under which the pip packages should be scanned into
        :param prefix_direct: whether to scan the pip packages into the ``site-packages`` directory
        :param use_deny_list: whether to delete the packages included with the Interpreter from the
                                temporary package area before bundling.
        :return: a function that cleans up the temporarily installed packages, and a dict that maps the names of
        pip packages that were scanned into the SPK package to their installed versions
        """
        tempdir = tempfile.mkdtemp(prefix="spk")
        self.last_scan_dir = tempdir

        def cleanup():
            """Cleanup the created tempdir."""
            shutil.rmtree(tempdir)

        # Install the packages from the requirement file into tempdir.
        _message(f"Installing pip packages from {requirements} to temporary location.")
        try:
            command = [sys.executable, "-m", "pip", "install", "--upgrade", "--disable-pip-version-check",
                             "--target", tempdir, "--requirement", requirements]
            if constraint:
                command.extend(["--constraint", constraint])
            pip_output = _tee(command)
        except subprocess.CalledProcessError:
            _error("Error installing required packages.  Aborting.")
            cleanup()
            sys.exit(1)

        # Update the brand with the package versions.
        package_versions = self._packages_installed(pip_output)

        # Delete duplicate packages if needed
        if use_deny_list:
            package_versions = self.scan_duplicate_packages(tempdir, package_versions)

        # Scan all files in tempdir
        _message("Scanning package files from temporary location.")
        for root, _, filenames in os.walk(tempdir):
            for filename in filenames:
                filename_ondisk = os.path.join(root, filename)
                filename_relative = os.path.relpath(filename_ondisk, tempdir)
                if prefix_direct:
                    filename_payload = f"{prefix}/{filename_relative}"
                else:
                    filename_payload = f"{prefix}/{self._site_packages_dirname}/{filename_relative}"
                if not filename_relative.startswith(f"bin{os.path.sep}"):
                    self.add(filename_ondisk, filename_payload)

        return cleanup, package_versions

    @staticmethod
    def scan_duplicate_packages(tempdir: str, package_versions):
        """ When building a custom Python Packages SPK, find and delete duplicate packages.
        :return:
        """
        # Disable Pylint `Too many nested blocks`
        # pylint: disable=too-many-nested-blocks,too-many-locals
        # Use the spotfire requirements file as a deny list.
        _message(f"{spotfire.__path__[0]}")
        if "spotfire.zip" in spotfire.__path__[0]:
            # Handle getting the requirements.txt from a zip file.
            with zipfile.ZipFile(os.path.split(spotfire.__path__[0])[0]) as zfile:
                with zfile.open("spotfire/requirements.txt") as deny_file:
                    deny_requirements = deny_file.readlines()
                deny_list = [line.decode("utf-8").rstrip('\n') for line in deny_requirements]
        else:
            # Handle getting the requirements.txt directly from the file system.
            with open(os.path.join(spotfire.__path__[0], "requirements.txt"), encoding="utf8") as deny_file:
                deny_requirements = deny_file.readlines()
            deny_list = [line.rstrip('\n') for line in deny_requirements]

        # Compile a Set of directories to delete
        package_directories = set()
        # Go through each package
        for package_name in deny_list:
            # Remove version numbers from package name and keep a copy of the original name
            package_name = package_name.split(' ', 1)[0]
            original_package_name = package_name
            # Convert dash to underscore for file access
            package_name = package_name.replace('-', '_')
            # Walk through each directory
            for root, directory_names, _ in os.walk(tempdir):
                for directory_name in directory_names:
                    # look for the `dist-info` directory for each package
                    if directory_name.startswith(package_name) and directory_name.endswith('dist-info'):
                        package_directories.add(directory_name)
                        # Go through the RECORD file from the package dist-info and delete each listed file
                        record_file = os.path.join(root, directory_name, 'RECORD')
                        if os.path.isfile(record_file):
                            with open(record_file, encoding="utf8") as open_record_file:
                                record_files = open_record_file.readlines()
                            for file in record_files:
                                # Clean up the path to each file.
                                # RECORD has file name, then comma followed by info we don't need.
                                file = file.split(',', 1)[0]
                                # Files in "/bin" start with "../../" but we don't need that.
                                if file.startswith('../../'):
                                    file = file.split('../../', 1)[1]
                                # Get the path to the file
                                file = os.path.join(root, file)
                                # Delete the file if it exists
                                if os.path.isfile(file):
                                    os.remove(file)
                                else:
                                    _message(f"Could not find RECORD file {file}")
                            _message(f"Deleted files listed in RECORD for {directory_name}")
                            package_versions.pop(original_package_name, None)
                    if directory_name == package_name:
                        package_directories.add(directory_name)
        # Manually add 'dateutil's non-standard package name
        package_directories.add('dateutil')
        # Delete the packages' directories
        for package_directory in package_directories:
            package_directory_file = os.path.join(tempdir, package_directory)
            if os.path.isdir(package_directory_file):
                try:
                    shutil.rmtree(package_directory_file)
                except OSError:
                    _message(f"Unable to remove directory {package_directory_file}")
        _message("Completed removing files and directories for packages on the deny list.")
        return package_versions

    @staticmethod
    def _packages_installed(pip_output):
        """Determine what packages were installed by parsing pip's output."""
        _installed = "Successfully installed "
        # Scan the output for the line with the magic string
        installed_line = None
        for i in reversed(pip_output):
            if i.startswith(_installed):
                installed_line = i
        # Now parse the line to get the package versions
        package_versions = {}
        if installed_line:
            installed_packages = installed_line[len(_installed):]
            for pkg in installed_packages.strip().split(" "):
                pkg_dash_pos = pkg.rfind("-")
                package_versions[pkg[:pkg_dash_pos]] = pkg[pkg_dash_pos + 1:]
        return package_versions

    @abc.abstractmethod
    def _payload_name(self) -> str:
        """Get the payload archive name for this package."""

    def _create_module(self) -> ElementTree.Element:
        """Create the module document."""
        module = ElementTree.Element("module")
        module_id = ElementTree.SubElement(module, "id")
        module_id.text = self.id
        module_name = ElementTree.SubElement(module, "name")
        module_name.text = self.name
        module_version = ElementTree.SubElement(module, "version")
        module_version.text = str(self.version)
        return module

    def _create_metadata(self, module: ElementTree.Element) -> ElementTree.Element:
        """Create the metadata document."""
        metadata = ElementTree.Element("Package", {
            "SchemaVersion": "2.0",
            "Name": self.name,
            "Version": str(self.version),
            "LastModified": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
            "SeriesId": self.id,
            "InstanceId": str(uuid.uuid4()),
            "CabinetName": self._payload_name(),
            "Type": "Module",
        })
        ElementTree.SubElement(metadata, "Files")
        ElementTree.SubElement(metadata, "Assemblies")
        metadata_client_module = ElementTree.SubElement(metadata, "ClientModule")
        for child in module:
            metadata_client_module.append(child)
        return metadata

    @abc.abstractmethod
    def _build_payload(self, metadata: ElementTree.Element, module: ElementTree.Element, payload_dest: str) -> None:
        """Build the main payload archive for the SPK package."""

    def build(self) -> None:
        """Build the SPK package."""

        # Create the module and metadata documents
        module = self._create_module()
        metadata = self._create_metadata(module)

        # Assemble things
        payload_fd, payload_tempfile = tempfile.mkstemp(prefix="spk")
        os.close(payload_fd)
        try:
            _message(f"Building Spotfire SPK package {self.output}.")

            # Assemble the payload zip
            self._build_payload(metadata, module, payload_tempfile)

            # Now assemble the SPK file
            with zipfile.ZipFile(self.output, "w", compression=zipfile.ZIP_DEFLATED) as spk:
                spk.writestr("module.xml", _et_to_bytes(module))
                spk.writestr("Metadata.xml", _et_to_bytes(metadata))
                spk.write(payload_tempfile, f"Contents/{self._payload_name()}")
            _message("Done.")
        finally:
            os.unlink(payload_tempfile)


def _et_to_bytes(element: ElementTree.Element) -> bytes:
    # Add indentation
    _et_indent(element)

    # Serialize the element to a string
    temp_io = io.BytesIO()
    ElementTree.ElementTree(element).write(temp_io, encoding="utf-8", xml_declaration=True)
    return temp_io.getvalue()


def _et_indent(element: ElementTree.Element, indent="  ", level=0) -> None:
    # pylint: disable=redefined-argument-from-local
    indent_text = "\n" + (level * indent)
    if element:
        if not element.text or not element.text.strip():
            element.text = indent_text + indent
        if not element.tail or not element.tail.strip():
            element.tail = indent_text
        for element in element:
            _et_indent(element, indent, level + 1)
        if not element.tail or not element.tail.strip():
            element.tail = indent_text
    else:
        if level and (not element.tail or not element.tail.strip()):
            element.tail = indent_text


class _ZipPackageBuilder(_PackageBuilder):
    # pylint: disable=too-many-instance-attributes

    def __init__(self):
        super().__init__()
        self.chmod_script_name = None

    def _payload_name(self) -> str:
        """Get the payload archive name for this package."""
        return f"{self.name}.zip"

    def _create_module(self) -> ElementTree.Element:
        """Create the module document."""
        module = super()._create_module()
        module_intended_client = ElementTree.SubElement(module, "intendedClient")
        module_intended_client.text = "PythonService"
        module_intended_platform = ElementTree.SubElement(module, "intendedPlatform")
        module_intended_platform.text = platform.system().upper()
        module_webplayer_folder = ElementTree.SubElement(module, "webPlayerContentFolder")
        module_webplayer_folder.text = "root"
        return module

    def _create_metadata(self, module: ElementTree.Element) -> ElementTree.Element:
        """Create the metadata document."""
        metadata = super()._create_metadata(module)
        metadata_archive = ElementTree.SubElement(metadata, "ArchiveFormat")
        metadata_archive.text = "zip"
        return metadata

    def _build_payload(self, metadata: ElementTree.Element, module: ElementTree.Element, payload_dest: str) -> None:
        """Build the main payload archive for the SPK package."""
        metadata_files = metadata.find("Files")
        payload_script = []
        with zipfile.ZipFile(payload_dest, "w", compression=zipfile.ZIP_DEFLATED) as payload:
            # Add all files that are supposed to go into the package
            for filename_ondisk, filename_payload in self._contents:
                filename_payload_fwdslash = filename_payload.replace("\\", "/")[5:]
                if os.path.islink(filename_ondisk):
                    payload_script += "if [ ! -e {payload} ]; then ln -s {ondisk} {payload}; fi\n".format(
                        payload=filename_payload_fwdslash,
                        ondisk=os.readlink(filename_ondisk))
                else:
                    payload.write(filename_ondisk, filename_payload.replace("\\", "/"))
                    stat = os.lstat(filename_ondisk)
                    mode = stat.st_mode & 0o7777
                    ElementTree.SubElement(metadata_files, "File", {
                        "TargetRelativePath": filename_payload,
                        "LastModifiedDate": datetime.datetime.utcfromtimestamp(stat.st_ctime).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"),
                    })
                    if platform.system() != "Windows" and mode != 0o644:
                        payload_script += f"chmod {mode:o} {filename_payload_fwdslash}\n"

            # Add the payload script if we added any lines
            if payload_script:
                payload_script.insert(0, "#!/bin/sh\n")
                payload.writestr(f"root/Tools/Update/{self.chmod_script_name}.sh", "".join(payload_script))
                ElementTree.SubElement(metadata_files, "File", {
                    "TargetRelativePath": f"root\\Tools\\Update\\{self.chmod_script_name}",
                    "LastModifiedDate": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

            # Add the module.xml file
            payload.writestr("module.xml", _et_to_bytes(module))


class _CabPackageBuilder(_PackageBuilder):
    # pylint: disable=too-many-instance-attributes

    def __init__(self):
        if platform.system() != "Windows":
            _error("Cabinet based SPK packages cannot be built on non-Windows systems.  Aborting.")
            sys.exit(1)
        super().__init__()
        self.cert_file = None
        self.cert_password = None
        self.timestamp_url = None
        self.sha256 = False
        self._resources = []

    def _payload_name(self) -> str:
        """Get the payload archive name for this package."""
        return f"{self.name}.cab"

    def add_resource(self, name: str, location: str) -> None:
        """Add a public resource provided by this package."""
        self._resources.append((name, location))

    def _create_module(self) -> ElementTree.Element:
        """Create the module document."""
        module = super()._create_module()
        module_intended_client = ElementTree.SubElement(module, "intendedClient")
        module_intended_client.text = "Forms"
        module_intended_platform = ElementTree.SubElement(module, "intendedPlatform")
        module_intended_platform.text = "WINDOWS_X64"
        module_resources = ElementTree.SubElement(module, "resources")
        for resource_name, resource_location in self._resources:
            ElementTree.SubElement(module_resources, "publicResource", {
                "name": resource_name,
                "relativePath": resource_location
            })
        return module

    def _build_payload(self, metadata: ElementTree.Element, module: ElementTree.Element, payload_dest: str) -> None:
        """Build the main payload archive for the SPK package."""
        # pylint: disable=import-outside-toplevel
        from spotfire import cabfile, codesign
        metadata_files = metadata.find("Files")

        with cabfile.CabFile(payload_dest) as payload:
            # Add all files that are supposed to go into the package
            for filename_ondisk, filename_payload in self._contents:
                payload.write(filename_ondisk, filename_payload)
                stat = os.lstat(filename_ondisk)
                ElementTree.SubElement(metadata_files, "File", {
                    "TargetRelativePath": filename_payload,
                    "LastModifiedDate": datetime.datetime.utcfromtimestamp(stat.st_ctime).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"),
                })

            # Add the module.xml file
            payload.writestr("module.xml", _et_to_bytes(module))

        # Codesign the payload
        if self.cert_file:
            codesign.codesign_file(payload_dest, self.cert_file, self.cert_password, self.timestamp_url, self.sha256,
                                   self.sha256)


# Subcommands

@subcommand([argument("spk-file", help="path to the SPK file to build"),
             argument("-v", "--version", default=1000, type=int, help="set the final component of the version number "
                                                                      "of the built SPK file (default: 1000)"),
             argument("--exclude", action="append", metavar="PATH", help="exclude files from the built SPK file"),
             argument("-c", "--constraint", metavar="FILE", help="apply the constraints in the file when installing "
                                                                 "Python packages"),
             argument("--analyst", action="store_true", help="build the SPK file for use with Spotfire Analyst"),
             argument("--cert", metavar="FILE", help="path to the certificate file to sign the package with (Analyst "
                                                     "only)"),
             argument("--password", help="password for the certificate file (Analyst only)"),
             argument("--timestamp", metavar="URL", help="URL of a timestamping service to timestamp the package with "
                                                         "(Analyst only)"),
             argument("--sha256", action="store_true", help="use SHA-256 for file and timestamp digests (Analyst only)")
             ])
def python(args, hook=None) -> None:
    """Package the currently running Python interpreter as an SPK package"""

    # Verify the version component
    version_identifier = getattr(args, "version")
    if version_identifier < 0:
        print("Error: '--version' cannot be less than 0.")
        sys.exit(1)
    if version_identifier < 1000:
        print("Warning: '--version' should not be less than 1000 in order to avoid conflicts with TIBCO-provided "
              "packages.")

    # Set up the package builder
    analyst = getattr(args, "analyst")
    if analyst:
        package_builder = _CabPackageBuilder()
        package_builder.excludes = getattr(args, "exclude")
        package_builder.cert_file = getattr(args, "cert")
        package_builder.cert_password = getattr(args, "password")
        package_builder.timestamp_url = getattr(args, "timestamp")
        package_builder.sha256 = getattr(args, "sha256")
    else:
        package_builder = _ZipPackageBuilder()
        package_builder.excludes = getattr(args, "exclude")
        package_builder.chmod_script_name = "python_chmod"
    package_builder.output = getattr(args, "spk-file")

    # Determine the platform and any constants that depend on it
    if analyst:
        package_builder.id = "2fe5bbd2-9748-40e5-95b5-748b556ed822"
        package_builder.name = "Python Interpreter"
    else:
        package_builder.id = {
            "Windows": "b95fbe51-c013-4f65-8523-5bffcf19e6a8",
            "Linux": "6692a2c3-d43d-4224-a8db-26619ae8f268",
        }.get(platform.system())
        package_builder.name = f"Python Interpreter {platform.system()}"

    # Get the version of the Python installation
    if sys.version_info.major == 3 and sys.version_info.minor < 5:
        print(f"Error: Unsupported version of Python ('{sys.version}').")
        sys.exit(1)
    package_builder.version = _SpkVersion.from_version_info(version_identifier)

    # Scan the files required to create the Python interpreter SPK
    def cleanup():
        """Dummy cleanup function."""

    if analyst:
        prefix = "python"
        package_builder.add_resource("default.python.interpreter.directory", prefix)
    else:
        prefix = "root/python"
    package_builder.scan_python_installation(prefix)
    package_builder.scan_spotfire_package(prefix)
    spotfire_requirements = os.path.join(spotfire.__path__[0], "requirements.txt")
    try:
        constraints = getattr(args, "constraint")
        cleanup, _ = package_builder.scan_requirements_txt(spotfire_requirements, constraints, prefix)
        if hook is not None:
            hook.scan_finished(package_builder)

        # Build the package
        package_builder.build()
    finally:
        cleanup()


@subcommand([argument("spk-file", help="path to the SPK file to build"),
             argument("requirements", help="package the Python packages listed in the file"),
             argument("-v", "--version", help="set the version number of the built SPK file"),
             argument("-f", "--force", action="store_true", help="ignore errors about downgrading version numbers"),
             argument("--versioned-filename", action="store_true", help="modify the filename of the SPK file to "
                                                                        "contain the version number of the built "
                                                                        "package"),
             argument("-n", "--name", help="set the internal module name of the built SPK file"),
             argument("-c", "--constraint", metavar="FILE", help="apply the constraints in the file when installing "
                                                                 "Python packages"),
             argument("--analyst", action="store_true", help="build the SPK file for use with Spotfire Analyst"),
             argument("--cert", metavar="FILE", help="path to the certificate file to sign the package with (Analyst "
                                                     "only)"),
             argument("--password", help="password for the certificate file (Analyst only)"),
             argument("--timestamp", metavar="URL", help="URL of a timestamping service to timestamp the package with "
                                                         "(Analyst only)"),
             argument("--sha256", action="store_true", help="use SHA-256 for file and timestamp digests (Analyst only)")
             ])
def packages(args) -> None:
    """Package a list of Python packages as an SPK package"""

    def cleanup():
        """Dummy cleanup function."""

    try:
        # Set up the package builder
        analyst = getattr(args, "analyst")
        if analyst:
            package_builder = _CabPackageBuilder()
            package_builder.cert_file = getattr(args, "cert")
            package_builder.cert_password = getattr(args, "password")
            package_builder.timestamp_url = getattr(args, "timestamp")
            package_builder.sha256 = getattr(args, "sha256")
        else:
            package_builder = _ZipPackageBuilder()
            package_builder.chmod_script_name = "packages_chmod"
        package_builder.output = getattr(args, "spk-file")
        requirements_file = getattr(args, "requirements")
        brand = _read_brand(requirements_file, "## spotfire.spk: ")
        version = getattr(args, "version")
        force = getattr(args, "force")
        versioned_filename = getattr(args, "versioned_filename")
        name = getattr(args, "name") or brand.get("BuiltName")
        pkg_id = brand.get("BuiltId")

        # If name and id are not in the brand or given on the command line, generate reasonable defaults
        if name is None:
            if analyst:
                name = "Python Packages"
            else:
                name = f"Python Packages {platform.system()}"
        if pkg_id is None:
            pkg_id = str(uuid.uuid4())
        package_builder.name = name
        package_builder.id = pkg_id

        # Scan the requirements file for packages to install
        if analyst:
            prefix = "site-packages"
            prefix_direct = True
            package_builder.add_resource(f"python.package.{package_builder.id}.whl", prefix)
        else:
            prefix = "root/python"
            prefix_direct = False
        constraints = getattr(args, "constraint")
        cleanup, installed_packages = package_builder.scan_requirements_txt(requirements_file, constraints, prefix,
                                                                            prefix_direct, True)

        # Based on the packages we installed, determine how to increment the version number
        _handle_versioning(package_builder, installed_packages, brand, version, force, versioned_filename)

        # Build the package
        package_builder.build()

        # Now prepare the brand with the results of the build and apply it to our requirements file
        brand["BuiltBy"] = sys.version
        brand["BuiltAt"] = time.asctime(time.localtime(os.path.getmtime(package_builder.output)))
        brand["BuiltFile"] = package_builder.output
        brand["BuiltName"] = package_builder.name
        brand["BuiltId"] = package_builder.id
        brand["BuiltVersion"] = str(package_builder.version)
        brand["BuiltPackages"] = installed_packages
        _brand_file(requirements_file, brand, "## spotfire.spk: ")
    finally:
        cleanup()


def _handle_versioning(package_builder, installed_packages, brand, version, force, versioned_filename):
    package_builder.version = _SpkVersion()
    if "BuiltVersion" in brand:
        package_builder.version = _SpkVersion.from_str(brand["BuiltVersion"])
        package_builder.version.increment_minor()
        if "BuiltPackages" in brand:
            # Tick the major version if required
            if _should_increment_major(brand["BuiltPackages"], installed_packages, force):
                package_builder.version.increment_major()
    # Handle manually specified version numbers
    if version:
        given_version = _SpkVersion.from_str(version)
        if given_version < package_builder.version:
            _error(f"Package version '{given_version}' is lower than generated version '{package_builder.version}'.")
            if not force:
                sys.exit(1)
        package_builder.version = given_version
    # Handle versioned filenames
    if versioned_filename:
        package_builder.output = re.sub(r"(\.spk)?$", fr"-{str(package_builder.version)}\1",
                                        package_builder.output, 1)


def _should_increment_major(old_packages, new_packages, force):
    tick_major = False
    # Check for removed packages
    if old_packages.keys() - new_packages.keys():
        tick_major = True
    # Check for package downgrades
    for pkg in old_packages.keys() & new_packages.keys():
        previous_version = pip_version.parse(old_packages[pkg])
        new_version = pip_version.parse(new_packages[pkg])
        if previous_version > new_version:
            tick_major = True
            _error(f"Package '{pkg}' has a lower version than previously built.")
            if not force:
                sys.exit(1)
    return tick_major


# Main

def main() -> None:
    """Start the package builder."""
    cli_args = CLI_PARSER.parse_args()
    if cli_args.subcommand is None:
        CLI_PARSER.print_help()
    else:
        cli_args.func(cli_args)


if __name__ == '__main__':
    main()
    sys.exit(0)
