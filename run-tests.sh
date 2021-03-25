#!/bin/sh
if python --version 2>&1 | grep -q "Python 3"; then
	python -m venv /tmp/v
	. /tmp/v/bin/activate
fi
pip install --upgrade pip
pip install -r /a/src/python/requirements_dev.txt
python -m spotfire.test

