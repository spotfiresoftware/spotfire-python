# Copyright © 2021. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

# pylint: skip-file
import logging
import sys

from setuptools import setup, find_packages
from Cython.Distutils import Extension, build_ext
import numpy as np


class BuildExtDebug(build_ext):
    def finalize_options(self):
        if sys.platform == "win32":
            logging.info("appending debug flags for Windows")
            for m in self.distribution.ext_modules:
                m.extra_compile_args.extend(["-Ox", "-Zi"])
                m.extra_link_args.extend(["-debug:full"])
        else:
            logging.info("enabling cygdb for Unix")
            super().cython_gdb = True
        super().finalize_options()


version = {}
with open('spotfire/version.py') as ver_file:
    exec(ver_file.read(), version)
    
if sys.platform == "win32":
    platform_filename = "_windows"
    cabfile_libraries = ['cabinet']
    codesign_includes = ['vendor/windows']
    codesign_libraries = ['crypt32']
else:
    platform_filename = ""
    cabfile_libraries = []
    codesign_includes = []
    codesign_libraries = []
extensions = [
    Extension("spotfire.cabfile",
              sources=[f"spotfire/cabfile{platform_filename}.pyx",
                       "spotfire/cabfile_helpers.c",
                       ],
              include_dirs=["spotfire"],
              libraries=cabfile_libraries
              ),
    Extension("spotfire.codesign",
              sources=[f"spotfire/codesign{platform_filename}.pyx"],
              include_dirs=codesign_includes,
              libraries=codesign_libraries
              ),
    Extension("spotfire.sbdf",
              sources=["spotfire/sbdf.pyx",
                       "spotfire/sbdf_helpers.c",
                       "vendor/sbdf-c/src/metadata.c",
                       "vendor/sbdf-c/src/valuearray.c",
                       "vendor/sbdf-c/src/internals.c",
                       "vendor/sbdf-c/src/fileheader.c",
                       "vendor/sbdf-c/src/columnmetadata.c",
                       "vendor/sbdf-c/src/bswap.c",
                       "vendor/sbdf-c/src/sbdfstring.c",
                       "vendor/sbdf-c/src/errors.c",
                       "vendor/sbdf-c/src/object.c",
                       "vendor/sbdf-c/src/columnslice.c",
                       "vendor/sbdf-c/src/bytearray.c",
                       "vendor/sbdf-c/src/tablemetadata.c",
                       "vendor/sbdf-c/src/tableslice.c",
                       "vendor/sbdf-c/src/valuetype.c",
                       ],
              define_macros=[("SBDF_STATIC", None),
                             ("NPY_NO_DEPRECATED_API", "NPY_1_23_API_VERSION")],
              include_dirs=["spotfire", "vendor/sbdf-c/include", np.get_include()]
              ),
]

setup(
    version=version['__version__'],
    packages=find_packages(exclude=['spotfire.test.files']),
    ext_modules=extensions,
    cmdclass={'build_ext_debug': BuildExtDebug},
)
