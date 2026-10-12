"""Explicit user-entered numbered notation; no image OCR or inferred rhythm."""
import re
from fractions import Fraction

KEYS={'C':0,'C#':1,'D':2,'Eb':3,'E':4,'F':5,'F#':6,'G':7,'Ab':8,'A':9,'Bb':10,'B':11}
DEGREES=[0,2,4,5,7,9,11]
TOKEN=re.compile(r"([#b]?)([0-7])([',]*)(?::([0-9]+(?:\.[0-9]+)?(?:/[0-9]+)?))?")

def parse_jianpu(text,key='D',octave=4,bpm=60):
    if key not in KEYS or octave not in (3,4,5) or not 30<=bpm<=240:
        raise ValueError('调号、主音八度或速度无效')
    tokens=text.replace('|',' ').split()
    if not tokens or len(tokens)>500:
        raise ValueError('请录入1—500个音或休止，音符之间用空格分开')
    notes=[];cursor=0.
    for token in tokens:
        match=TOKEN.fullmatch(token)
        if not match:raise ValueError(f'无法读取“{token}”：例如6:1、2\':0.5、0:1；用空格分开')
        accidental,degree,marks,length=match.groups();degree=int(degree)
        try:beats=float(Fraction(length or '1'))
        except (ValueError,ZeroDivisionError):raise ValueError('拍数必须为有效正数')
        if not 0<beats<=16:raise ValueError('单个音或休止的拍数须大于0且不超过16')
        if "'" in marks and ',' in marks:raise ValueError('一个音不能同时标高八度与低八度')
        end=cursor+beats*60/bpm
        if end>120+.0001:raise ValueError('参考片段超过120秒，请只录入短片段')
        if degree:
            pitch=12*(octave+1)+KEYS[key]+DEGREES[degree-1]+12*(marks.count("'")-marks.count(','))
            pitch+=(1 if accidental=='#' else -1 if accidental=='b' else 0)
            if not 21<=pitch<=108:raise ValueError('音高超出支持范围，请检查八度')
            notes.append({'id':f'ref-{len(notes)}','pitch':pitch,'start':round(cursor,6),'end':round(end,6),'velocity':80})
        elif accidental or marks:raise ValueError('休止0不能标升降号或八度')
        cursor=end
    if not notes:raise ValueError('参考不能只有休止')
    return notes
