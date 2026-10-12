import io
import json
import pretty_midi
import pytest
from fastapi.testclient import TestClient
import app
from practice import compare_reference, parse_reference


def n(id_,pitch,start,end):
    return {'id':id_,'pitch':pitch,'start':start,'end':end,'velocity':80}


def ref(notes, **changes):
    return {'notes':notes,'settings':{**app.Alignment().model_dump(),**changes}}


def midi_bytes(notes):
    midi=pretty_midi.PrettyMIDI()
    instrument=pretty_midi.Instrument(0)
    for note in notes:
        instrument.notes.append(pretty_midi.Note(80,note['pitch'],note['start'],note['end']))
    midi.instruments.append(instrument)
    stream=io.BytesIO();midi.write(stream)
    return stream.getvalue()


def test_independent_difference_categories_and_correction():
    gold=[n('r1',60,0,.5),n('r2',62,1,1.5),n('r3',64,2,2.5),n('r4',65,3,3.5)]
    actual=[n('a1',61,0,.5),n('a2',62,1.15,1.65),n('a3',64,2,2.8),n('extra',72,4,4.5)]
    result=compare_reference(actual,ref(gold),5)
    assert result['counts']=={'pitch':1,'timing':1,'duration':1,'missing':1,'extra':1}
    assert result['matched_pairs']==3
    actual[0]['pitch']=60
    assert compare_reference(actual,ref(gold),5)['counts']['pitch']==0
    assert gold[0]['pitch']==60


def test_polyphony_matched_by_pitch_not_input_order():
    gold=[n('r1',60,0,.5),n('r2',67,0,.5)]
    actual=[n('a2',67,.01,.51),n('a1',60,.02,.52)]
    assert not compare_reference(actual,ref(gold),1)['issues']


def test_alignment_exclusion_and_empty_predictions():
    gold=[n('r1',60,1,2),n('r2',62,3,4)]
    actual=[n('a1',60,0,.5)]
    result=compare_reference(actual,ref(gold,scale=.5,shift=-.5),1)
    assert not result['issues'] and result['excluded_reference_notes']==1
    assert compare_reference([],ref(gold),5)['counts']['missing']==2


def test_far_apart_onsets_are_not_forced_into_pitch_errors():
    result=compare_reference([n('a',61,1,1.5)],ref([n('r',60,0,.5)]),2)
    assert result['counts']['pitch']==0
    assert result['counts']['missing']==1 and result['counts']['extra']==1


@pytest.mark.parametrize('content',[b'not midi', midi_bytes([]), midi_bytes([n('bad',60,0,121)])])
def test_invalid_reference(content):
    with pytest.raises(ValueError):
        parse_reference(content)


def test_reference_api_persistence_alignment_report_edit_and_remove(tmp_path,monkeypatch):
    monkeypatch.setattr(app,'DATA',tmp_path)
    folder=tmp_path/'a5e16582-8377-4794-b4f4-d7cbe85b3afc';folder.mkdir()
    notes=[n('a',61,.2,.7)]
    p={'id':folder.name,'duration':2,'revision':0,'notes':notes,'original_notes':notes.copy(),'history':[]}
    app.write_project(folder,p)
    with TestClient(app.app) as client:
        base='/api/projects/'+folder.name
        response=client.post(base+'/reference',files={'file':('example.mid',midi_bytes([n('r',60,0,.5)]))})
        assert response.status_code==200,response.text
        assert response.json()['revision']==0
        assert response.json()['practice']['counts']['pitch']==1
        response=client.put(base+'/reference/alignment',json={'shift':.2})
        assert response.status_code==200
        assert response.json()['practice']['counts']['timing']==0
        corrected=[{**notes[0],'pitch':60}]
        result=client.put(base+'/notes',json={'revision':0,'notes':corrected}).json()
        assert result['practice']['counts']['pitch']==0
        report=client.get(base+'/report').json()
        assert report['practice']['counts']['pitch']==0
        assert report['original_practice']['counts']['pitch']==1
        assert report['original_notes']==notes
        assert len(report['reference_history'])==2
        assert client.get(base).json()['reference']['settings']['shift']==.2
        assert client.put(base+'/reference/alignment',json={'window':.05,'timing_tolerance':.2}).status_code==422
        assert client.post(base+'/reference',files={'file':('bad.mid',b'bad')}).status_code==422
        assert client.get(base).json()['reference']['notes']
        result=client.delete(base+'/reference').json()
        assert 'practice' not in result and 'reference' not in result
        assert result['original_notes']==notes
        assert client.put(base+'/reference/alignment',json={}).status_code==422
