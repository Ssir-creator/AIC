"""Mechanical file checks, not a claim of scientific or anonymity approval."""
import json,subprocess
from pathlib import Path
from pypdf import PdfReader
root=Path(__file__).resolve().parents[1]
name='谱易改'
intro=(root/'docs/作品简介.txt').read_text().strip()
checks=[{'item':'作品名称','passed':len(name)<=20,'characters':len(name)},
        {'item':'作品简介','passed':len(intro)<=300,'characters':len(intro)}]
for filename,limit in [('谱易改-技术方案审核稿.pdf',10*1024*1024),('谱易改-答辩审核稿.pdf',None),('谱易改-研发验证佐证审核稿.pdf',None)]:
 path=root/'artifacts'/filename
 reader=PdfReader(path)
 text='\n'.join(page.extract_text() or '' for page in reader.pages)
 checks.append({'item':filename,'passed':path.is_file() and (limit is None or path.stat().st_size<=limit),
                'bytes':path.stat().st_size,'pages':len(reader.pages),
                'metadata_author':str(reader.metadata.author),
                'draft_label_present':any(word in text for word in ['审核','草稿','非提交定稿']),
                'anonymity':'school/advisor names and logos require visual review; cannot infer unnamed institution'})
video=root/'artifacts/谱易改-演示审核稿.mp4'
if video.is_file():
 metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(video)]))
 duration=float(metadata['format']['duration'])
 checks.append({'item':video.name,'passed':180<=duration<=300 and video.stat().st_size<=300*1024*1024,
                'seconds':duration,'bytes':video.stat().st_size,
                'streams':[{'type':s['codec_type'],'codec':s['codec_name']} for s in metadata['streams']]})
else:checks.append({'item':'演示视频','passed':False,'reason':'not yet generated'})
report={'mechanical_checks':checks,'ready_to_submit':False,
        'unresolved':['独立乐谱/音符标注与效果验证','真实用户同任务对比','Windows/MuseScore实际验证',
                      '正式模板与匿名视觉复查','参赛编号命名及百度网盘永久链接','审核稿不是最终提交材料']}
(root/'artifacts/提交材料机械检查.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps(report,indent=2,ensure_ascii=False))
