import io
import json
from zipfile import ZipFile,ZIP_DEFLATED
import pytest
from jianpu import parse_jianpu
from test_workflow import client,project

def test_numbered_key_octaves_rests_and_triplet_beats():
    notes=parse_jianpu("6:1 0:0.5 2':1/3 1,:1",key='D',octave=4,bpm=60)
    assert [n['pitch'] for n in notes]==[71,76,50]
    assert notes[1]['start']==1.5 and abs(notes[1]['end']-1.833333)<1e-6
    assert parse_jianpu('b3 #4',key='C')[0]['pitch']==63

@pytest.mark.parametrize('text',['0:1','1:0','1:1/0','8','1:20',"1',",'0\'','1:1 bad'])
def test_bad_reference_is_rejected(text):
    with pytest.raises(ValueError):parse_jianpu(text)

def enter_reference(c,p):
    r=c.post('/api/projects/'+p['id']+'/reference/jianpu',json={'text':'1:1','key':'Bb','bpm':60})
    assert r.status_code==200,r.text
    return r.json()

def test_human_decision_does_not_edit_notes_and_stale_alignment_rejected(client,project):
    p=enter_reference(client,project);base='/api/projects/'+p['id']
    assert p['reference']['status']=='human_entered_unverified'
    assert p['reference']['source']['independent_ground_truth'] is False
    issue=next(i for i in p['practice']['issues'] if i['kind']=='pitch')
    decision={'revision':p['revision'],'issue_id':issue['id'],'verdict':'recognition_error','comment':'TEST ONLY, not a musician finding'}
    r=client.put(base+'/issue-review',json=decision)
    assert r.status_code==200
    assert r.json()['notes']==p['notes']
    assert r.json()['practice']['counts']==p['practice']['counts']
    assert any(i['human_review'] for i in r.json()['practice']['issues'])
    assert client.put(base+'/reference/alignment',json={'shift':.5}).status_code==200
    assert client.put(base+'/issue-review',json=decision).status_code==409

def test_complete_backup_restore_preserves_audio_original_edits_reference_and_reviews(client,project):
    p=enter_reference(client,project);base='/api/projects/'+p['id']
    issue=p['practice']['issues'][0]
    assert client.put(base+'/issue-review',json={'revision':0,'issue_id':issue['id'],'verdict':'uncertain','comment':'TEST ONLY'}).status_code==200
    clean=[{k:n[k] for k in ('id','pitch','start','end','velocity')} for n in p['notes']];clean[0]['pitch']+=1
    edited=client.put(base+'/notes',json={'revision':0,'notes':clean}).json()
    before=client.get(base+'/report').json()
    backup=client.get(base+'/backup');assert backup.status_code==200
    r=client.post('/api/projects/restore',files={'file':('backup.zip',backup.content,'application/zip')})
    assert r.status_code==200,r.text
    after=r.json();assert after['id']!=p['id'] and after['revision']==1
    assert after['original_notes']==edited['original_notes'] and after['notes']==edited['notes']
    assert after['reference']==before['reference']
    assert after['issue_reviews']==before['issue_reviews']
    assert after['audio_sha256']==before['audio_sha256']
    assert client.get(base).status_code==200
    assert client.get('/api/projects/'+after['id']+'/audio').content[:4]==b'RIFF'

def rewritten_zip(data,extra=None,change=None):
    out=io.BytesIO()
    with ZipFile(io.BytesIO(data)) as z:files={n:z.read(n) for n in z.namelist()}
    if extra:files.update(extra)
    if change:
        p=json.loads(files['project.json']);change(p);files['project.json']=json.dumps(p).encode()
        import hashlib
        m=json.loads(files['manifest.json']);m['files']['project.json']=hashlib.sha256(files['project.json']).hexdigest();files['manifest.json']=json.dumps(m).encode()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        for n,v in files.items():z.writestr(n,v)
    return out.getvalue()

def test_archive_paths_hash_and_invalid_notes_do_not_overwrite_or_leave_projects(client,project):
    import app
    data=client.get('/api/projects/'+project['id']+'/backup').content
    before=set(app.DATA.iterdir())
    for bad in [rewritten_zip(data,{'../escape':'malicious'}),rewritten_zip(data,{'audio.wav':b'changed'}),
                rewritten_zip(data,change=lambda p:p['notes'][0].update(end=10))]:
        r=client.post('/api/projects/restore',files={'file':('bad.zip',bad)})
        assert r.status_code==422,r.text
        assert set(app.DATA.iterdir())==before


def test_independent_evaluation_uses_synthetic_truth_and_rejects_model_reference(client,project):
    base='/api/projects/'+project['id']
    review={'schema':'aic-independent-review-v1','audio_sha256':project['audio_sha256'],
            'status':'human_confirmed_not_automatically_verified','independent':True,'complete':True,
            'reviewer':'TEST-SYNTHETIC-NOT-USER','scope':{'start':0,'end':2},
            'notes':[{'pitch':69,'start':0,'end':2,'certainty':'confirmed'}]}
    # Expected tone comes from fixture synthesis, not the model's note predictions.
    r=client.post(base+'/evaluation',files={'file':('synthetic-test.json',json.dumps(review).encode())})
    assert r.status_code==200,r.text
    assert r.json()['reference_notes']==1 and r.json()['note_revision']==0
    assert client.get(base+'/report').json()['independent_evaluation']['reviewer']=='TEST-SYNTHETIC-NOT-USER'
    for invalid in [[],{'notes':project['original_notes']},{**review,'scope':{'start':0,'end':30}},{**review,'complete':False}]:
        assert client.post(base+'/evaluation',files={'file':('invalid.json',json.dumps(invalid).encode())}).status_code==422
