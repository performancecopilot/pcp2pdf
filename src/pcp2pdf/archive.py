# pcp2pdf.archive - pcp2pdf(1) report graphing utility
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

import datetime
import sys

import cpmapi as c_api
from pcp import pmapi


class PcpHelp(object):
    '''Class to fetch description texts from local pmcd instance

    Help texts are not shipped in an archive file. This class is used
    to fetch the help texts from the locally running pmcd service. This
    presumes that the PMNS tree is the same between the archive and the
    local PCP instance. Just a best effort thing. If the local PCP instance
    does not have the same PMDAs or has a different PMNS tree, texts
    will be missing.
    '''
    pmns = {}
    help_text = {}
    ctx = None

    def _pmns_callback(self, label):
        '''Callback for the PMNS tree walk.'''
        try:
            newlabel = label.decode("utf-8")
        except AttributeError:
            newlabel = label

        self.pmns[newlabel] = None

    def __init__(self):
        try:
            self.ctx = pmapi.pmContext(target='local:')
        except Exception:
            print("Unable to contact local pmcd. Help text will be missing")
            return
        self.ctx.pmTraversePMNS('', self._pmns_callback)
        for metric in self.pmns:
            try:
                pmid = self.ctx.pmLookupName(metric)
                text = self.ctx.pmLookupText(pmid[0],
                                             kind=c_api.PM_TEXT_HELP)
                try:
                    self.help_text[metric] = text.decode('utf-8')
                except AttributeError:
                    self.help_text[metric] = text
            except Exception:
                pass


class PcpArchive(object):
    '''Class to make it easy to extract data from a PCP archive.'''
    pcparchive = ''
    ctx = None
    result = None
    # keys is the metric string. Value is (type, sem, units)
    pmns = {}

    def __init__(self, pcp_fname, opts):
        '''Opens a PCP archive and does an initial walk of the PMNS tree.'''
        self.pcparchive = pcp_fname
        try:
            self.ctx = pmapi.pmContext.fromOptions(opts.opts, sys.argv)
        except pmapi.pmErr as e:
            print("Error: {0}".format(e))
            sys.exit(-1)

        self.ctx.pmTraversePMNS('', self._pmns_callback)
        self.start = opts.opts.pmGetOptionStart()
        self.end = opts.opts.pmGetOptionFinish()
        self.interval = opts.opts.pmGetOptionInterval()

    def _timestamp_to_secs(self, tstamp):
        '''Convert a timestamp object (tv_sec + tv_usec) to seconds.'''
        secs = tstamp.tv_sec + (tstamp.tv_usec * 10**-6)
        return secs

    def _pmns_callback(self, label):
        '''Callback to walk the PMNS tree and populate self.pmns dictionary.'''
        try:
            newlabel = label.decode("utf-8")
        except AttributeError:
            newlabel = label
        pmid = self.ctx.pmLookupName(label)
        try:
            desc = self.ctx.pmLookupDesc(pmid[0])
        except pmapi.pmErr:
            print("Unable to get description for: {0} [{1}] -> Skipping".format(label, pmid[0]))
            return

        self.pmns[newlabel] = (desc.type, desc.sem, desc.contents.units,
                            desc.contents.type,
                            self.ctx.pmUnitsStr(desc.contents.units),
                            self.ctx.pmTypeStr(desc.contents.type))

    def _extract_value(self, result, desc, i, inst=0):
        '''Return python value given a pmExtractValue set of parameters.'''
        mtype = desc.contents.type
        value = self.ctx.pmExtractValue(result.contents.get_valfmt(i),
                                        result.contents.get_vlist(i, inst),
                                        mtype, mtype)
        if mtype == c_api.PM_TYPE_U64:
            retval = value.ull
        elif mtype == c_api.PM_TYPE_U32:
            retval = value.ul
        elif mtype == c_api.PM_TYPE_64:
            retval = value.ll
        elif mtype == c_api.PM_TYPE_32:
            retval = value.l
        elif mtype == c_api.PM_TYPE_STRING:
            retval = value.cp
        elif mtype == c_api.PM_TYPE_FLOAT:
            retval = value.f
        elif mtype == c_api.PM_TYPE_DOUBLE:
            retval = value.d
        else:
            raise Exception("Metric has unknown type: [%s]" % (mtype))
        return retval

    def close(self):
        '''Frees the context.'''
        if self.ctx and self.result:
            self.ctx.pmFreeResult(self.result)

    def get_hostname(self):
        '''Returns the host that collected the metrics in the archive.'''
        return self.ctx.pmGetContextHostName()

    def get_metrics(self):
        '''Returns a list of all the metric labels of the archive.'''
        return list(self.pmns.keys())

    def get_metric_info(self, metric):
        '''Given a metric label, return (type, sem, units).'''
        return self.pmns[metric]

    def get_pmids(self, metrics):
        '''Given a list of metrics, returns a list of PMIDs.'''
        return self.ctx.pmLookupName(metrics)

    def get_values(self, progress=None):
        '''Returns a dictionary of dictionaries with the archive data

        It will contain all the data within a PCP archive log file. Data will
        be returned as a a tuple (data, skipped_metrics). skipped_metrics is a
        list of metrics skipped because the archive log was corrupted. data
        will be in the following form:
        return[metric1] = {'indom1': [(ts0, ts1, .., tsN), (v0, v1, .., vN)],
                           ....
                           'indomN': [(ts0, ts1, .., tsN), (v0, v1, .., vN)]}
        return[metric2] = {'indom1': [(ts0, ts1, .., tsX), (v0, v1, .., vX)],
                           ....
                           'indomN': [(ts0, ts1, .., tsX), (v0, v1, .., vX)]}

        (ts0, .., tsN) are timestamps in datetime format and (v0, .., vN) are
        the actual values. If a metric has no indom, "0" will be used as its
        key.
        "progress" is a callback function which takes a boolean argument (True
        when the pmFetch() call returned data and False if it did not)
        '''
        data = {}
        self.ctx.pmSetMode(c_api.PM_MODE_FORW, self.start, 0)
        # If the user defined an interval, we set it up
        if self.interval:
            self.ctx.pmSetMode(c_api.PM_MODE_INTERP |
                               c_api.PM_XTB_SET(c_api.PM_TIME_SEC),
                               self.start, self.interval)

        skipped_metrics = []
        # indom_map is just used as an optimization. The keys are (numpmid,
        # numinst) and the value is the indom name. This avoids too many
        # expensive calls to pmNameInDomArchive.
        indom_map = {}
        metrics = self.get_metrics()
        pmids = self.get_pmids(metrics)
        start = self._timestamp_to_secs(self.start)
        end = self._timestamp_to_secs(self.end)
        while 1:
            try:
                # We need to do this without pmFetchArchive() as it does not
                # support INTERP mode
                pmids = self.ctx.pmLookupName(metrics)
                result = self.ctx.pmFetch(pmids)
            except pmapi.pmErr as error:
                # Exit if we are at the end of the file or if the record is
                # corrupted. Raise proper exception in all other cases
                if error.args[0] in [c_api.PM_ERR_EOL, c_api.PM_ERR_LOGREC]:
                    break
                else:
                    raise error

            secs = self._timestamp_to_secs(result.contents.timestamp)
            ts = datetime.datetime.fromtimestamp(secs)
            if not (float(self.start) <= secs and secs <= float(self.end)):
                self.ctx.pmFreeResult(result)
                continue

            if progress:
                progress(secs, start, end)

            # Walk through the whole list of PMIDs fetched at time ts
            for i in range(result.contents.numpmid):
                pmid = result.contents.get_pmid(i)
                desc = self.ctx.pmLookupDesc(pmid)
                metric = self.ctx.pmNameID(pmid)
                if metric not in data:
                    data[metric] = {}
                count = result.contents.get_numval(i)
                if count == 0:  # No instance whatsoever
                    continue
                elif count == 1:  # No indoms are present
                    try:
                        value = self._extract_value(result, desc, i)
                    except pmapi.pmErr as error:
                        if error.args[0] in [c_api.PM_ERR_CONV]:
                            skipped_metrics.append(metric)
                            continue
                        raise error
                    if 0 not in data[metric]:
                        data[metric][0] = [[ts, ], [value, ]]
                    else:
                        data[metric][0][0].append(ts)
                        data[metric][0][1].append(value)
                    continue

                # count > 1 -> Multiple indoms
                for j in range(count):
                    inst = result.contents.get_inst(i, j)
                    try:
                        value = self._extract_value(result, desc, i, j)
                    except pmapi.pmErr as error:
                        if error.args[0] in [c_api.PM_ERR_CONV]:
                            skipped_metrics.append(metric)
                            continue
                    if (i, j) not in indom_map:
                        try:
                            indom = self.ctx.pmNameInDomArchive(desc, inst)
                            indom_map[(i, j)] = indom
                        except pmapi.pmErr:
                            print("Error in pmNameInDomArchive %s -> %s" % (desc, inst))
                    else:
                        indom = indom_map[(i, j)]
                    if indom not in data[metric]:
                        data[metric][indom] = [[ts, ], [value, ]]
                    else:
                        data[metric][indom][0].append(ts)
                        data[metric][indom][1].append(value)

            self.ctx.pmFreeResult(result)

        return (data, skipped_metrics)
