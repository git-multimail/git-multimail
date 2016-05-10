#! /usr/bin/env python

import sys
import os
from setuptools import setup

assert 0x02040000 <= sys.hexversion, \
    "Install Python, version 2.4 or greater"

URL = 'https://github.com/git-multimail/git-multimail'


def read_version():
    sys.path.insert(0, os.path.join('git-multimail'))
    import git_multimail
    return git_multimail.__version__


def read_readme():
    readme = open(os.path.join('git-multimail', 'README')).read()
    # Turn relative links into absolute ones
    readme = readme.replace("`<doc/", "`<" + URL + "/blob/master/doc/")
    readme = readme.replace("`<CONTRIBUTING.rst", "`<" + URL + "/blob/master/CONTRIBUTING.rst")
    return readme

setup(
    name='git-multimail',
    version=read_version(),
    description='Send notification emails for Git pushes',
    long_description=read_readme(),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Topic :: Communications :: Email',
        'Topic :: Software Development :: Version Control',
        ],
    keywords='git hook email',
    url=URL,
    author='Michael Haggerty',
    author_email='mhagger@alum.mit.edu',
    maintainer='Matthieu Moy',
    maintainer_email='Matthieu.Moy@imag.fr',
    license='GPLv2',
    package_dir={'': 'git-multimail'},
    py_modules=['git_multimail'],
    )
