"""Encode the real browser recording and disclosed original audio excerpt."""
import json, subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
folder=root/'artifacts/video-review'
log=json.loads((folder/'recording-log.json').read_text())
assert log['status']=='completed' and not log['js_errors']
event=log['audio_events'][0]
source=folder/'browser-recording.webm'
duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(source)]))
assert 180<=duration<=300
output=root/'artifacts/谱易改-演示审核稿.mp4'
filters=(f"[1:a]atrim=start={event['source_seconds']}:duration={event['duration']},"
         f"asetpts=PTS-STARTPTS,aresample=44100,adelay={round(event['video_seconds']*1000)}:all=1,apad[a]")
subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','warning','-i',str(source),'-i',event['source'],
    '-filter_complex',filters,'-map','0:v:0','-map','[a]','-t',str(duration),
    '-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','128k','-ac','1','-movflags','+faststart',str(output)],check=True)
assert output.stat().st_size<=300*1024*1024
print(output,round(duration,3),'seconds',output.stat().st_size,'bytes')
