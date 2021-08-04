# pcp2pdf - pcp(1) report graphing utility
# Copyright (C) 2014  Michele Baldessari
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.

from __future__ import print_function

import configparser
import datetime
import os
import os.path
import sys

import cpmapi as c_api
from pcp import pmapi
import pcp2pdf.stats

NAME = "pcp2pdf"

class _Options(object):
    def __init__(self):
        self.input_file = ""
        self.start_time = None
        self.end_time = None
        self.include = []
        self.exclude = []
        self.custom_graphs = []
        self.raw = False
        self.output_file = "output.pdf"
        self.interval = None
        self.labels = {}
        self.dpi = None
        self.histogram = False
        # max nr of CPUs to use. None == All available CPUs
        self.max_cpus = None
        self.opts = self.setup()
        configfiles = []
        path = os.path.join(pmapi.pmContext.pmGetConfig('PCP_SYSCONF_DIR'),
                            NAME, NAME + ".conf")

        configfiles.append(path)
        path = os.path.join(os.getcwd(), "src", NAME + ".conf")
        configfiles.append(path)
        self.configparser = configparser.ConfigParser()
        # Make sure the items are not lower-cased
        self.configparser.optionxform = str
        ret = self.configparser.read(configfiles)
        if not ret:
            print("No configuration files found: {0}".format(configfiles))
            sys.exit(-1)

    def setup(self):
        """Setup default command line argument option handling."""
        # FIXME: There has got to be a better way to indent the text in a
        # visually pleasing way
        t = " " * 24
        opts = pmapi.pmOptions()
        opts.pmSetOptionCallback(self.option_callback)
        opts.pmSetOverrideCallback(self.override)
        opts.pmSetShortOptions("grVi:e:o:c:?S:T:t:a:l:m:d:")
        opts.pmSetOptionFlags(c_api.PM_OPTFLAG_BOUNDARIES)
        opts.pmSetOptionFlags(c_api.PM_OPTFLAG_MULTI)
        opts.pmSetShortUsage("[options] -a <pcp_archive>\nFor example:\npcp2pdf -S \"May 30 12:00 2014\" -T \"May 30 15:00 2014\" -t \"4 minute\" \\\n -c \"traffic:network.interface.out.bytes:eth0,network.interface.in.bytes:*\" -l 'foo:2014-05-30 12:30:00' -a tests/20140530.0")
        opts.pmSetLongOptionHeader("Options")

        opts.pmSetLongOption("include", 1, 'i', '', "Include specific metrics")
        opts.pmSetLongOptionText(t + "Includes metrics which match the specified regular expression.")
        opts.pmSetLongOptionText(t + "For example: --include 'network.*'. The option can be specified")
        opts.pmSetLongOptionText(t + "multiple times. If only --include is specified, only the matching")
        opts.pmSetLongOptionText(t + "metrics will be included in the output. If both --include and --exclude")
        opts.pmSetLongOptionText(t + "are specified first all excluded metrics are evaluted and then the included ones")
        opts.pmSetLongOption("exclude", 1, 'e', '', "Exclude specific metrics")
        opts.pmSetLongOptionText(t + "Excludes metrics which match the specified regular expression. For example:")
        opts.pmSetLongOptionText(t + "--exclude 'network.*'. The option can be specified multiple times. If only")
        opts.pmSetLongOptionText(t + "--exclude is specified, all metrics are shown except the specified ones")
        opts.pmSetLongOption("output", 1, 'o', '', "Output file name (default: output.pdf)")
        opts.pmSetLongOption("custom", 1, 'c', '', "Add custom graphs")
        opts.pmSetLongOptionText(t + "Add ability to create graphs with multiple metrics. For example:")
        opts.pmSetLongOptionText(t + "--custom 'traffic:network.interface.out.bytes:virbr0,network.interface.in.bytes:br0,network.tcp.*:.*'")
        opts.pmSetLongOptionText(t + "would create a 'traffic' page with the above matrics as regular expressions combined in a single graph.")
        opts.pmSetLongOptionText(t + "The general syntax is:")
        opts.pmSetLongOptionText(t + "--custom '<label>:<metric1_re>:<indom1_re>,...<metricN_re>:<indomN_re>'. The option can be specified multiple times")
        opts.pmSetLongOption("raw", 0, 'r', '', "Disable rate conversions")
        opts.pmSetLongOptionText(t + "Disable the rate conversion for all the metrics that have the PM_SEM_COUNTER semantic")
        opts.pmSetLongOptionText(t + "associated with them. By default those are converted via: (value(T) - value(T-1)) / (T - T-1)")
        opts.pmSetLongOption("label", 1, 'l', '', "Adds one or more labels to a graph at specified time")
        opts.pmSetLongOptionText(t + "For example --label 'foo:2014-01-01 13:45:03' --label 'bar:2014-01-02 13:15:15' will add")
        opts.pmSetLongOptionText(t + "two extra labels on every graph at those times. This is useful for correlation work")
        opts.pmSetLongOption("histogram", 0, 'g', '', "Disables the creation of distribution histograms for each graph")
        opts.pmSetLongOption("dpi", 1, 'd', '', "Sets the DPI used to create the images for the graph. Default is 200")
        opts.pmSetLongOptionText(t + "unless overridden in the configuration. The lower the value, the less memory the process will need")
        opts.pmSetLongOptionText(t + "and the less quality the graphs will have.")
        opts.pmSetLongOption("cpus", 1, 'm', '', "Maximum nr of CPUs to use when rendering (default: all available CPUs)")
        opts.pmSetLongOptionStart()
        opts.pmSetLongOptionFinish()
        opts.pmSetLongOptionInterval()
        opts.pmSetLongOptionArchive()
        opts.pmSetLongOptionVersion()
        opts.pmSetLongOptionHelp()
        return opts

    def override(self, opt):
        """Override a few standard PCP options to match free(1)."""
        # pylint: disable=R0201
        if opt == 'g':
            return 1
        elif opt == 'n':
            return 1
        return 0

    def option_callback(self, opt, optarg, index):
        """Perform setup for an individual command line option."""
        # pylint: disable=W0613
        if opt == "S":
            self.start_time = optarg
        elif opt == "T":
            self.end_time = optarg
        elif opt == "g":
            self.histogram = True
        elif opt == "d":
            try:
                self.dpi = int(optarg)
            except Exception:
                print("Error parsing dpi: {0}".format(optarg))
                sys.exit(1)
        elif opt == "t":
            self.interval = optarg
        elif opt == "m":
            if int(optarg) == 0:
                self.max_cpus = None
            else:
                self.max_cpus = int(optarg)
        elif opt == "e":
            self.exclude.append(optarg)
        elif opt == "c":
            self.custom_graphs.append(optarg)
        elif opt == "i":
            self.include.append(optarg)
        elif opt == "l":
            try:
                # labels are in the form "foo:2014-01-01 13:45:03"
                # FIXME: I did not find any PCP python function to parse the
                # time directly (?)
                label = optarg.split(':')[0]
                time_str = "".join(optarg.split(':')[1:])
                time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H%M%S")
                self.labels[label] = time
            except Exception as e:
                print("Error parsing label: {0} -> {1}".format(optarg, e))
                sys.exit(1)
        elif opt == "a":
            self.input_file = optarg
        elif opt == "o":
            self.output_file = optarg
        elif opt == "r":
            self.raw = True


def main():
    global opts
    opts = _Options()
    if c_api.pmGetOptionsFromList(sys.argv) != 0:
        c_api.pmUsageMessage()
        sys.exit(1)

    pcp_files = opts.opts.pmGetOptionArchives()
    if pcp_files is None:
        print("Error: No pcp archives specified")
        c_api.pmUsageMessage()
        sys.exit(1)

    print("Parsing: {0}".format(" ".join(
          map(os.path.basename, pcp_files))), end='')
    print()

    pcpstats = pcp2pdf.stats.PcpStats([pcp_files[0]], opts)
    pcpstats.output()

if __name__ == '__main__':
    main()


# vim: autoindent tabstop=4 expandtab smarttab shiftwidth=4 softtabstop=4 tw=0
