pcp2pdf
========

Creates a PDF report out of PCP archive files collected via pmlogger

Here is a sample pdf http://acksyn.org/software/pcp2pdf/output.pdf created with:
```
pcp2pdf -a myfiles/20141208.0 -c "traffic:network.interface.out.bytes:eth0,network.interface.in.bytes:virbr[0-9]*,network.tcp..*:.*" \
     -c "in_out:network.interface.out.bytes:eth0,network.interface.in.bytes:eth0" -l 'testlabel:2014-12-08 12:00:00'
```
