import copy
import pytest
from independent_review import evaluate_review

@pytest.fixture
def case():
    note={'pitch':60,'start':1.,'end':1.5}
    project={'audio_sha256':'test-hash','original_notes':[note,{'pitch':72,'start':15.,'end':16.}], 'notes':[note]}
    review={'schema':'aic-independent-review-v1','audio_sha256':'test-hash',
            'status':'human_confirmed_not_automatically_verified','independent':True,'complete':True,
            'reviewer':'TEST-NOT-REAL-USER','scope':{'start':0.,'end':3.},
            'notes':[{**note,'certainty':'confirmed'}]}
    return project,review

def test_partial_scope_does_not_evaluate_unannotated_recording(case):
    p,r=case;out=evaluate_review(p,r,'test-hash')
    assert out['model_draft']['onset_only']['f1']==1
    assert out['model_draft']['unassessed_onsets']==1

def test_uncertain_note_cannot_be_ground_truth(case):
    p,r=case;r['notes'][0]['certainty']='uncertain'
    with pytest.raises(ValueError,match='待确认'):evaluate_review(p,r,'test-hash')

def test_wrong_audio_is_rejected(case):
    p,r=case
    with pytest.raises(ValueError,match='原音'):evaluate_review(p,r,'another-hash')

def test_prediction_from_another_audio_or_old_record_is_rejected(case):
    p,r=case
    for digest in [None,'other-hash']:
        p['audio_sha256']=digest
        with pytest.raises(ValueError,match='模型记录'):evaluate_review(p,r,'test-hash')

def test_incomplete_or_invalid_scope_is_rejected(case):
    p,r=case
    for change in [{'complete':False},{'scope':{'start':0.,'end':float('nan')}},{'scope':{'start':1.2,'end':3}}]:
        altered=copy.deepcopy(r);altered.update(change)
        with pytest.raises(ValueError):evaluate_review(p,altered,'test-hash')
