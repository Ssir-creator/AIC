"""Anonymous review slides using only actual current results; optional reportlab."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib import colors
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from xml.sax.saxutils import escape
root=Path(__file__).resolve().parents[1]
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
output=root/'artifacts/谱易改-答辩审核稿.pdf'
c=canvas.Canvas(str(output),pagesize=(960,540));c.setTitle('谱易改答辩审核稿 / 非提交定稿')
style=ParagraphStyle('body',fontName='STSong-Light',fontSize=18,leading=29,wordWrap='CJK',textColor=colors.HexColor('#334b3c'))
slides=[
('谱易改 / 琵琶短录音转谱与纠谱',[
'2026 AIC / AI+软件创新',
'帮助学习者定位与校对音符，整理可继续使用的乐谱草稿。',
'音频识别 → 原音校对 → 参考定位 → MIDI / MusicXML草稿',
'研发审核版：参考草稿与实际用户效果仍待验证。']),
('用户任务：从录音到可用谱面',[
'目标用户：希望整理短练习录音的琵琶学习者。',
'待验证需求：模型音符难以逐一检查，原音定位与后续制谱流程分散。',
'琵琶特点：自由速度、泛音、轮指、双弦和装饰音可能影响识别与比较。',
'需求与效率优势尚无访谈/计时证据，不能把假设写成用户结论。']),
('可操作流程与自主实现',[
'生成初稿后，在音符时间轴点选原音，修改音高、时间或补删音符。',
'模型初稿、当前结果与参考轮廓分别显示，每次修改保留历史。',
'参考MIDI导入、手动对齐与试验性自动定位，提示待确认差异。',
'导出原始/当前MIDI、MusicXML草稿及JSON记录。']),
('技术架构与贡献边界',[
'前端：原生JavaScript / 时间轴 / 原音与片段试听 / 版本状态。',
'后端：FastAPI / ffmpeg / 本地持久化 / 编辑校验 / 导出。',
'识别基础：Spotify Basic Pitch 0.4.0 / 官方ONNX CPU，未训练。',
'自主贡献：校对流程、参考匹配/定位、乐谱草稿与记录工具。',
'现有编辑、MusicXML、序列对齐方法已有先例，不宣称首创。']),
('局部旋律定位：降低手工调时负担',[
'把参考单旋律与原始模型候选音符组作半全局序列匹配。',
'容许多余/遗漏候选，保留八度差异；锚点之间分段映射时间。',
'支持2—100音单旋律；多声部、线索不足或重复段落有明确限制。',
'锚点来自模型，不是独立标注：自动模式不评定起音/时长。',
'候选创新：面向琵琶短片段的校对与制谱流程，效果仍待证明。']),
('实测：功能、公开数据与琵琶输入',[
'56项测试通过；Chromium流程、手机布局、MusicXML独立解析通过。',
'GuitarSet固定12段：起音/音高F1为0.7975，加入结束时间为0.5660。',
'另12段本地验证：分别0.7611、0.5722；参数实验未提高默认结果。',
'训练重叠未核实，吉他结果不是琵琶精度，也不是原创模型提升。',
'三段本人琵琶录音前30秒均跑通；没有独立标注，不报告准确率。']),
('春雨案例：展示线索，也保留不确定性',[
'谱页开头8音提纲仍待确认八度与节奏，不作为正式真值。',
'自动定位候选范围约1.52—10.04秒，保留D5/D4八度差异。',
'原音与模型音符未改写；差异可能来自技法、识别或参考草稿。',
'当前缺口：简谱图片自动识别、三连音/琵琶技法、多声部自动对齐。',
'Windows/MuseScore与真实用户任务效果仍需验证。']),
('下一步与提交边界',[
'先独立核对谱面、演奏音高与时间，再验证差异提示。',
'与同模型直接MIDI流程作同质量任务比较，记录耗时与错误。',
'补真实试用和困难案例，不虚构用户、专利、软著或准确率。',
'保留Basic Pitch、GuitarSet署名；开发使用AI辅助，如实说明贡献。',
'本文件为匿名审核稿，尚未套用官方模板或作为最终材料提交。'])]
for i,(title,items) in enumerate(slides,1):
 c.setFillColor(colors.HexColor('#f4f5ef'));c.rect(0,0,960,540,fill=1,stroke=0)
 c.setFillColor(colors.HexColor('#274632'));c.setFont('STSong-Light',29);c.drawString(48,476,title)
 y=409
 for item in items:
  p=Paragraph(escape(item),style);w,h=p.wrap(860,400);p.drawOn(c,50,y-h);y-=h+20
 c.setFont('STSong-Light',10);c.setFillColor(colors.HexColor('#6f7e6c'))
 c.drawString(48,23,'谱易改 / 审核草稿 / 非提交定稿');c.drawRightString(912,23,f'{i} / {len(slides)}')
 c.showPage()
c.save();print(output)
