"""
Test unit for pcp2pdf. This is only meant to be run from
the current directory via ./setup.py test
"""

from __future__ import print_function

import glob
import os
import os.path
from pkgutil import extend_path
import sys
import time
import unittest

# Get the path at ../tests/test_functions.py and import
# src/pcp2pdf
mypath = os.path.join(sys.modules['tests'].__file__)
basedir = os.path.split(os.path.dirname(mypath))[0]
moduledir = os.path.join(basedir, "src")
extend_path(moduledir, 'pcp2pdf')
from pcp2pdf.__main__ import main

GLOB_PATTERN = '*.0'

class TestPCP2PDF(unittest.TestCase):
    """Main UnitTest class"""
    def setUp(self):
        """Sets the test cases up"""
        self.start_time = time.time()
        self.archives = glob.glob(os.path.join(os.path.dirname(mypath), GLOB_PATTERN))

    def tearDown(self):
        """Called when the testrun is complete. Displays full time"""
        tdelta = time.time() - self.start_time
        print("{0}: {1:.5f}".format(self.id(), tdelta))

    def test_pcp2pdf(self):
        """Parses all the pcp archive files and creates the pdf outputs. This
           time with a specified interval, labels and custom graphs"""
        for archive in self.archives:
            print(archive)
            sys.argv = ['pcp2pdf', '--output', '%s-interval.pdf' % archive,
                    '-t', '1 minute', '-c' 'traffic:network.interface.out.bytes:eth0,network.tcp..*:.*',
                    '--exclude', 'pmcd.*', '-a', archive]
            main()

if __name__ == '__main__':
    unittest.main()
