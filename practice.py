"""Reference-guided comparison, not a diagnosis of playing or transcription errors."""
import io
import math
import hashlib
import json
import numpy as np
import pretty_midi
from scipy.optimize import linear_sum_assignment
from alignment import warped_time


def parse_reference(content):
    if not content.startswith(b'MThd'):
        raise ValueError('请上传有效的MIDI曲谱文件（.mid/.midi），不是音频或图片')
    try:
        midi = pretty_midi.PrettyMIDI(io.BytesIO(content))
        notes = []
        for instrument in midi.instruments:
            if instrument.is_drum:
                continue
            for n in instrument.notes:
                if not (21 <= n.pitch <= 108 and math.isfinite(n.start) and math.isfinite(n.end)
                        and 0 <= n.start < n.end <= 120):
                    raise ValueError('参考曲谱音符须在0—120秒内，音高21—108；请先导出对应短片段')
                notes.append({'id':f'ref-{len(notes)}', 'pitch':int(n.pitch),
                              'start':float(n.start),'end':float(n.end),'velocity':int(max(1,n.velocity))})
                if len(notes) > 500:
                    raise ValueError('参考曲谱超过500个音符，请只导出当前练习片段')
    except ValueError:
        raise
    except Exception:
        raise ValueError('无法读取MIDI，请重新导出标准MIDI文件')
    if not notes:
        raise ValueError('参考曲谱没有可比较的非打击乐音符')
    return sorted(notes, key=lambda n:(n['start'],n['pitch'],n['id']))


def compare_reference(notes, reference, duration):
    settings = reference['settings']
    automatic = reference.get('automatic_alignment')
    all_notes = notes
    if automatic:
        notes = [n for n in notes if automatic['scope_start']-.08 <= n['start'] <= automatic['scope_end']+.08]
    expected, excluded = [], 0
    for n in reference['notes']:
        start = warped_time(n['start'], automatic['anchors']) if automatic else n['start'] * settings['scale'] + settings['shift']
        end = warped_time(n['end'], automatic['anchors']) if automatic else n['end'] * settings['scale'] + settings['shift']
        if start < 0 or end > duration + .001:
            excluded += 1
            continue
        expected.append({**n,'start':round(start,4),'end':round(end,4)})
    window = settings['window']
    # Assignment prioritizes the number of temporally plausible pairs, then
    # exact pitch, then onset distance. Dummy columns represent unmatched refs.
    pairs, used = {}, set()
    if expected and notes:
        cost = np.full((len(expected),len(notes)+len(expected)), 2e7, dtype=np.float64)
        cost[:,len(notes):] = 1e7
        for i,r in enumerate(expected):
            for j,n in enumerate(notes):
                distance = abs(r['start']-n['start'])
                if distance <= window:
                    cost[i,j] = (0 if r['pitch']==n['pitch'] else len(expected)+1) + distance/window * .1
        rows, columns = linear_sum_assignment(cost)
        for i,j in zip(rows,columns):
            if j < len(notes) and cost[i,j] < 1e7:
                pairs[int(i)] = int(j)
                used.add(int(j))
    issues = []
    counts = {'pitch':0,'timing':0,'duration':0,'missing':0,'extra':0}
    for i,r in enumerate(expected):
        if i not in pairs:
            counts['missing'] += 1
            issues.append({'kind':'missing','note_id':None,'reference':r,'time':r['start']})
            continue
        n = notes[pairs[i]]
        for kind, mismatch in (
            ('pitch', n['pitch']!=r['pitch']),
            ('timing', not automatic and abs(n['start']-r['start'])>settings['timing_tolerance']+1e-8),
            ('duration', not automatic and abs((n['end']-n['start'])-(r['end']-r['start']))>settings['duration_tolerance']+1e-8),
        ):
            if mismatch:
                counts[kind] += 1
                issues.append({'kind':kind,'note_id':n['id'],'reference':r,'actual':n,'time':n['start']})
    for j,n in enumerate(notes):
        if j not in used:
            counts['extra'] += 1
            issues.append({'kind':'extra','note_id':n['id'],'actual':n,'time':n['start']})
    if automatic:
        counts['timing']=counts['duration']=None
    context={'notes':reference['notes'],'settings':settings,'automatic':automatic}
    for issue in issues:
        issue['id']=hashlib.sha256(json.dumps({'context':context,'issue':issue},sort_keys=True).encode()).hexdigest()[:24]
    return {'settings':settings,'expected_notes':expected,'excluded_reference_notes':excluded,
            'uncompared_recording_notes':len(all_notes)-len(notes),
            'automatic_alignment':automatic,
            'matched_pairs':len(pairs),'counts':counts,
            'issues':sorted(issues,key=lambda x:(x['time'],x['kind'])),
            'interpretation':'参考差异不是错误诊断；可能来自演奏、模型识别或时间对齐，请听原音确认。'}
