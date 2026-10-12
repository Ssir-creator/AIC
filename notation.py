"""Deterministic, user-configured MusicXML draft; no beat or meter inference."""
from __future__ import annotations
import math
import xml.etree.ElementTree as ET

METERS = {'2/4': (2, 4), '3/4': (3, 4), '4/4': (4, 4), '6/8': (6, 8)}
# A grid unit is one sixteenth note; divisions are four per quarter.
VALUES = [(24, 'whole', True), (16, 'whole', False), (12, 'half', True),
          (8, 'half', False), (6, 'quarter', True), (4, 'quarter', False),
          (3, 'eighth', True), (2, 'eighth', False), (1, '16th', False)]
PITCHES = [('C', 0), ('C', 1), ('D', 0), ('D', 1), ('E', 0), ('F', 0),
           ('F', 1), ('G', 0), ('G', 1), ('A', 0), ('A', 1), ('B', 0)]


def sub(parent, tag, text=None, **attrs):
    element = ET.SubElement(parent, tag, {key: str(value) for key, value in attrs.items()})
    if text is not None:
        element.text = str(text)
    return element


def export_musicxml(notes, bpm=120., meter='4/4', origin=0., title='Reviewed note draft'):
    if not math.isfinite(bpm) or not 30 <= bpm <= 240 or meter not in METERS:
        raise ValueError('速度须为30—240 BPM，拍号为2/4、3/4、4/4或6/8')
    if not math.isfinite(origin) or not 0 <= origin <= 60:
        raise ValueError('起拍时间须为0—60秒')
    beats, beat_type = METERS[meter]
    measure_units = beats * 16 // beat_type
    scale = bpm / 60 * 4
    quantized = []
    for n in notes:
        if n['end'] <= origin:
            continue
        start = math.floor(max(0, n['start'] - origin) * scale + .5)
        end = max(start + 1, math.floor((n['end'] - origin) * scale + .5))
        quantized.append((start, end, n['pitch']))
    # Preserve overlapping notes as separate voices, never silently discard them.
    voices, ends = [], []
    for item in sorted(quantized):
        voice = next((i for i, end in enumerate(ends) if end <= item[0]), len(voices))
        if voice == len(voices):
            voices.append([])
            ends.append(0)
        voices[voice].append(item)
        ends[voice] = item[1]
    voices = voices or [[]]
    count = max(1, math.ceil(max(ends, default=0) / measure_units))
    if len(voices) > 32 or count > 480:
        raise ValueError('重叠声部或小节过多，请先校对音符或缩短录音')
    root = ET.Element('score-partwise', version='4.0')
    sub(sub(root, 'work'), 'work-title', title)
    identification = sub(root, 'identification')
    sub(identification, 'creator', '谱易改 / Spotify Basic Pitch + manual review', type='software')
    miscellaneous = sub(identification, 'miscellaneous')
    for name, value in [('bpm-quarter-note', bpm), ('meter', meter),
                        ('audio-origin-seconds', origin), ('grid', 'sixteenth-note'),
                        ('beat-detection', 'none: user configured')]:
        sub(miscellaneous, 'miscellaneous-field', value, name=name)
    part_list = sub(root, 'part-list')
    sub(sub(part_list, 'score-part', id='P1'), 'part-name', 'Reviewed notes')
    part = sub(root, 'part', id='P1')

    def segment(measure, start, end, pitch, voice, full_start=None, full_end=None):
        cursor = start
        while cursor < end:
            length, type_, dotted = next(v for v in VALUES if v[0] <= end - cursor)
            note = sub(measure, 'note')
            if pitch is None:
                sub(note, 'rest')
            else:
                step, alter = PITCHES[pitch % 12]
                p = sub(note, 'pitch')
                sub(p, 'step', step)
                if alter:
                    sub(p, 'alter', alter)
                sub(p, 'octave', pitch // 12 - 1)
            sub(note, 'duration', length)
            ties = []
            if pitch is not None:
                if cursor > full_start:
                    ties.append('stop')
                if cursor + length < full_end:
                    ties.append('start')
                for tie in ties:
                    sub(note, 'tie', type=tie)
            sub(note, 'voice', voice)
            sub(note, 'type', type_)
            if dotted:
                sub(note, 'dot')
            if ties:
                notation = sub(note, 'notations')
                for tie in ties:
                    sub(notation, 'tied', type=tie)
            cursor += length

    for index in range(count):
        measure = sub(part, 'measure', number=index + 1)
        if index == 0:
            attributes = sub(measure, 'attributes')
            sub(attributes, 'divisions', 4)
            sub(sub(attributes, 'key'), 'fifths', 0)
            time = sub(attributes, 'time')
            sub(time, 'beats', beats)
            sub(time, 'beat-type', beat_type)
            clef = sub(attributes, 'clef')
            sub(clef, 'sign', 'G')
            sub(clef, 'line', 2)
            direction = sub(measure, 'direction', placement='above')
            sub(sub(direction, 'direction-type'), 'words',
                'Draft / 1/16 grid')
            sub(direction, 'sound', tempo=bpm)
        left, right = index * measure_units, (index + 1) * measure_units
        for voice_id, voice in enumerate(voices, 1):
            if voice_id > 1:
                sub(sub(measure, 'backup'), 'duration', measure_units)
            cursor = left
            for start, end, pitch in voice:
                if end <= left or start >= right:
                    continue
                a, b = max(left, start), min(right, end)
                if a > cursor:
                    segment(measure, cursor, a, None, voice_id)
                segment(measure, a, b, pitch, voice_id, start, end)
                cursor = b
            if cursor < right:
                segment(measure, cursor, right, None, voice_id)
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
