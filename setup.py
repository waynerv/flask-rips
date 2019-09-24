#!/usr/bin/env python

import re
from os import path

from setuptools import setup, find_packages

requirements = [
    'Flask>=1.0'
]

version_file = path.join(
    path.dirname(__file__),
    'flask_rips',
    '__version__.py'
)
with open(version_file, 'r') as fp:
    m = re.search(
        r"^__version__ = ['\"]([^'\"]*)['\"]",
        fp.read(),
        re.M
    )
    version = m.groups(1)[0]

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='Flask-Rips',
    version=version,
    license='BSD',
    url='https://www.github.com/waynerv/flask-rip/',
    author='Waynerv',
    author_email='ampedee@gmail.com',
    description='Simple framework for minimal REST APIs',
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=find_packages(exclude=['tests']),
    classifiers=[
        'Framework :: Flask',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'License :: OSI Approved :: BSD License',
    ],
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    test_suite='nose.collector',
    install_requires=requirements,
    tests_require=['Flask-Rips', 'mock>=0.8', 'blinker'],
    # Install these with "pip install -e '.[docs]'
    extras_require={
        'docs': 'sphinx',
    }
)
