"""Explicitly crop user recordings and run inference; no ground-truth accuracy claim."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import normalize_audio, transcribe, write_project, public_project, DATA
from notation import export_musicxml
import uuid

parser=argparse.ArgumentParser()
parser.add_argument('recordings', nargs='+',type=Path)
parser.add_argument('--seconds',type=float,default=30)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if not .2 <= args.seconds <= 60: parser.error('seconds must be .2—60')
if args.output.exists(): parser.error('Use a fresh output directory to preserve previous results')
args.output.mkdir(parents=True)
protocol={'selection':'first requested seconds of EVERY supplied recording, chosen before inference',
          'seconds':args.seconds,'source':'user supplied recordings; authorship/permission pending confirmation',
          'interpretation':'functional diagnosis only: no independent pitch/timing ground truth',
          'model':'Spotify Basic Pitch 0.4.0 ONNX CPU','results':[]}
(args.output/'protocol.json').write_text(json.dumps(protocol,indent=2,ensure_ascii=False))
failed=False
for i,source in enumerate(args.recordings):
    result={'filename':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    directory=args.output/f'{i:02d}'
    directory.mkdir()
    try:
        metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(source)]))
        result['full_duration']=float(metadata['format']['duration'])
        (directory/'audio-metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False))
        clip=directory/f'first-{args.seconds:g}s.wav'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(source),'-t',str(args.seconds),'-ac','1','-ar','22050',str(clip)],check=True,capture_output=True)
        duration=normalize_audio(clip,directory/'normalized.wav')
        started=time.perf_counter();notes=transcribe(directory/'normalized.wav',duration)
        if len(notes) > 2000:
            raise ValueError('More than 2000 notes; shorten the excerpt for editable projects')
        result.update(status='completed',clip_start=0,clip_duration=duration,note_count=len(notes),inference_seconds=time.perf_counter()-started)
        (directory/'model-notes.json').write_text(json.dumps(notes,indent=2,ensure_ascii=False))
        (directory/'model-draft-120bpm.musicxml').write_bytes(export_musicxml(notes))
        # Private persistent UI project, not included in the development bundle.
        import shutil
        folder=DATA/str(uuid.uuid4());folder.mkdir()
        shutil.copyfile(directory/'normalized.wav',folder/'audio.wav')
        project={'id':folder.name,'filename':source.stem+f'（前{args.seconds:g}秒）','duration':round(duration,4),
                 'inference_seconds':round(result['inference_seconds'],3),'model':protocol['model'],
                 'revision':0,'notes':notes,'original_notes':notes.copy(),'history':[],
                 'limitations':'真实琵琶录音初稿，未经独立标注；120BPM草稿不是原曲实际节奏。'}
        write_project(folder,project)
        result['private_project_id']=project['id']
    except Exception as exc:
        failed=True;result.update(status='failed',reason=str(exc))
    protocol['results'].append(result)
    (args.output/'results.json').write_text(json.dumps(protocol,indent=2,ensure_ascii=False))
    print(json.dumps(result,ensure_ascii=False),flush=True)
raise SystemExit(1 if failed else 0)
