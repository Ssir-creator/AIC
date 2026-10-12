"""Provisional monophonic motif alignment against ORIGINAL model note events.

Semi-global sequence alignment, not independent truth or a playing-error detector.
"""
import numpy as np


def pitch_cost(expected, actual):
    distance=abs(expected-actual)
    if distance==0:return 0.
    if distance==12:return .45
    return .7+min(distance,12)/24


def auto_align(reference_notes, original_notes):
    refs=sorted(reference_notes,key=lambda n:(n['start'],n['pitch']))
    if not 2 <= len(refs) <= 100:
        raise ValueError('自动定位支持2—100个参考旋律音，请选取少量小节')
    if any(a['end']>b['start']+.01 for a,b in zip(refs,refs[1:])):
        raise ValueError('自动定位暂支持单旋律参考；双弦或重叠声部请用手动对齐')
    groups=[]
    for note in sorted(original_notes,key=lambda n:(n['start'],n['pitch'])):
        if not groups or note['start']-groups[-1]['start']>.08:
            groups.append({'start':note['start'],'notes':[]})
        groups[-1]['notes'].append(note)
    if not groups:raise ValueError('模型初稿没有音符，无法自动定位')
    m,k=len(refs),len(groups)
    dp=np.full((m+1,k+1),np.inf)
    dp[0,:]=0 # Free prefix: find the reference as a subsequence.
    dp[:,0]=np.arange(m+1)*.9
    back=np.zeros((m+1,k+1),dtype=np.uint8)
    back[1:,0]=1
    candidates={}
    for i,r in enumerate(refs,1):
        for j,g in enumerate(groups,1):
            # Velocity breaks ties only; never treated as model confidence.
            note=min(g['notes'],key=lambda n:(pitch_cost(r['pitch'],n['pitch']),-n['velocity'],n['id']))
            candidates[i,j]=note
            values=(dp[i-1,j-1]+pitch_cost(r['pitch'],note['pitch']),dp[i-1,j]+.9,dp[i,j-1]+.18)
            op=int(np.argmin(values));dp[i,j]=values[op];back[i,j]=op
    endpoint=int(np.argmin(dp[m,1:]))+1
    pairs=[];i,j=m,endpoint
    while i:
        op=int(back[i,j])
        if j and op==0:
            pairs.append({'reference_id':refs[i-1]['id'],'reference_start':refs[i-1]['start'],
                          'audio_start':groups[j-1]['start'],'actual_note_id':candidates[i,j]['id'],
                          'reference_pitch':refs[i-1]['pitch'],'actual_pitch':candidates[i,j]['pitch'],
                          'actual_end':candidates[i,j]['end']})
            i-=1;j-=1
        elif op==1 or not j:i-=1
        else:j-=1
    pairs.reverse()
    if len(pairs)<max(2,int(np.ceil(m*.6))):
        raise ValueError('未找到足够连续的旋律线索，请缩短参考或使用手动对齐')
    if sum(p['reference_pitch']==p['actual_pitch'] for p in pairs)<len(pairs)/2:
        raise ValueError('音高吻合线索不足，自动定位不可靠，请检查参考调号或手动对齐')
    first,last=pairs[0]['audio_start'],pairs[-1]['audio_start']
    ambiguous=any(abs(groups[e-1]['start']-last)>max(1,(last-first)*.5)
                  and dp[m,e]<=dp[m,endpoint]+.05 for e in range(1,k+1))
    return {'method':'semi-global-sequence-dp-v1','source':'original_model_notes',
            'independent_ground_truth':False,'timing_assessment_available':False,
            'anchors':pairs,'matched_reference_notes':len(pairs),'total_reference_notes':m,
            'ambiguous_occurrence':ambiguous,'alignment_cost':float(dp[m,endpoint]),
            'scope_start':first,'scope_end':max(last,pairs[-1]['actual_end']),
            'warning':'自动对齐位置来源于模型初稿，不是人工标注；不评定起音/时长，音高差异仍需听音核对。'}


def warped_time(value, anchors):
    source=[a['reference_start'] for a in anchors]
    target=[a['audio_start'] for a in anchors]
    if value<source[0]:
        index=0
    elif value>source[-1]:
        index=len(source)-2
    else:
        return float(np.interp(value,source,target))
    slope=(target[index+1]-target[index])/(source[index+1]-source[index])
    return target[index]+(value-source[index])*slope
