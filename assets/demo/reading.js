'use strict';
(() => {
  const video = document.querySelector('video');
  const toggle = document.getElementById('reading-toggle');
  const select = document.getElementById('reading-voice');
  const status = document.getElementById('reading-status');
  const synth = window.speechSynthesis;
  let voices = [], cues = [], lastCue = -1, currentUtterance = null;

  function stop() {
    if (synth) synth.cancel();
    currentUtterance = null;
    lastCue = -1;
  }
  function disable(message) {
    toggle.checked = false;
    toggle.disabled = true;
    select.disabled = true;
    select.replaceChildren(new Option('无可用中文音色', ''));
    status.textContent = message;
    stop();
  }
  function updateVoices() {
    const previous = select.value;
    voices = synth.getVoices().filter(v => /^(zh|cmn)([-_]|$)/i.test(v.lang));
    voices.sort((a,b) => Number(/^zh[-_]CN$/i.test(b.lang))-Number(/^zh[-_]CN$/i.test(a.lang)));
    if (!voices.length) {
      disable('当前浏览器未提供中文音色。请观看中文字幕；也可以在支持中文语音的浏览器中打开。');
      return;
    }
    select.replaceChildren(...voices.map((voice,index) => new Option(voice.name + ' · ' + voice.lang, String(index))));
    if (voices[Number(previous)]) select.value = previous;
    select.disabled = false;
    toggle.disabled = !cues.length;
    status.textContent = cues.length
      ? '已找到中文音色。勾选“随视频朗读字幕”，再播放视频。音质取决于所选浏览器音色。'
      : '已找到中文音色，正在读取字幕。';
  }
  function readCurrentCue() {
    if (!toggle.checked || video.paused || video.ended || video.seeking || !voices.length) return;
    if (synth.speaking || synth.pending) return;
    const index = cues.findIndex(cue => video.currentTime >= cue.start && video.currentTime < cue.end);
    if (index < 0 || index === lastCue) return;
    const cue = cues[index];
    const voice = voices[Number(select.value)] || voices[0];
    if (!voice) return;
    lastCue = index;
    const utterance = new SpeechSynthesisUtterance(cue.text);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = Math.max(.85, Math.min(1.5, video.playbackRate * Math.max(.9, cue.text.length / ((cue.end-cue.start)*4.2))));
    utterance.volume = 1;
    utterance.onend = () => { if (currentUtterance === utterance) currentUtterance = null; };
    utterance.onerror = event => {
      if (['canceled','interrupted'].includes(event.error)) return;
      toggle.checked = false;
      status.textContent = '该音色朗读未成功。可选择其他中文音色，或继续观看字幕。';
      stop();
    };
    currentUtterance = utterance;
    synth.speak(utterance);
  }
  if (!synth || typeof window.SpeechSynthesisUtterance === 'undefined') {
    disable('当前浏览器不支持中文朗读。视频已保留完整中文字幕。');
    return;
  }
  synth.addEventListener('voiceschanged', updateVoices);
  toggle.addEventListener('change', () => {
    stop();
    status.textContent = toggle.checked ? '已开启浏览器中文朗读，暂停视频时朗读也会停止。' : '中文朗读已关闭，视频按字幕版播放。';
    readCurrentCue();
  });
  select.addEventListener('change', () => { stop(); readCurrentCue(); });
  video.addEventListener('timeupdate', readCurrentCue);
  video.addEventListener('play', readCurrentCue);
  video.addEventListener('pause', stop);
  video.addEventListener('seeking', stop);
  video.addEventListener('seeked', readCurrentCue);
  video.addEventListener('ended', stop);
  video.addEventListener('ratechange', () => { stop(); readCurrentCue(); });
  window.addEventListener('pagehide', stop);
  fetch('reading-cues.json', {cache:'no-store'})
    .then(response => { if (!response.ok) throw Error('captions unavailable'); return response.json(); })
    .then(value => {
      if (!Array.isArray(value) || !value.length || !value.every(cue => Number.isFinite(cue.start) && Number.isFinite(cue.end) && cue.end > cue.start && typeof cue.text === 'string')) throw Error('invalid captions');
      cues = value;
      updateVoices();
    })
    .catch(() => disable('朗读字幕暂时无法读取。视频中的中文字幕仍可正常观看。'));
  updateVoices();
})();
