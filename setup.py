#! /usr/bin/env python2

import sys
from setuptools import setup

assert 0x02040000 <= sys.hexversion < 0x03000000, \
       "Install Python 2, version 2.4 or greater"


setup(
    name='git-multimail',
    version='0.9.0',
    description='Send notification emails for git pushes',
    url='https://github.com/mhagger/git-multimail',
    author='Michael Haggerty',
    author_email='mhagger@alum.mit.edu',
    maintainer='Michael Haggerty',
    maintainer_email='mhagger@alum.mit.edu',
    license='GPLv2',
    package_dir = {'': 'git-multimail'},
    py_modules=['git_multimail'],
    )


