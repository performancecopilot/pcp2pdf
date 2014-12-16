# pcp2pdf.style - pcp(1) report graphing utility
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

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.styles import ParagraphStyle as PS
from reportlab.platypus.doctemplate import BaseDocTemplate
from reportlab.platypus.doctemplate import PageTemplate
from reportlab.platypus.frames import Frame
from reportlab.lib.units import inch

class PcpDocTemplate(BaseDocTemplate):
    """Custom Doc Template

    Allows to have bookmarks for certain type of text
    """
    def __init__(self, filename, cfgparser, **kw):
        self.allowSplitting = 0
        # Inch graph size (width, height)
        self.graph_size = (float(cfgparser.get("page", "graph_width")),
                           float(cfgparser.get("page", "graph_height")))
        self.x_axis = ('Time', 12, '%m-%d %H:%M', 20)
        self.tablestyle = [
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), (colors.lightgrey, colors.white)),
            ('GRID', (0, 0), (-1, -1), 1, colors.toColor(cfgparser.get("string_table", "color"))),
            ('ALIGN', (0, 0), (-1, -1), cfgparser.get("string_table", "align")),
            ('LEFTPADDING', (0, 0), (-1, -1), int(cfgparser.get("string_table", "leftPadding"))),
            ('RIGHTPADDING', (0, 0), (-1, -1), int(cfgparser.get("string_table", "rightPadding"))),
            ('FONTSIZE', (0, 0), (-1, -1), int(cfgparser.get("string_table", "fontSize"))),
            ('FONTNAME', (0, 0), (-1, 0), cfgparser.get("string_table", "font")), ]
        apply(BaseDocTemplate.__init__, (self, filename), kw)
        template = PageTemplate('normal', [Frame(
            float(cfgparser.get("page", "x1")) * inch,
            float(cfgparser.get("page", "y1")) * inch,
            float(cfgparser.get("page", "width")) * inch,
            float(cfgparser.get("page", "height")) * inch,
            id='F1')])
        self.addPageTemplates(template)

        font_list = ["centered", "centered_index", "small_centered",
                     "heading1", "heading1_centered", "heading1_invisible",
                     "heading2", "heading2_centered", "heading2_invisible",
                     "mono", "mono_centered", "normal", "front_title", "axes"]
        int_fields = ["fontSize", "leading", "alignment", "spaceAfter"]
        self.fonts = {}
        for font in font_list:
            sheet = getSampleStyleSheet()
            text = sheet['BodyText']
            section = "font_%s" % font
            items = dict(cfgparser.items(section))
            for i in int_fields:
                if i in items:
                    items[i] = int(items[i])

            tmp_ps = PS(font, parent=text)
            tmp_ps.__dict__.update(items)
            self.fonts[font] = tmp_ps

    def afterFlowable(self, flowable):
        """Registers TOC entries."""
        if flowable.__class__.__name__ == 'Paragraph':
            text = flowable.getPlainText()
            style = flowable.style.name
            if style in ["heading1", "centered_index", "heading1_invisible"]:
                level = 0
            elif style in ["heading2", "heading2_centered", "heading2_invisible"]:
                level = 1
            else:
                return
            entry = [level, text, self.page]
            # if we have a bookmark name append that to our notify data
            bookmark_name = getattr(flowable, '_bookmarkName', None)
            if bookmark_name is not None:
                entry.append(bookmark_name)
            self.notify('TOCEntry', tuple(entry))
            self.canv.addOutlineEntry(text, bookmark_name, level, True)
