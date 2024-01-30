# Copyright © 2023. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Utility functions for preparing troubleshooting bundles."""

import csv
import importlib.metadata as md
import json
import os
import platform
import re
import sys
import typing


_TroubleshootingInfo = dict[str, typing.Any]


def _tb_operating_system() -> _TroubleshootingInfo:
    info: _TroubleshootingInfo = {
        'name': platform.system()
    }

    if info['name'] == "Windows":
        info['distro'] = {
            'id': platform.win32_edition(),
            'version': platform.version()
        }
    elif info['name'] == "Linux":
        # Capture uname information
        info['uname'] = _join(platform.uname())

        # Capture Linux distribution information
        with open("/etc/os-release", encoding="utf-8") as os_file:
            os_reader = csv.reader(os_file, delimiter='=')
            os_info = dict(os_reader)
        info['distro'] = {
            'id': os_info['ID'],
            'version': os_info['VERSION_ID'],
            'libc': _join(platform.libc_ver(lib='unknown'))
        }

        # Capture Docker information
        def _docker_cgroup(cgroup_file: str = "/proc/self/cgroup") -> bool:
            if not os.path.isfile(cgroup_file):
                return False
            with open(cgroup_file, encoding="utf-8") as file:
                for line in file:
                    if re.match(r"\d+:[\w=]+:/docker(-[ce]e)?/\w+", line):
                        return True
                return False

        in_docker = os.path.exists('/.dockerenv') or _docker_cgroup()
        info['docker'] = in_docker

    return info


def _tb_python() -> _TroubleshootingInfo:
    info: _TroubleshootingInfo = {
        'impl': sys.implementation.name,
        'version': sys.version
    }

    if sys.prefix == sys.base_prefix:
        info['loc'] = sys.prefix
    else:
        info['loc'] = (sys.prefix, sys.base_prefix)

    return info


def _tb_packages() -> _TroubleshootingInfo:
    info: _TroubleshootingInfo = {}

    # Prepare empty locations to preserve ordering of PYTHONPATH
    for dir_ in sys.path:
        info[dir_] = {}

    # Now list all distributions available
    for dist in md.distributions():
        dir_loc = str(dist.locate_file('.'))
        info[dir_loc][dist.name] = dist.version

    return info


def _join(seq: typing.Iterable[str]) -> str:
    return ' '.join(seq).rstrip()


def troubleshooting_bundle() -> str:
    """Create a Python data function troubleshooting bundle.

    :return: a string containing the troubleshooting bundle
    """
    bundle: _TroubleshootingInfo = {
        'os': _tb_operating_system(),
        'python': _tb_python(),
        'packages': _tb_packages(),
        'env': dict(os.environ)
    }
    return json.dumps(bundle, separators=(',', ':'))


def main():
    """Generate a troubleshooting bundle."""

    # pylint: disable=import-outside-toplevel
    import argparse
    parser = argparse.ArgumentParser(prog="python -m spotfire.support")
    parser.add_argument("-f", "--file", help="filename to write the bundle to instead of to the "
                                             "standard output")
    args = parser.parse_args()
    bundle = troubleshooting_bundle()
    if args.file:
        with open(args.file, "w", encoding="utf-8") as file:
            file.write(bundle)
    else:
        print(bundle)


if __name__ == '__main__':
    main()
    sys.exit(0)
