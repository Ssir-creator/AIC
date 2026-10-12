"""A score-reading outline, NOT a timed or verified reference for evaluation."""
from pathlib import Path
import io,json,wave
import numpy as np
import pretty_midi
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from notation import export_musicxml

root=Path(__file__).resolve().parents[1]
output=root/'artifacts/春雨开头-旋律提纲待确认'
output.mkdir(exist_ok=True)
# Digits read from the supplied image; octave assignments below are provisional.
digits=[6,7,2,2,1,1,6,5]
# Illustrative octave contour, requires a musician's confirmation.
octaves=[0,0,1,1,1,1,0,0]
major_intervals=[0,2,4,5,7,9,11]
pitches=[62+major_intervals[degree-1]+12*octave for degree,octave in zip(digits,octaves)]
notes=[{'pitch':pitch,'start':i,'end':i+.8,'velocity':80} for i,pitch in enumerate(pitches)]
midi=pretty_midi.PrettyMIDI(initial_tempo=60);instrument=pretty_midi.Instrument(0)
for note in notes:instrument.notes.append(pretty_midi.Note(note['velocity'],note['pitch'],note['start'],note['end']))
midi.instruments.append(instrument);midi.write(str(output/'旋律提纲-非正式参考.mid'))
# Use equal quarter-note durations for the outline, not the source's dotted rhythm.
score_notes=[{**n,'end':n['start']+1} for n in notes]
(output/'旋律提纲-等长音.musicxml').write_bytes(export_musicxml(score_notes,bpm=60,meter='3/4',title='Chunyu outline ONLY: octave unconfirmed, equal-note rhythm'))
rate=22050;audio=np.zeros(rate*9,dtype=np.float64)
for n in notes:
 length=int(.8*rate);t=np.arange(length)/rate
 envelope=np.minimum(t/.025,1)*np.minimum((.8-t)/.12,1)
 tone=.2*np.sin(2*np.pi*440*2**((n['pitch']-69)/12)*t)*envelope
 start=int(n['start']*rate);audio[start:start+length]+=tone
with wave.open(str(output/'旋律提纲试听-非琵琶音色.wav'),'wb') as f:
 f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate);f.writeframes((audio*32767).astype('<i2').tobytes())
(output/'待确认说明.json').write_text(json.dumps({'source':'user supplied Chunyu score page97, opening two measures',
 'digits_from_score':digits,'octave_contour':'provisional, not confirmed',
 'rhythm':'illustrative equal one-second spacing; NOT score rhythm or performance timing',
 'techniques':'not represented','evaluation_allowed':False,
 'notes':notes},ensure_ascii=False,indent=2))
(output/'请先读.txt').write_text('这是《春雨》前两个小节的旋律提纲，不是正式参考曲谱。谱面数字为6 7 2 2 | 1 1 6 5。八度走向暂定；所有音符采用等长节奏，只用于试听，不代表原谱时值或录音时间。没有泛音/轮指等技法。请识谱者确认旋律与八度，再整理真实节奏与录音位置。不得拿此提纲计算识别准确率或判定演奏错误。')
from zipfile import ZipFile,ZIP_DEFLATED
with ZipFile(root/'artifacts/春雨开头-旋律提纲待确认.zip','w',ZIP_DEFLATED) as z:
 for file in output.iterdir():z.write(file,file.name)
print(output)
