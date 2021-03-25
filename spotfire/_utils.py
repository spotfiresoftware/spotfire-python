# Copyright © 2021. TIBCO Software Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

"""Utilities used by multiple submodules."""


def type_name(type_: type) -> str:
    """Convert a type object to a string in a consistent manner.

    :param type_: the type object to convert
    :return: a string with the type name
    """
    type_qualname = type_.__qualname__
    type_module = type_.__module__
    if type_module not in ("__main__", "builtins"):
        type_qualname = type_module + '.' + type_qualname
    return type_qualname
