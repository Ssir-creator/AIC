"""Reproducible, explicitly provisional score-guided localization case."""
import json,sys,uuid,shutil,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alignment import auto_align
from practice import parse_reference,compare_reference
from app import DATA,write_project,Alignment
root=Path(__file__).resolve().parents[1]
output=root/'artifacts/chunyu-assisted-case';output.mkdir(exist_ok=True)
source=root/'artifacts/pipa-diagnostic-20261011/00'
notes=json.loads((source/'model-notes.json').read_text())
outline=root/'artifacts/春雨开头-旋律提纲待确认/旋律提纲-非正式参考.mid'
reference={'filename':'春雨开头-八度与节奏待确认.mid','notes':parse_reference(outline.read_bytes()),
           'settings':Alignment().model_dump(),'status':'unverified_score_outline',
           'limitations':'谱面数字人工读取，八度暂定，参考时值仅为等长旋律提纲，不是正式曲谱。'}
reference['automatic_alignment']=auto_align(reference['notes'],notes)
comparison=compare_reference(notes,reference,30)
report={'case':'Chunyu opening score-outline assisted localization','reference':reference,'practice':comparison,
        'independent_ground_truth':False,'accuracy_claim':None,'human_validation':'not completed',
        'notes_modified':False,'scope':'opening two measures only; remaining recording not assessed'}
(output/'assisted-case.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
shutil.copyfile(outline,output/'reference-outline-unverified.mid')
subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(source/'first-30s.wav'),'-ss','1.3','-t','9.2',str(output/'opening-context.wav')],check=True)
folder=DATA/str(uuid.uuid4());folder.mkdir();shutil.copyfile(source/'normalized.wav',folder/'audio.wav')
p={'id':folder.name,'filename':'春雨前30秒 / 自动定位研究案例','duration':30.,'revision':0,
   'notes':notes,'original_notes':notes.copy(),'history':[],'reference':reference,
   'inference_seconds':1.889,'model':'Spotify Basic Pitch 0.4.0 ONNX CPU',
   'limitations':reference['limitations'],'reference_history':[{'source':'build_chunyu_case.py','after':reference}]}
write_project(folder,p)
(output/'private-project.json').write_text(json.dumps({'id':p['id']},indent=2))
print(json.dumps({'id':p['id'],'anchors':len(reference['automatic_alignment']['anchors']),
                  'scope':[reference['automatic_alignment']['scope_start'],reference['automatic_alignment']['scope_end']],
                  'candidate_counts':comparison['counts'],'not_an_accuracy_score':True},ensure_ascii=False))
