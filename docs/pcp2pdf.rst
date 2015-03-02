:orphan:

pcp2pdf manual page
===================

Synopsis
--------

**pcp2pdf** [*options*] -a <*pcparchive*> 


Description
-----------

:program:`pcp2pdf` generates a pdf report from a PCP archive. Per default,
the report contains a graph plotting each metric and its corresponding frequency
histogram. By default all the metrics contained in the archive will be plotted.
In order to limit or augment the plotted metrics in the report, use the
``--include``, ``--exclude`` or ``--custom`` options.

:program:`pcp2pdf` only operates on PCP archive files and cannot use live data.

:program:`pcp2pdf` needs a locally running :program:`pmcd` in order to fetch the
help text of each metric. Without it running the report won't have metrics help
text.


Options
-------

-a <archivefile>                           Sets the PCP archive name to be parsed
-i <metrics>, --include <metrics>          Includes metrics which match the specified regular expression.
                                           For example::

                                               --include 'network.*'
                                         
                                           will include only metrics starting with 'network.'. The option can be specified
                                           multiple times. If only ``--include`` is specified, only the matching metrics will
                                           be included in the output. If both ``--include`` and ``--exclude`` are specified,
                                           first all excluded metrics are evaluted, and then the ones explicitely included.
-e <metrics>, --exclude <metrics>          Excludes metrics which match the specified regular expression.
                                           For example::

                                               --exclude 'proc.*'
                                         
                                           will exclude all metrics starting with 'proc.'. The option can be specified
                                           multiple times. If only ``--exclude`` is specified, all metrics are shown except
                                           the specified ones.
-c <graphs>, --custom <graphs>             Add custom graphs with multiple metrics.
                                           For example::

                                               --custom 'traffic:network.tcp.outrsts:.*,network.tcp.ofoqueue.*,network.interfaces.out.*:eth[0-9]'

                                           will create a 'traffic' page with the each matched metric and the corresponding
                                           matched indom single graph. The general syntax is the following::

                                               --custom '<label>:<metric1_regex>:<indom1_regex>,...<metricN_regex>:<indomN_regex>'

                                           The option can be specified multiple times. This makes it easy to try and correlate
                                           metrics that normally would not appear on the same graph. The different metrics'
                                           values need to be in similar scales or the graph will be not too useful.

-o <filename>, --output <filename>         Output file name (default: output.pdf)
-r, --raw                                  Disable rate conversion
                                           Disables the rateconversion for all the metrics that have the ``PM_SEM_COUNTER``
                                           semantic associated with them. By default those are converted via the following
                                           formula ::

                                               (value(T) - value(T-1)) / (T - T-1)
                                          
                                           By setting this option the aforementioned conversion will *not* take place.
-l <labels>, --label <labels>              Adds one or more labels to a graph at specified time
                                           For example::

                                               --label 'foo:2014-01-01 13:45:03' --label 'bar:2014-01-02 13:15:15'
                                          
                                           will add two extra labels on every graph at those times.  This is usually
                                           useful for correlation analysis. The time format is specified in the
                                           :manpage:`PCPIntro(1)` man page.
-S <time>, --start <time>                  Sets the start of the time for the analysis
                                           See :manpage:`PCPIntro(1)` for the accepted time formats. For example::

                                               --start "Fri Oct 10 22:10:12.362 2014"
                                          
-T <time>, --finish <time>                            Sets the end of the time window
                                           See :manpage:`PCPIntro(1)` for the accepted time formats. For example::

                                               --finish "Sat Oct 11 01:00:00.00 2014"

-t <interval>, --interval <interval>       Sets the sampling interval
                                           See :manpage:`PCPIntro(1)` for the accepted interval formats. For example::

                                               --interval "14 minute"
                           
-n, --nohistogram                          Disable the frequency histogram graphs (enabled by default)
-V, --version                              Display version number and exit
--help                                     Show the usage message and exit


See also
--------

:manpage:`PCPIntro(1)`
:manpage:`pmcd(1)`

Homepage
--------

`Homepage <http://github.com/performancecopilot/pcp2pdf`
`Reporting issues <http://github.com/performancecopilot/pcp2pdf/issues>`

