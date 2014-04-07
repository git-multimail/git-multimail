#! /usr/bin/env python2

import sys
import os
from setuptools import setup

assert 0x02040000 <= sys.hexversion < 0x03000000, \
       "Install Python 2, version 2.4 or greater"


def read_readme():
    return open(os.path.join('git-multimail', 'README')).read()


setup(
    name='git-multimail',
    version='1.0.0',
    description='Send notification emails for Git pushes',
    long_description=read_readme(),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2 :: Only',
        'Topic :: Communications :: Email',
        'Topic :: Software Development :: Version Control',
        ],
    keywords='git hook email',
    url='https://github.com/mhagger/git-multimail',
    author='Michael Haggerty',
    author_email='mhagger@alum.mit.edu',
    maintainer='Michael Haggerty',
    maintainer_email='mhagger@alum.mit.edu',
    license='GPLv2',
    package_dir = {'': 'git-multimail'},
    py_modules=['git_multimail'],
    )


