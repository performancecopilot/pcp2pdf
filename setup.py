#!/usr/bin/python

import os
import sys
import subprocess
import shutil
import unittest

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


def discover_and_run_tests():

    # get setup.py directory
    setup_file = sys.modules['__main__'].__file__
    setup_dir = os.path.abspath(os.path.dirname(setup_file))

    # use the default shared TestLoader instance
    test_loader = unittest.defaultTestLoader

    # use the basic test runner that outputs to sys.stderr
    test_runner = unittest.TextTestRunner()

    # automatically discover all tests
    if sys.version_info < (2, 7):
        raise "Must use python 2.7 or later"
    test_suite = test_loader.discover(setup_dir)

    # run the test suite
    test_runner.run(test_suite)

from setuptools.command.test import test

class DiscoverTest(test):
    def finalize_options(self):
        test.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        discover_and_run_tests()

# Build manpages if we're making a source distribution tarball.
if 'sdist' in sys.argv:
    # Go into the docs directory and build the manpage.
    docdir = os.path.join(os.path.dirname(__file__), 'docs')
    curdir = os.getcwd()
    os.chdir(docdir)
    try:
        subprocess.check_call(['make', 'man'])
    finally:
        os.chdir(curdir)

    # Copy resulting manpages.
    mandir = os.path.join(os.path.dirname(__file__), 'man')
    if os.path.exists(mandir):
        shutil.rmtree(mandir)
    shutil.copytree(os.path.join(docdir, '_build', 'man'), mandir)

config = {
    'name': 'pcp2pdf',
    'version': '0.1',
    'author': 'Michele Baldessari',
    'author_email': 'michele@acksyn.org',
    'url': 'https://github.com/mbaldessari/pcp2pdf',
    'license': 'GPLv2',
    'package_dir': {'': 'src'},
    'packages': ['pcp2pdf'],
    'scripts': ['src/bin/pcp2pdf'],
    'data_files': [('/etc/bash_completion.d', ['src/pcp2pdf.bash']),
                   ('/etc/pcp/pcp2pdf/', ['src/pcp2pdf.conf']),
                   ('/usr/share/pcp2pdf/', ['src/pcplogo.png'])],
    'cmdclass': {'test': DiscoverTest},
    'classifiers': [
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Programming Language :: Python",
    ],
}

setup(**config)
