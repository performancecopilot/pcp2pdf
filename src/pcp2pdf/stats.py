# pcp2pdf.stats - pcp(1) report graphing utility
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

import bisect
import datetime
import hashlib
import itertools
import multiprocessing
import os
import re
import resource
import shutil
import sys
import tempfile
import time

from reportlab.platypus.paragraph import Paragraph
from reportlab.platypus import Image
from reportlab.platypus import PageBreak
from reportlab.platypus import Spacer
from reportlab.platypus import Table
import reportlab.lib.colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import inch
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.colors as colors
import matplotlib.cm as cm
from matplotlib.patches import Rectangle

import cpmapi as c_api
from pcp2pdf.style import PcpDocTemplate
from pcp2pdf.archive import PcpArchive
from pcp2pdf.archive import PcpHelp

# When showing a rectangle gap when the interval is > than the average frequency we
# first multiply by FREQUNCY ERROR in order to avoid spurious rectangles
FREQUENCY_ERROR = 1.1

# Threshold above which the legend is placed on the bottom
# of the page
LEGEND_THRESHOLD = 50

progress_counter = multiprocessing.Value('i', 0)
progress_lock = multiprocessing.Lock()
progress_total = 0

def ellipsize(text, limit=20):
    '''Truncates a string in a nice-formatted way.'''
    if len(text) < limit:
        return text

    limit = limit - 2  # '..'
    a = int(limit / 2)
    b = int(limit / 2 + (limit % 2))
    ret = text[:a] + '..' + text[len(text) - b:]
    return ret


def date_string(dt):
    '''Prints a datetime string in format '2014-10-21 23:24:10'.'''
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def parse_progress_callback(ts, start, finish):
    percentage = round(((ts - start) / (finish - start)) * 100.0, 1)
    sys.stdout.write('\rParsing archive: [%s %s%%]' % ('#' * (int(percentage/10)), percentage))
    sys.stdout.flush()

def graph_progress_callback(pcpobj):
    percentage = round((progress_counter.value / progress_total) * 100.0, 1)
    sys.stdout.write('\rCreating graphs: [%s %s%%]' % ('#' * (int(percentage/10)), percentage))
    sys.stdout.flush()


def split_chunks(list_to_split, chunksize):
    """Split the list l in chunks of at most n in size."""
    ret = [list_to_split[i:i + chunksize]
           for i in range(0, len(list_to_split), chunksize)]
    return ret


def graph_wrapper(zip_obj):
    """Wrapper due to pool.map() single argument limit.
    zip_obj = zip(itertools.repeat(self), self.all_graphs)
    where self is a PcpStats object. Each CPU will get
    a slice of the self.all_graphs list
    """
    (pcpstats_obj, data) = list(zip_obj)
    (label, fname, metrics, text, indomres, histogram) = data
    if histogram:
        ret = pcpstats_obj.create_histogram(fname, label, metrics, indomres)
    else:
        ret = pcpstats_obj.create_graph(fname, label, metrics, indomres)
    with progress_lock:
        progress_counter.value += 1
    graph_progress_callback(pcpstats_obj)
    return ((label, fname, metrics, text, indomres, histogram), ret)


def print_mem_usage(data):
    usage = resource.getrusage(resource.RUSAGE_SELF)
    print("Graphing: {0} usertime={1} systime={2} mem={3} MB"
          .format(data, usage[0], usage[1], (usage[2] / 1024.0)))


def match_res(patterns, string, flags=0):
    if type(string) != str:
        string = str(string)
    for pattern in patterns:
        ret = re.match(pattern, string, flags)
        if ret is not None:
            return ret
    return None

class PcpStats(object):
    story = []

    def __init__(self, args, opts):
        self.args = args
        self.opts = opts
        self.configparser = opts.configparser
        self.doc = PcpDocTemplate(opts.output_file, self.configparser, pagesize=landscape(A4))
        self.pcphelp = PcpHelp()
        self.pcparchive = PcpArchive(args, opts)
        if self.opts.dpi is not None and self.opts.dpi > 0:
            self.DPI = self.opts.dpi
        else:
            self.DPI = self.configparser.getint('main', 'dpi')
        self.logo = self.configparser.get('main', 'logo')
        # Allow to be run from the current dir for unit-testing purposes
        if not os.path.isfile(self.logo):
            self.logo = os.path.join(os.getcwd(), "src", "pcplogo.png")

        # Using /var/tmp as /tmp is ram-mounted these days
        self.tempdir = tempfile.mkdtemp(prefix='pcpstats', dir='/var/tmp')
        # This will contain all the metrics found in the archive file
        self.all_data = {}
        # Verify which set of metrics are to be used
        self.metrics = []
        if not opts.include and not opts.exclude:
            self.metrics = sorted(self.pcparchive.get_metrics())
        elif opts.include and not opts.exclude:  # Only specified filters
            metrics = sorted(self.pcparchive.get_metrics())
            for i in opts.include:
                try:
                    matched = filter(lambda x: re.match(i, x), metrics)
                except Exception:
                    print("Failed to parse: {0}".format(i))
                    sys.exit(-1)
                self.metrics.extend(matched)
        elif not opts.include and opts.exclude:  # Exclude specified filter
            metrics = sorted(self.pcparchive.get_metrics())
            matched = []
            for i in opts.exclude:
                try:
                    matched.extend(filter(lambda x: re.match(i, x), metrics))
                except Exception:
                    print("Failed to parse: {0}".format(i))
                    sys.exit(-1)

            self.metrics = sorted(list(set(metrics) - set(matched)))
        else:
            all_metrics = sorted(self.pcparchive.get_metrics())
            matched = []
            for i in opts.exclude:
                try:
                    matched.extend(filter(lambda x: re.match(i, x),
                                          all_metrics))
                except Exception:
                    print("Failed to parse: {0}".format(i))
                    sys.exit(-1)

            delta_metrics = sorted(list(set(all_metrics) - set(matched)))
            metrics = sorted(self.pcparchive.get_metrics())
            for i in opts.include:
                try:
                    matched = filter(lambda x: re.match(i, x), metrics)
                except Exception:
                    print("Failed to parse: {0}".format(i))
                    sys.exit(-1)
                delta_metrics.extend(matched)
            self.metrics = delta_metrics

        self.custom_graphs = []
        # Verify if there are any custom graphs. They can be defined like
        # the following :
        # "foo:network.interface.out.bytes:eth0,network.tcp..*:.*"
        for graph in opts.custom_graphs:
            try:
                x = graph.find(':')
                label = graph[0:x]
                line = graph[x + 1:]
                elements = line.split(',')
            except Exception:
                print("Failed to parse label: {0}".format(graph))
                sys.exit(-1)

            if label in self.metrics:
                print("Cannot use label {0}. It is an existing metric".format(label))
                sys.exit(-1)

            all_metrics = sorted(self.pcparchive.get_metrics())
            indomres = {}
            metrics = []
            for element in elements:
                try:
                    (metric_str, indom_str) = element.split(':')
                except Exception:
                    print("Failed to parse: {0}".format(element))
                    sys.exit(-1)
                try:
                    tmp_metrics = filter(lambda x: re.match(metric_str, x),
                                         all_metrics)
                    metrics.extend(tmp_metrics)
                except Exception:
                    print("Failed to parse: {0}".format(metric_str))
                    sys.exit(-1)
                for metric in tmp_metrics:
                    if metric in indomres:
                        indomres[metric].append(indom_str)
                    else:
                        indomres[metric] = [indom_str]

            # Try to compile the indom_res to make sure they are valid
            errors = []
            for pattern in indomres:
                try:
                    re.compile(pattern)
                except Exception:
                    errors.append(pattern)
                    pass

            if len(errors) > 0:
                print("Invalid regular expressions: {0}".format(
                    " ".join(errors)))
                sys.exit(-1)

            # We expanded all the metrics here. We cannot do the same for
            # indoms as those are not yet available. We just pass the regexes
            # and do it at custom graph creation time
            self.custom_graphs.append(("Custom.%s" % label, metrics, indomres))

        try:  # Not all matplotlib versions have this key
            matplotlib.rcParams['figure.max_open_warning'] = 100
        except KeyError:
            pass

    def _graph_filename(self, metrics, extension='.png', histogram=False):
        '''Creates a unique constant file name given a list of metrics.'''
        # We're on python 2.6o .jpg even though graph quality is affected,
        # because the underlying imaging lib bails out on a few graphs from
        # time to time
        pyver = sys.version_info
        if pyver[0] == 2 and pyver[1] <= 6:
            extension = '.jpg'
        if isinstance(metrics, list):
            temp = ''
            for i in metrics:
                temp += i
        else:
            temp = "_".join(metrics)
        if histogram:
            temp = 'h' + temp
        fname = os.path.join(self.tempdir, temp + extension)
        return fname

    def _do_heading(self, text, sty):
        if isinstance(text, list):
            text = "_".join(text)
        # create bookmarkname
        bn = hashlib.sha1(text.encode('utf-8') + sty.name.encode('utf-8')).hexdigest()
        # modify paragraph text to include an anchor point with name bn
        # store the bookmark name on the flowable so afterFlowable can see this
        h = Paragraph(text + '<a name="%s"/>' % bn, sty)
        h._bookmarkName = bn
        self.story.append(h)

    def rate_convert(self, timestamps, values):
        '''Do a rate conversion

        Given a list of timestamps and a list of values it will return the
        following:
        [[t1,..,tN], [(v1-v0)/(t1-t0),(v2-v1)/(t2-t1),..,(vN-vN-1)/(tN -tN-1)]
        '''
        if len(timestamps) != len(values):
            raise Exception('Len of timestamps must be equal to len of values')
        new_timestamps = []
        new_values = []
        for t in range(1, len(timestamps)):
            delta = timestamps[t] - timestamps[t - 1]
            new_timestamps.append(delta)

        for v in range(1, len(values)):
            seconds = new_timestamps[v - 1].total_seconds()
            try:
                delta = (values[v] - values[v - 1]) / seconds
            except ZeroDivisionError:
                # If we have a zero interval but the values difference is zero
                # return 0 anyway
                if values[v] - values[v - 1] == 0:
                    delta = 0
                    pass
                else:
                    # if the delta between the values is not zero try to use
                    # the previous calculated delta
                    if v > 1:
                        delta = new_values[v - 2]
                    else:  # In all other cases just set the delta to 0
                        delta = 0
                    pass

            new_values.append(delta)

        # Add previous datetime to the time delta
        for t in range(len(new_timestamps)):
            ts = new_timestamps[t]
            new_timestamps[t] = ts + timestamps[t]

        return (new_timestamps, new_values)

    def find_max(self, timestamp, metrics):
        '''Find maximum value given timestamp and metrics

        Given data as returned by pcparchive.get_values a timestamp and a set
        of metrics, find the maximum y value. If the given timestamp does not
        exist in the data we do a linear interpolation.
        '''
        max_value = -sys.maxint
        for metric in metrics:
            for indom in self.all_data[metric]:
                timestamps = self.all_data[metric][indom][0]
                y_values = self.all_data[metric][indom][1]
                try:
                    x = timestamps.index(timestamp)
                    y = y_values[timestamp]
                except ValueError:
                    time_key_right = bisect.bisect_right(timestamps, timestamp)
                    # If the custom label's timestamp falls outside the
                    # data we have we skip this
                    if time_key_right >= len(timestamps):
                        continue
                    time_key_left = time_key_right - 1
                    x1 = mdates.date2num(timestamps[time_key_left])
                    x2 = mdates.date2num(timestamps[time_key_right])
                    y1 = y_values[time_key_left]
                    y2 = y_values[time_key_right]
                    if x1 == x2 or y1 == y2:  # No need to do any interpolation
                        y = y1
                    else:
                        m = (y2 - y1) / (x2 - x1)
                        x = mdates.date2num(timestamp) - x1
                        y = m * x + y1

                if y > max_value:
                    max_value = y
        return max_value

    def get_frequency(self, data):
        # First we calculate the observed frequency (in seconds) of the
        # observed measurements
        total = 0.0
        counter = 0
        for metric in data:
            for indom in data[metric]:
                timestamps = data[metric][indom][0]
                last = None
                for timestamp in timestamps:
                    if not last:
                        last = timestamp
                        continue
                    delta = (timestamp - last).total_seconds()
                    total += delta
                    counter += 1
                    last = timestamp

        frequency = total / counter
        return frequency

    def find_data_gaps(self, data):
        '''Find data gaps given a dataset

        Returns a dictionary with tuples containing the start and end of the
        large intervals as tuples. The value of the dictionary is a list of
        tuples where this interval has been observed (metric, indom).
        Returns: {(gap1start, gap1end): [(metric, indom), (m2, indom2), ...],
                  {gap2start, gap2end): [(metric, indom), (m2, indom2), ...]}
        '''

        frequency = self.get_frequency(data)
        ret = {}
        for metric in data:
            for indom in data[metric]:
                timestamps = data[metric][indom][0]
                last = None
                for timestamp in timestamps:
                    if not last:
                        last = timestamp
                        continue
                    delta = (timestamp - last).total_seconds()
                    if delta > frequency * FREQUENCY_ERROR:
                        key = (last, timestamp)
                        if key not in ret:
                            ret[key] = [(metric, indom)]
                        else:
                            ret[key].append((metric, indom))
                    last = timestamp
        return ret

    def parse(self):
        '''Parse the archive and store all the metrics in self.all_data

        It returns a dictionary containing the metrics which have been
        rate converted
        '''
        start_time = time.time()
        (all_data, self.skipped_graphs) = self.pcparchive.get_values(progress=parse_progress_callback)
        tdelta = time.time() - start_time
        sys.stdout.write('\rParsing archive: [########## 100.0%%] - %.2fs' % tdelta)
        sys.stdout.flush()
        print()

        rate_converted = {}
        # Prune all the sets of values where all values are zero as it makes
        # no sense to show those
        for metric in all_data:
            rate_converted[metric] = False
            tmp = {}
            # FIXME: Once python 2.6 dep is dropped we can use the following
            # tmp = {key: value for key, value in all_data[metric].items()
            #       if not all([ v == 0 for v in value[1]])}
            data = all_data[metric].items()
            for key, value in data:
                if not all([v == 0 for v in value[1]]):
                    tmp[key] = value

            if len(tmp) > 0:
                self.all_data[metric] = tmp

        if self.opts.raw:  # User explicitely asked to not rate convert any metrics
            return rate_converted

        # Rate convert all the PM_SEM_COUNTER metrics
        for metric in self.all_data:
            (mtype, msem, munits, dtype, desc_units, desc_type) = self.pcparchive.get_metric_info(metric)
            if msem != c_api.PM_SEM_COUNTER:
                continue

            for indom in self.all_data[metric]:
                data = self.all_data[metric][indom]
                (ts, val) = self.rate_convert(data[0], data[1])
                self.all_data[metric][indom] = [ts, val]
                if not rate_converted[metric]:
                    rate_converted[metric] = {}
                rate_converted[metric][indom] = True

        return rate_converted

    def get_category(self, label, metrics):
        '''Return the category given one or a list of metric strings.'''
        if isinstance(metrics, str):
            if label.startswith('Custom'):
                return 'Custom'
            return metrics.split('.')[0]
        elif isinstance(metrics, list):
            if label.startswith('Custom'):
                return 'Custom'
            category = None
            for metric in metrics:
                prefix = metric.split('.')[0]
                if category is None and prefix != category:
                    category = prefix
                elif category is not None and prefix != category:
                    raise Exception('Multiple categories in %s' % metrics)
            return category.title()
        else:
            raise Exception('Cannot find category for %s' % metrics)

    def is_string_metric(self, metric):
        '''Given a metric returns True if values' types are strings.'''
        data = self.all_data[metric]
        isstring = False
        for indom in data:
            values = data[indom][1]
            if all([isinstance(v, str) for v in values]):
                isstring = True
                break
        return isstring

    def get_colormap(self, metrics, indomres):
        '''Return the colormap used to plot the different graphs'''
        # First we calculate the maximum number of colors needed
        max_values_len = 0
        for metric in metrics:
            values = self.all_data[metric]
            count = 0
            for indom in values:
                if indomres is not None and metric in indomres:
                    if match_res(indomres[metric], indom) is None:
                        continue
                count += 1
            if count > max_values_len:
                max_values_len = count

        # We need at most number of max(indoms) * metrics colors
        vmax_color = max_values_len * len(metrics)
        color_norm = colors.Normalize(vmin=0, vmax=vmax_color)
        scalar_map = cm.ScalarMappable(norm=color_norm,
                                       cmap=plt.get_cmap('Set1'))
        return scalar_map

    def create_histogram(self, fname, title, metrics, indomres):
        '''Creates a histogram image

        Take a filename, a title, a list of metrics and an indom_regex to
        create an image of the graph
        '''
        # reportlab has a 72 dpi by default
        fig = plt.figure(figsize=(self.doc.graph_size[0],
                                  self.doc.graph_size[1]))
        axes = fig.add_subplot(111)
        # Set Axis metadata
        axes.set_xlabel('Values')
        axes.set_title('{0}'.format(title, fontsize=self.doc.fonts['axes'].fontSize))
        axes.set_ylabel('%s frequency' % title)
        y_formatter = matplotlib.ticker.ScalarFormatter(useOffset=False)
        axes.yaxis.set_major_formatter(y_formatter)
        axes.yaxis.get_major_formatter().set_scientific(False)
        axes.grid(True)

        found = False
        indoms = 0
        counter = 0
        scalar_map = self.get_colormap(metrics, indomres)

        # Then we walk the metrics and plot
        for metric in metrics:
            values = self.all_data[metric]
            for indom in sorted(values):
                # If the indomres is not None we use the indom only if the re string
                # matches
                if indomres is not None and metric in indomres:
                    if match_res(indomres[metric], indom) is None:
                        continue
                (timestamps, dataset) = values[indom]
                # Currently if there is only one (timestamp,value) like with filesys.blocksize
                # we just do not graph the thing
                if len(timestamps) <= 1:
                    continue

                if len(metrics) > 1:
                    if indom == 0:
                        lbl = metric
                    else:
                        lbl = "%s %s" % (metric, indom)
                else:
                    if indom == 0:
                        lbl = title
                    else:
                        lbl = indom

                lbl = ellipsize(lbl, 30)
                found = True
                try:
                    axes.hist(dataset, cumulative=False,
                              label=lbl, color=scalar_map.to_rgba(counter))
                except Exception:
                    import traceback
                    print("Metric: {0}".format(metric))
                    print(traceback.format_exc())
                    sys.exit(-1)

                indoms += 1
                counter += 1

        if not found:
            return False

        # Add legend only when there is more than one instance
        lgd = False
        if indoms > 1:
            fontproperties = matplotlib.font_manager.FontProperties(size='xx-small')
            if indoms > LEGEND_THRESHOLD:
                # Draw legend on the bottom only when instances are more than
                # LEGEND_THRESHOLD
                lgd = axes.legend(loc=9, ncol=int(indoms ** 0.6),
                                  bbox_to_anchor=(0.5, -0.29), shadow=True,
                                  prop=fontproperties)
            else:
                # Draw legend on the right when instances are more than
                # LEGEND_THRESHOLD
                lgd = axes.legend(loc=1, ncol=int(indoms ** 0.5), shadow=True,
                                  prop=fontproperties)


        if lgd:
            plt.savefig(fname, bbox_extra_artists=(lgd,), bbox_inches='tight',
                        dpi=self.DPI)
        else:
            plt.savefig(fname, bbox_inches='tight', dpi=self.DPI)
        plt.cla()
        plt.clf()
        plt.close('all')
        return True

    def create_graph(self, fname, title, metrics, indomres):
        '''Creates a graph image

        Take a filename, a title, a list of metrics and an indom_regex to
        create an image of the graph
        '''
        # reportlab has a 72 dpi by default
        fig = plt.figure(figsize=(self.doc.graph_size[0],
                                  self.doc.graph_size[1]))
        axes = fig.add_subplot(111)
        # Set X Axis metadata
        axes.set_xlabel('Time')
        axes.set_title('{0}'.format(title, fontsize=self.doc.fonts['axes'].fontSize))
        axes.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        axes.xaxis.set_minor_locator(mdates.MinuteLocator(interval=20))
        fig.autofmt_xdate()
        # Set Y Axis metadata
        axes.set_ylabel(title)
        y_formatter = matplotlib.ticker.ScalarFormatter(useOffset=False)
        axes.yaxis.set_major_formatter(y_formatter)
        axes.yaxis.get_major_formatter().set_scientific(False)

        axes.grid(True)

        found = False
        indoms = 0
        counter = 0
        scalar_map = self.get_colormap(metrics, indomres)

        # Then we walk the metrics and plot
        for metric in metrics:
            values = self.all_data[metric]
            for indom in sorted(values):
                # If the indomres is not None we use the indom only if the re string
                # matches
                if indomres is not None and metric in indomres:
                    if match_res(indomres[metric], indom) is None:
                        continue
                (timestamps, dataset) = values[indom]
                # Currently if there is only one (timestamp,value) like with filesys.blocksize
                # we just do not graph the thing
                if len(timestamps) <= 1:
                    continue

                if len(metrics) > 1:
                    if indom == 0:
                        lbl = metric
                    else:
                        lbl = "%s %s" % (metric, indom)
                else:
                    if indom == 0:
                        lbl = title
                    else:
                        lbl = indom

                lbl = ellipsize(lbl, 30)
                found = True
                try:
                    axes.plot(timestamps, dataset, 'o:', label=lbl,
                              color=scalar_map.to_rgba(counter))
                except Exception:
                    import traceback
                    print("Metric: {0}".format(metric))
                    print(traceback.format_exc())
                    sys.exit(-1)

                # Have the Y axis always start from 0
                axes.set_ylim(ymin=0)

                indoms += 1
                counter += 1

        if not found:
            return False

        # Show any data collection gaps in the graph
        gaps = self.find_data_gaps(self.all_data).keys()
        if len(gaps) > 0:
            for i in gaps:
                (g1, g2) = i
                x1 = mdates.date2num(g1)
                x2 = mdates.date2num(g2)
                (ymin, ymax) = plt.ylim()
                axes.add_patch(Rectangle((x1, ymin), x2 - x1, ymax - ymin,
                               facecolor="lightgrey"))

        # Draw self.labels if non empty
        if len(self.opts.labels) > 0:
            for label in self.opts.labels:
                max_value = self.find_max(self.opts.labels[label], metrics)
                # should we not find a max_value at all (due to empty timestamps)
                if max_value == -sys.maxint:
                    max_value = 0
                axes.annotate(label, xy=(mdates.date2num(self.opts.labels[label]), max_value),
                              xycoords='data', xytext=(30, 30), textcoords='offset points',
                              arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2"))

        # Add legend only when there is more than one instance
        lgd = False
        if indoms > 1:
            fontproperties = matplotlib.font_manager.FontProperties(size='xx-small')
            if indoms > LEGEND_THRESHOLD:
                # Draw legend on the bottom only when instances are more than
                # LEGEND_THRESHOLD
                lgd = axes.legend(loc=9, ncol=int(indoms ** 0.6),
                                  bbox_to_anchor=(0.5, -0.29), shadow=True,
                                  prop=fontproperties)
            else:
                # Draw legend on the right when instances are more than
                # LEGEND_THRESHOLD
                lgd = axes.legend(loc=1, ncol=int(indoms ** 0.5), shadow=True,
                                  prop=fontproperties)

        if lgd:
            plt.savefig(fname, bbox_extra_artists=(lgd,), bbox_inches='tight',
                        dpi=self.DPI)
        else:
            plt.savefig(fname, bbox_inches='tight', dpi=self.DPI)
        plt.cla()
        plt.clf()
        plt.close('all')
        return True

    def get_all_graphs(self):
        '''Returns all the graphs that need to be plotted

        Prepare the full list of graphs that will be drawn
        Start with any custom graphs if they exist and
        proceed with the remaining ones. Split the metrics
        that have string values into a separate array
        all_graphs = [(label, fname, (m0, m1, .., mN), text), ...].
        '''

        all_graphs = []
        string_metrics = []
        indom_res = []

        for graph in self.custom_graphs:
            (label, metrics, indom_res) = graph
            fname = self._graph_filename(label)
            text = None
            custom_metrics = []
            for metric in metrics:  # verify custom graph's metrics existance
                if metric in self.all_data:
                    custom_metrics.append(metric)

            if len(custom_metrics) == 0:
                break

            if isinstance(metrics, str) and metrics in self.pcphelp.help_text:
                text = '<strong>%s</strong>: %s' % (metrics, self.pcphelp.help_text[metrics])
            all_graphs.append((label, fname, custom_metrics, text, indom_res, False))
            if self.opts.histogram:
                fname = self._graph_filename(label, histogram=True)
                all_graphs.append(('%s histogram' % label, fname, custom_metrics, text, indom_res, True))

        for metric in sorted(self.all_data):
            # Make sure that we plot only the metrics that the
            # user has specified
            if metric not in self.metrics:
                continue

            if self.is_string_metric(metric):
                string_metrics.append(metric)
                continue

            fname = self._graph_filename([metric])
            units_str = self.pcparchive.get_metric_info(metric)[4]
            type_str = self.pcparchive.get_metric_info(metric)[5]
            if isinstance(metric, str) and metric in self.pcphelp.help_text:
                help_text = self.pcphelp.help_text[metric]
            else:
                help_text = '...'

            text = '<strong>%s</strong>: %s (%s - %s)' % (metric, help_text, units_str, type_str)
            if self.rate_converted[metric]:
                text = text + ' - <em>%s</em>' % 'rate converted'
            all_graphs.append((metric, fname, [metric], text, None, False))
            if self.opts.histogram:
                fname = self._graph_filename([metric], histogram=True)
                all_graphs.append(('%s histogram' % metric, fname, [metric], text, None, True))

        return (all_graphs, string_metrics)

    def output(self):
        # FIXME: Split this function in smaller pieces. This is unreadable
        self.rate_converted = self.parse()
        (self.all_graphs, string_metrics) = self.get_all_graphs()
        if len(self.all_graphs) == 0:
            print('No usable non-zero graphs found.')
            sys.exit(0)

        width = self.doc.pagesize[0]
        hostname = self.pcparchive.get_hostname()
        self._do_heading('Report', self.doc.fonts["heading1_invisible"])
        self.story.append(Paragraph('%s' % hostname, self.doc.fonts["front_title"]))
        self.story.append(Spacer(1, 1.5 * inch))
        self.story.append(Image(self.logo))
        self.story.append(Spacer(1, 0.5 * inch))

        data = [['PCP Archive', '%s' % (" ".join(self.args))],
                ['Start', '%s' % date_string(datetime.datetime.fromtimestamp(self.pcparchive.start))],
                ['End', '%s' % date_string(datetime.datetime.fromtimestamp(self.pcparchive.end))],
                ['Created', '%s' % date_string(datetime.datetime.now())], ]
        rows = 4
        if self.pcparchive.interval:
            data.append(['Interval', '%s seconds' % self.pcparchive.interval])
            rows = 5
        style = [('GRID', (0, 0), (-1, -1), 1, reportlab.lib.colors.black),
                 ('ALIGN', (0, 0), (-1, -1), "LEFT"),
                 ('FONTSIZE', (0, 0), (-1, -1), 14),
                 ('FONTNAME', (0, 0), (-1, -1), "Helvetica"),
                 ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                 ('INNERGRID', (0, 0), (-1, -1), 0.44, reportlab.lib.colors.black), ]

        table = Table(data, 2 * [3.5 * inch], rows * [0.4 * inch])
        table.setStyle(style)
        self.story.append(table)
        self.story.append(PageBreak())

        start_time = time.time()
        done_metrics = []
        global progress_total
        progress_total = len(self.all_graphs)
        if True:
            pool = multiprocessing.Pool(None)
            l = zip(itertools.repeat(self), self.all_graphs)
            metrics_rets = pool.map(graph_wrapper, l)
            (metrics, rets) = zip(*metrics_rets)
            done_metrics = [metric for (metric, ret) in metrics_rets if ret]
        else: # This is just to debug in non multi-threaded mode
            for graph in self.all_graphs:
                (label, fname, metrics, text, indomres, histogram) = graph
                if histogram:
                    if self.create_histogram(fname, label, metrics, indomres):
                        done_metrics.append(graph)
                    progress_counter.value += 1
                else:
                    if self.create_graph(fname, label, metrics, indomres):
                        done_metrics.append(graph)
                    progress_counter.value += 1
                
                graph_progress_callback(self)
                

        tdelta = time.time() - start_time
        sys.stdout.write('\rCreating graphs: [########## 100.0%%] - %.2fs' % tdelta)
        sys.stdout.flush()
        print()
        # Build the string metrics table. It only prints
        # a value if it changed over time
        data = [('Metric', 'Timestamp', 'Value')]
        for metric in string_metrics:
            last_value = None
            for indom in self.all_data[metric]:
                timestamps = self.all_data[metric][indom][0]
                values = self.all_data[metric][indom][1]
                for (ts, v) in zip(timestamps, values):
                    if last_value != v:
                        text = ellipsize(v, 100)
                        ts = date_string(ts)
                        data.append((metric, '%s' % ts, text))
                        last_value = v

        if len(data) > 1:
            self._do_heading('String Metrics', self.doc.fonts["heading1"])
            self.story.append(Spacer(1, 0.2 * inch))
            table = Table(data, colWidths=(0.17 * width, 0.12 * width, 0.56 * width))
            table.setStyle(self.doc.tablestyle)
            self.story.append(table)
            self.story.append(PageBreak())

        # At this point all images are created let's build the pdf
        print("Building pdf: ", end='')
        sys.stdout.flush()
        start_time = time.time()
        # Add the graphs to the pdf
        last_category = ''
        for graph in done_metrics:
            (label, fname, metrics, text, indom_res, histogram) = graph
            category = self.get_category(label, metrics)
            if last_category != category:
                self._do_heading(category, self.doc.fonts["heading1"])
                last_category = category

            self._do_heading(label, self.doc.fonts["heading2_invisible"])
            self.story.append(Image(fname, width=self.doc.graph_size[0] * inch,
                                    height=self.doc.graph_size[1] * inch))
            if text:
                self.story.append(Paragraph(text, self.doc.fonts["normal"]))
            self.story.append(PageBreak())

        self.doc.multiBuild(self.story)
        tdelta = time.time() - start_time
        print("{0} - {1:.2f}s".format(self.opts.output_file, tdelta))
        shutil.rmtree(self.tempdir)
