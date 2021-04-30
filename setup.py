# Copyright © 2021. TIBCO Software Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

# pylint: skip-file
from setuptools import setup, find_packages


def get_requires(filename):
    requirements = []
    with open(filename, "rt") as req_file:
        for line in req_file.read().splitlines():
            if not line.strip().startswith("#"):
                requirements.append(line)
    return requirements


project_requirements = get_requires("spotfire/requirements.txt")
version = {}
with open('spotfire/version.py') as ver_file:
    exec(ver_file.read(), version)
    
with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='spotfire',
    version=version['__version__'],
    description='Package for Building Python Extensions to TIBCO Spotfire',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='TIBCO Software Inc.',
    maintainer='Spotfire Python Package Support',
    maintainer_email='spotfirepython@tibco.com',
    url='https://github.com/TIBCOSoftware/spotfire-python',
    license='BSD 3-Clause License',
    packages=find_packages(exclude=['spotfire.test']),
    include_package_data=True,
    install_requires=project_requirements,
    python_requires='>=3.7',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],
)
