import pytest
from alignment import auto_align,warped_time
from practice import compare_reference
from app import Alignment


def n(id_,pitch,start,end):
    return {'id':id_,'pitch':pitch,'start':start,'end':end,'velocity':80}


def refs():
    return [n('r1',60,0,.8),n('r2',62,1,1.8),n('r3',64,2,2.8),n('r4',65,3,3.8)]


def test_variable_tempo_harmonic_noise_and_prefix():
    notes=[n('prefix',80,0,.2),n('a',60,2,2.5),n('harmonic',72,2,2.5),
           n('b',62,2.6,3),n('noise',33,3.3,3.4),n('c',64,4,4.6),n('d',65,5,5.9)]
    alignment=auto_align(refs(),notes)
    assert [a['actual_note_id'] for a in alignment['anchors']]==['a','b','c','d']
    assert alignment['source']=='original_model_notes'
    assert alignment['independent_ground_truth'] is False
    assert warped_time(.5,alignment['anchors'])==2.3
    assert warped_time(4,alignment['anchors'])==6


def test_octave_candidate_is_preserved_as_difference_not_corrected():
    notes=[n('a',60,2,2.5),n('b',74,3,3.5),n('c',64,4,4.5),n('d',65,5,5.5)]
    alignment=auto_align(refs(),notes)
    reference={'notes':refs(),'settings':Alignment().model_dump(),'automatic_alignment':alignment}
    comparison=compare_reference(notes,reference,8)
    assert comparison['counts']['pitch']==1
    assert comparison['counts']['timing'] is None and comparison['counts']['duration'] is None
    assert notes[1]['pitch']==74


def test_repeated_motif_is_marked_ambiguous():
    notes=[n(str(i)+r['id'],r['pitch'],r['start']+shift,r['end']+shift)
           for i,shift in enumerate([1,10]) for r in refs()]
    assert auto_align(refs(),notes)['ambiguous_occurrence']


@pytest.mark.parametrize('reference,actual',[
    (refs(),[]),([n('r',60,0,1)],[]),
    ([n('r1',60,0,1),n('r2',64,.2,1.2)],[]),
    (refs(),[n('a',90,0,.5),n('b',91,1,1.5),n('c',92,2,2.5)]),
])
def test_insufficient_or_unsupported_alignment_rejected(reference,actual):
    with pytest.raises(ValueError):auto_align(reference,actual)


def test_auto_alignment_api_keeps_original_and_manual_reset(tmp_path,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app,'DATA',tmp_path)
    folder=tmp_path/'6ea63d56-0dac-4cda-8b65-a902bb1132b8';folder.mkdir()
    notes=[n('a',60,2,2.7),n('b',62,3,3.7),n('c',64,4.5,5.2),n('d',65,6,6.7)]
    reference={'filename':'confirmed.mid','notes':refs(),'settings':Alignment().model_dump()}
    app.write_project(folder,{'id':folder.name,'notes':notes,'original_notes':notes.copy(),
                             'duration':8,'reference':reference,'revision':0,'history':[]})
    with TestClient(app.app) as client:
        base='/api/projects/'+folder.name
        response=client.post(base+'/reference/auto-align')
        assert response.status_code==200,response.text
        p=response.json()
        assert p['revision']==0 and p['original_notes']==notes and p['notes'][0]['pitch']==60
        assert p['practice']['counts']['timing'] is None
        assert p['reference']['automatic_alignment']['matched_reference_notes']==4
        assert client.get(base+'/report').json()['original_practice']['counts']['duration'] is None
        response=client.put(base+'/reference/alignment',json={'shift':2})
        assert response.status_code==200
        assert 'automatic_alignment' not in response.json()['reference']
        assert response.json()['practice']['counts']['timing'] is not None
        assert len(response.json()['reference_history'])==2
