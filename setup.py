#!/usr/bin/env python
# -*- coding: utf-8 -*-

import codecs
import os

from setuptools import setup


def read(fname):
    file_path = os.path.join(os.path.dirname(__file__), fname)
    return codecs.open(file_path, encoding="utf-8").read()


setup(
    name="strictus",
    version="1.0.2",
    url="https://github.com/jbasko/strictus",
    license="MIT",
    author="Jazeps Basko",
    author_email="jazeps.basko@gmail.com",
    maintainer="Jazeps Basko",
    maintainer_email="jazeps.basko@gmail.com",
    description="Strictus (a rewrite of Strictus Dictus)",
    keywords="nested schema dictionary attribute attrdict type hinting typing annotations",
    long_description=read("README.md"),
    long_description_content_type='text/markdown',
    packages=["strictus"],
    python_requires=">=3.7.0",
    install_requires=[
        'cached-property',
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "License :: OSI Approved :: MIT License",
    ],
)
