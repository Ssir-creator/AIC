import xml.etree.ElementTree as ET
import pytest
from notation import export_musicxml


def test_triplet_grid_preserves_three_equal_notes_and_ratio():
    import xml.etree.ElementTree as ET
    notes=[{'pitch':60+i,'start':i/3,'end':(i+1)/3} for i in range(3)]
    root=ET.fromstring(export_musicxml(notes,bpm=60,grid='eighth_triplet'))
    assert root.findtext('.//divisions')=='3'
    pitched=root.findall('.//note[pitch]')
    assert len(pitched)==3
    assert all(n.findtext('duration')=='1' and n.findtext('type')=='eighth' for n in pitched)
    assert all(n.findtext('time-modification/actual-notes')=='3' and n.findtext('time-modification/normal-notes')=='2' for n in pitched)


def n(pitch, start, end):
    return {'pitch': pitch, 'start': start, 'end': end}


def timeline(xml):
    root = ET.fromstring(xml)
    cursor = 0
    events = []
    for measure in root.findall('./part/measure'):
        for item in measure:
            if item.tag == 'backup':
                cursor -= int(item.findtext('duration'))
            elif item.tag == 'note':
                duration = int(item.findtext('duration'))
                if item.find('pitch') is not None:
                    events.append((cursor, duration, item.findtext('voice'), item.findtext('pitch/step'),
                                   [t.get('type') for t in item.findall('tie')]))
                cursor += duration
    return root, events, cursor


def test_overlap_rest_sharp_tie_preserved():
    root, events, end = timeline(export_musicxml([n(61, .5, 2.5), n(67, 1, 1.5)], bpm=120))
    assert events == [(4,12,'1','C',['start']), (8,4,'2','G',[]), (16,4,'1','C',['stop'])]
    assert root.findtext('.//pitch/alter') == '1'
    assert end == 32
    for measure in root.findall('./part/measure'):
        for voice in ('1', '2'):
            assert sum(int(note.findtext('duration')) for note in measure.findall('note')
                       if note.findtext('voice') == voice) == 16


def test_origin_meter_tempo_and_short_notes():
    root, events, end = timeline(export_musicxml([n(60,0,.1), n(69,1,1.01)], bpm=60,meter='6/8',origin=1))
    assert events == [(0,1,'1','A',[])]
    assert root.findtext('.//time/beats') == '6'
    assert root.find('.//sound').get('tempo') == '60'
    assert end == 12


def test_nonstandard_duration_tied_and_empty_score():
    _, events, _ = timeline(export_musicxml([n(60,0,.875)], bpm=120))
    assert events == [(0,6,'1','C',['start']), (6,1,'1','C',['stop'])]
    _, events, end = timeline(export_musicxml([]))
    assert events == [] and end == 16


@pytest.mark.parametrize('settings', [{'bpm':float('nan')},{'bpm':241},{'meter':'5/7'},{'origin':-1}])
def test_invalid_settings(settings):
    with pytest.raises(ValueError):
        export_musicxml([], **settings)
