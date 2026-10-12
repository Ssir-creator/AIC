"""Build a draft PDF from the measured report; requires optional reportlab."""
import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument("--input",type=Path,default=ROOT/"docs/阶段评测报告.md")
parser.add_argument("--output",type=Path,default=ROOT/"artifacts/阶段评测报告-非提交定稿.pdf")
parser.add_argument("--no-plot",action="store_true")
args=parser.parse_args()
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
base=ParagraphStyle("body",fontName="STSong-Light",fontSize=10,leading=17,wordWrap="CJK",spaceAfter=8,textColor=colors.HexColor("#293a2c"))
title=ParagraphStyle("title",parent=base,fontSize=22,leading=30,spaceAfter=16)
heading=ParagraphStyle("heading",parent=base,fontSize=14,leading=22,spaceBefore=14,spaceAfter=9)
small=ParagraphStyle("small",parent=base,fontSize=8,leading=12,textColor=colors.HexColor("#657362"))
output=args.output
output.parent.mkdir(exist_ok=True)
story=[]
lines=args.input.read_text(encoding="utf-8").splitlines()
index=0
while index<len(lines):
    line=lines[index].strip()
    if not line:
        index+=1;continue
    if line.startswith("|"):
        rows=[]
        while index<len(lines) and lines[index].strip().startswith("|"):
            cells=[c.strip() for c in lines[index].strip().strip("|").split("|")]
            if not all(c and set(c)<=set("-:") for c in cells):
                rows.append([Paragraph(escape(c),base) for c in cells])
            index+=1
        table=Table(rows,colWidths=[505/len(rows[0])]*len(rows[0]),repeatRows=1,hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#edf2e8")),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#d6decc")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),7)]))
        story.extend([table,Spacer(1,12)]);continue
    style=title if line.startswith("# ") else heading if line.startswith("## ") else base
    text=line.lstrip("# ").replace("**","").replace("`","").replace("·", " / ")
    story.append(Paragraph(escape(text),style));index+=1
plot=ROOT/"artifacts/guitarset-baseline-20261011/baseline-diagnostics.png"
if plot.is_file() and not args.no_plot:
    story.extend([PageBreak(),Paragraph("附图：固定12段的基础模型诊断",heading),
                  Paragraph("不是琵琶评测；不是原创算法提升。完整逐段数据见实测包。",small),
                  Image(str(plot),width=505,height=226)])


def footer(canvas,document):
    canvas.saveState();canvas.setFont("STSong-Light",8);canvas.setFillColor(colors.HexColor("#71816a"))
    canvas.drawString(42,26,"谱易改 / 开发阶段记录 / 非提交定稿")
    canvas.drawRightString(A4[0]-42,26,str(document.page));canvas.restoreState()


SimpleDocTemplate(str(output),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=45,
                  title=args.input.stem+"（非提交定稿）",author="谱易改项目").build(story,onFirstPage=footer,onLaterPages=footer)
print(output)
