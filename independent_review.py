"""Validate declared independent annotation before scoped note evaluation."""
from evaluation import evaluate_notes,PROTOCOL
import math

def evaluate_review(project,review,audio_sha256):
    if review.get('schema')!='aic-independent-review-v1' or review.get('audio_sha256')!=audio_sha256:
        raise ValueError('核对记录与原音不匹配')
    if project.get('audio_sha256')!=audio_sha256:
        raise ValueError('模型记录未确认来自同一原音；请用当前版本重新上传该原音并导出记录')
    if (review.get('status')!='human_confirmed_not_automatically_verified'
        or review.get('independent') is not True or review.get('complete') is not True
        or not str(review.get('reviewer','')).strip()):
        raise ValueError('必须有匿名编号、独立且完整核对的确认记录')
    scope=review.get('scope',{});start=scope.get('start');end=scope.get('end')
    if any(not isinstance(t,(int,float)) or not math.isfinite(t) for t in (start,end)) or start<0 or end<=start:
        raise ValueError('核对范围无效')
    notes=review.get('notes',[])
    if not notes or any(n.get('certainty')!='confirmed' for n in notes):
        raise ValueError('仍有待确认音符或无音符')
    if any(n['start']<start or n['end']>end for n in notes):
        raise ValueError('标注超出核对范围')
    report={'scope':scope,'protocol':PROTOCOL,'reviewer':review['reviewer'],
        'audio_sha256':audio_sha256,'reference_notes':len(notes),
        'verification':'human declaration, not independently certified by software',
        'boundary_policy':'compare predicted onsets in [start,end); clip predicted ends to scope end; earlier onsets unassessed',
        'warning':'仅评测完整核对范围。边界截断可能影响结束时间指标；手动时间精度须另行复核。人工结果提升不是基础模型提升。'}
    for label,key in [('model_draft','original_notes'),('human_reviewed','notes')]:
        prediction=project[key]
        scoped=[{**n,'end':min(n['end'],end)} for n in prediction if start<=n['start']<end]
        report[label]=evaluate_notes(notes,scoped)
        report[label]['unassessed_onsets']=len(prediction)-len(scoped)
        report[label]['ends_clipped']=sum(n['end']>end for n in prediction if start<=n['start']<end)
    return report
