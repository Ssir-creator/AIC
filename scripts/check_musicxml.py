"""Optional independent score round-trip check; install music21 separately."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music21 import converter
from notation import export_musicxml

cases = [[], [{'pitch':61,'start':.5,'end':2.5},{'pitch':67,'start':1,'end':1.5}],
         [{'pitch':60,'start':0,'end':.875}]]
for notes in cases:
    score = converter.parseData(export_musicxml(notes).decode(), format='musicxml').stripTies()
    actual = sorted((float(n.offset), float(n.quarterLength), n.pitch.midi) for n in score.flatten().notes)
    expected = []
    for note in notes:
        start = math.floor(note['start'] * 8 + .5)
        end = max(start + 1, math.floor(note['end'] * 8 + .5))
        expected.append((start / 4, (end-start) / 4, note['pitch']))
    assert actual == sorted(expected), (actual, expected)
print('3 independent MusicXML round-trip cases passed')
