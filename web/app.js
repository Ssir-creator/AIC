"use strict";
const $ = id => document.getElementById(id);
let project = null, selected = null, undoStack = [], audioContext, voices = [], editing = false;
const noteName = pitch => ["C","C♯","D","D♯","E","F","F♯","G","G♯","A","A♯","B"][pitch % 12] + (Math.floor(pitch / 12) - 1);
function status(message, type = "") { $("status").textContent = message; $("status").className = type; }
async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try { const body = await response.json(); message = typeof body.detail === "string" ? body.detail : "数据不符合要求，请检查音高和起止时间"; } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}
function cell(row, content) { const td = document.createElement("td"); td.textContent = content; row.appendChild(td); return td; }
function render() {
  $("workspace").hidden = false;
  $("project-title").textContent = project.filename;
  invalidatePreview();
  $("duration").textContent = project.duration.toFixed(1) + "s";
  $("note-count").textContent = project.notes.length;
  $("review-count").textContent = project.notes.filter(n => n.review_reasons.length).length;
  $("revision").textContent = "v" + project.revision;
  for (const id of ['start','end','loop-start','loop-end','score-origin']) $(id).max=project.duration;
  const base = `/api/projects/${project.id}`;
  $("export-midi").href = base + "/midi"; $("original-midi").href = base + "/midi?original=true";
  $("export-report").href = base + "/report";
  if (!$("original-audio").src.endsWith(base + "/audio")) $("original-audio").src = base + "/audio";
  $("model-time").textContent = `本次模型推理用时 ${project.inference_seconds}s（不含音频解码与传输）。建议检查来自短音符/弱音符规则，不是模型置信度。`;
  $("notes-body").replaceChildren();
  const shown = project.notes.filter(n => !$("only-review").checked || n.review_reasons.length);
  for (const n of shown) {
    const tr = document.createElement("tr"); tr.className = "selectable" + (n.id === selected ? " selected" : "");
    tr.tabIndex = 0; tr.setAttribute("aria-label", `选择${noteName(n.pitch)}，开始${n.start.toFixed(2)}秒`);
    cell(tr, noteName(n.pitch)); cell(tr, n.start.toFixed(3)); cell(tr, (n.end - n.start).toFixed(3));
    const last = cell(tr, n.review_reasons.length ? "建议检查" : "—");
    if (n.review_reasons.length) { last.className = "badge"; last.title = n.review_reasons.join("；"); }
    tr.onclick = () => selectNote(n.id); tr.onkeydown = e => { if (e.key === "Enter") selectNote(n.id); };
    $("notes-body").appendChild(tr);
  }
  if (!shown.length) { const tr = document.createElement("tr"); const td = cell(tr, project.notes.length ? "当前筛选下无音符" : "未识别到音符，可以补音符或换更清晰的录音"); td.colSpan = 4; $("notes-body").appendChild(tr); }
  drawTimeline();
  renderPractice();
  $("undo").disabled = !undoStack.length || editing;
  $("delete-note").disabled = !selected || editing;
  $("listen-note").disabled = !selected;
  $("previous-note").disabled = !project.notes.length;
  $("next-note").disabled = !project.notes.length;
}
function svgElement(type, attrs, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", type);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text) node.textContent = text;
  $("timeline").appendChild(node); return node;
}
function drawTimeline() {
  const svg = $("timeline"); svg.replaceChildren();
  const width = timelineWidth(), height = 260, left = 42;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`); svg.style.width = width + "px";
  const pitches = [...project.notes,...($("show-original").checked ? project.original_notes : []),...($("show-reference").checked ? project.practice?.expected_notes || [] : [])].map(n => n.pitch);
  const low = Math.max(21, (pitches.length ? Math.min(...pitches) : 55) - 2);
  const high = Math.min(108, (pitches.length ? Math.max(...pitches) : 75) + 2);
  const row = 218 / (high - low + 1), x = t => left + t / project.duration * (width - left - 12);
  for (let p = low; p <= high; p++) {
    const y = 10 + (high - p) * row;
    svgElement("rect", {x:left, y, width:width-left, height:row, fill:[1,3,6,8,10].includes(p%12) ? "#edf0e8" : "#f8faf5"});
    if (row > 8) svgElement("text", {x:4, y:y+row*.8, fill:"#7d8c7b", "font-size":Math.min(10,row*.8)}, noteName(p));
  }
  const step = project.duration > 20 ? 5 : 1;
  for (let t = 0; t <= project.duration; t += step) {
    svgElement("line", {x1:x(t), x2:x(t), y1:10, y2:230, stroke:"#d7dfd0", "stroke-width":1});
    svgElement("text", {x:x(t)+2, y:250, fill:"#7d8c7b", "font-size":11}, t+"s");
  }
  if ($("show-original").checked) for (const n of project.original_notes) {
    svgElement("rect", {x:x(n.start), y:10+(high-n.pitch)*row, width:Math.max(3,x(n.end)-x(n.start)), height:Math.max(3,row), rx:2,
      fill:"none",stroke:"#96a38e","stroke-width":1.5,"pointer-events":"none"});
  }
  if ($("show-reference").checked) for (const n of project.practice?.expected_notes || []) {
    svgElement("rect", {x:x(n.start), y:10+(high-n.pitch)*row, width:Math.max(3,x(n.end)-x(n.start)), height:Math.max(3,row), rx:2,
      fill:"none",stroke:"#8872ae","stroke-width":2,"stroke-dasharray":"4 2","pointer-events":"none"});
  }
  for (const n of project.notes) {
    const rect = svgElement("rect", {x:x(n.start), y:10+(high-n.pitch)*row+1, width:Math.max(3,x(n.end)-x(n.start)), height:Math.max(3,row-2), rx:2,
      fill:n.id===selected?"#1c3926":n.review_reasons.length?"#c89143":"#809b70", tabindex:0, role:"button", "aria-label":`${noteName(n.pitch)} ${n.start.toFixed(2)}秒`});
    rect.style.cursor = "pointer"; rect.onclick = () => selectNote(n.id);
    rect.onkeydown = e => { if (e.key === "Enter") selectNote(n.id); };
  }
  svgElement("line", {id:"playhead",x1:x($("original-audio").currentTime||0),x2:x($("original-audio").currentTime||0),y1:10,y2:230,stroke:"#bd4f35","stroke-width":2,"pointer-events":"none"});
}
function selectNote(id) {
  selected = id; const n = project.notes.find(n => n.id === id); if (!n) return;
  excerptEnd = null;
  $("pitch").value = n.pitch; $("start").value = n.start; $("end").value = n.end; $("velocity").value = n.velocity;
  $("pitch-choice").value = n.pitch; $("pitch-name").textContent = noteName(n.pitch); $("save-note").textContent = "保存修改";
  $("selection-hint").textContent = n.review_reasons.join("；") || "对照原音确认音高与起止时间。";
  const original = project.original_notes.find(note => note.id === id);
  $("original-note-hint").textContent = original ? `模型初稿：${noteName(original.pitch)} / ${original.start.toFixed(3)}—${original.end.toFixed(3)}秒` : "这是人工补充的音符，模型初稿中没有此音符。";
  $("original-audio").currentTime = n.start; render();
}
function cleanNotes(notes) { return notes.map(({id,pitch,start,end,velocity}) => ({id,pitch,start,end,velocity})); }
async function saveNotes(notes, remember = true) {
  if (editing || $("upload-button").disabled) return false;
  editing = true;
  const before = cleanNotes(project.notes), revision = project.revision;
  $("save-note").disabled = true; $("add-note").disabled = true; render();
  try {
    project = await request(`/api/projects/${project.id}/notes`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({revision, notes:cleanNotes(notes)})});
    if (remember && project.revision !== revision) undoStack.push(before);
    if (!project.notes.some(n => n.id === selected)) selected = null;
    status("已保存。MIDI和校对记录已更新。"); refreshProjects(); return true;
  } catch (e) { status(e.message, "error"); return false; }
  finally { editing = false; $("save-note").disabled = false; $("add-note").disabled = false; render(); }
}
$("file").onchange = () => { $("filename").textContent = $("file").files[0]?.name || "未选择文件"; };
$("upload-form").onsubmit = async e => {
  e.preventDefault(); const file = $("file").files[0]; if (!file) return;
  if (file.size > 20*1024*1024) { status("文件超过20MB，请选短录音", "error"); return; }
  const data = new FormData(); data.append("file", file);
  $("upload-button").disabled = true; status("正在解码并识别，请稍候。首次启动可能需要更长时间…", "busy");
  try {
    const next = await request("/api/transcribe", {method:"POST", body:data});
    stopSynth(); stopLoop(); $("original-audio").pause(); project = next; selected = null; undoStack = [];
    localStorage.setItem("pu-yigai-project", project.id); setTab("notes"); render(); refreshProjects();
    status(`初稿生成：${project.notes.length}个音符。请试听原音并检查结果。`);
  } catch (err) { status(err.message, "error"); }
  finally { $("upload-button").disabled = false; }
};
$("only-review").onchange = render;
$("show-original").onchange = render;
$("show-reference").onchange = render;
function navigateNote(direction) {
  if (!project) return;
  const notes = project.notes.filter(n => !$("only-review").checked || n.review_reasons.length);
  if (!notes.length) return;
  const index = notes.findIndex(n => n.id === selected);
  const next = index < 0 ? (direction > 0 ? 0 : notes.length-1) : (index+direction+notes.length)%notes.length;
  selectNote(notes[next].id);
}
$("previous-note").onclick = () => navigateNote(-1);
$("next-note").onclick = () => navigateNote(1);
$("pitch").oninput = () => { $("pitch-name").textContent = noteName(Number($("pitch").value)); $("pitch-choice").value = $("pitch").value; };
$("edit-form").onsubmit = async e => {
  e.preventDefault(); if (!project) return;
  const n = {id:selected || crypto.randomUUID().replaceAll("-", "").slice(0,12), pitch:Number($("pitch").value), start:Number($("start").value), end:Number($("end").value), velocity:Number($("velocity").value)};
  if(n.end<=n.start){status('结束时间必须晚于开始时间，请调整后保存。','error');return;}
  const notes = cleanNotes(project.notes).filter(x => x.id !== n.id); notes.push(n);
  if (await saveNotes(notes)) selectNote(n.id);
};
$("add-note").onclick = () => {
  selected = null; $("save-note").textContent = "保存新音符"; $("selection-hint").textContent = "输入漏掉的音符，保存后加入当前结果。";
  $("original-note-hint").textContent = "人工补充音符；保存后会记录为新增。";
  const start = Math.min($("original-audio").currentTime || 0, Math.max(0,project.duration-0.2));
  $("start").value = start.toFixed(3); $("end").value = Math.min(project.duration,start+.3).toFixed(3); render();
};
$("delete-note").onclick = async () => { if (selected) await saveNotes(project.notes.filter(n => n.id !== selected)); };
$("undo").onclick = async () => { if (!undoStack.length || editing) return; const previous = undoStack.at(-1); if (await saveNotes(previous, false)) { undoStack.pop(); render(); } };
let excerptEnd = null;
$("listen-note").onclick = async () => {
  const n = project.notes.find(n => n.id === selected); if (!n) return;
  stopSynth(); stopLoop(); const audio = $("original-audio"); audio.currentTime = Math.max(0,n.start-.15); excerptEnd = Math.min(project.duration,n.end+.2);
  try { await audio.play(); } catch (e) { status("原音播放失败，请重试", "error"); }
};
$("original-audio").addEventListener("timeupdate", () => {
  if (project && $("playhead")) {
    const width = timelineWidth(),x=42+$("original-audio").currentTime/project.duration*(width-54);
    $("playhead").setAttribute("x1",x);$("playhead").setAttribute("x2",x);
  }
  if (excerptEnd !== null && $("original-audio").currentTime >= excerptEnd) { $("original-audio").pause(); excerptEnd = null; }
});
$("original-audio").addEventListener("seeked", () => { /* seeking retains the currently requested excerpt */ });
function stopSynth() { for (const oscillator of voices) { try { oscillator.stop(); } catch (_) {} } voices = []; }
$("stop-synth").onclick = stopSynth;
$("play-synth").onclick = async () => {
  if (!project) return; stopSynth(); stopLoop(); $("original-audio").pause(); excerptEnd = null;
  audioContext ||= new (window.AudioContext || window.webkitAudioContext)(); await audioContext.resume();
  const origin = audioContext.currentTime + .1;
  const gainScale = .2 / Math.sqrt(Math.max(1, project.notes.length));
  for (const n of project.notes) {
    const oscillator = audioContext.createOscillator(), gain = audioContext.createGain();
    oscillator.type = "triangle"; oscillator.frequency.value = 440 * 2 ** ((n.pitch - 69) / 12);
    const start = origin+n.start, end = origin+n.end, amplitude = n.velocity/127*gainScale;
    gain.gain.setValueAtTime(0,start); gain.gain.linearRampToValueAtTime(amplitude,start+Math.min(.015,(end-start)/3)); gain.gain.exponentialRampToValueAtTime(.0001,end);
    oscillator.connect(gain); gain.connect(audioContext.destination); oscillator.start(start); oscillator.stop(end+.02); voices.push(oscillator);
  }
};
$("delete-project").onclick = async () => {
  if (!project || !confirm("删除本项目的录音和校对记录？请先导出需要保留的文件。")) return;
  try { await request(`/api/projects/${project.id}`, {method:"DELETE"}); stopSynth(); stopLoop(); $("original-audio").pause(); refreshProjects(); localStorage.removeItem("pu-yigai-project"); project = null; selected = null; $("workspace").hidden = true; status("项目已删除。"); } catch (e) { status(e.message,"error"); }
};
(async () => {
  const id = localStorage.getItem("pu-yigai-project"); if (!id) return;
  try { project = await request(`/api/projects/${encodeURIComponent(id)}`); render(); status("已恢复上次项目，可以继续校对。"); }
  catch (_) { localStorage.removeItem("pu-yigai-project"); }
})();

async function downloadScore(original) {
  if (!project) return;
  const fields = [$("score-bpm"), $("score-origin")];
  if (!fields.every(field => field.value !== "" && field.reportValidity())) return;
  const params = new URLSearchParams({bpm:$("score-bpm").value,meter:$("score-meter").value,origin:$("score-origin").value,original});
  try {
    const response = await fetch(`/api/projects/${project.id}/musicxml?${params}`);
    if (!response.ok) { const body = await response.json(); throw new Error(typeof body.detail === "string" ? body.detail : "请检查速度、拍号和起拍位置"); }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a"); link.href=url; link.download=original?"model-draft.musicxml":"reviewed-draft.musicxml";
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
    status("乐谱草稿已导出。请在 MuseScore 中确认节奏、声部与排版。");
  } catch (error) { status(error.message,"error"); }
}
$("export-score").onclick = () => downloadScore(false);
$("export-original-score").onclick = () => downloadScore(true);

function renderPractice() {
  const reference = project.reference, comparison = project.practice;
  $("reference-workspace").hidden = !reference;
  if (!reference || !comparison) return;
  $("reference-name").textContent = `参考曲谱：${reference.filename} / ${reference.notes.length}个音符${reference.status === "unverified_score_outline" ? " / 草稿待确认：八度与节奏未核实" : ""}`;
  const settings=reference.settings;
  for (const [id,key] of [["reference-scale","scale"],["reference-shift","shift"],["reference-window","window"],["reference-timing","timing_tolerance"],["reference-duration","duration_tolerance"]]) $(id).value=settings[key];
  const automatic=comparison.automatic_alignment;
  $("auto-alignment-note").textContent=automatic ? `自动定位了 ${automatic.matched_reference_notes}/${automatic.total_reference_notes} 个参考音，范围 ${automatic.scope_start.toFixed(2)}—${automatic.scope_end.toFixed(2)}秒。${automatic.ambiguous_occurrence ? "发现相似重复段落，需检查位置。" : ""}位置来自模型初稿，不是独立标注；此模式不评定起音和时长。手动更新对齐后可退出此模式。` : "可尝试自动找到少量单旋律音符的位置；双弦、多声部或对齐不准时用手动方式。";
  const counts=comparison.counts;
  $("practice-summary").textContent = `音高差异 ${counts.pitch} · 起音差异 ${counts.timing ?? "未评定"} · 时长差异 ${counts.duration ?? "未评定"} · 参考有当前无 ${counts.missing} · 当前有参考无 ${counts.extra}`;
  $("practice-excluded").textContent = `已配对 ${comparison.matched_pairs} 对；${comparison.excluded_reference_notes} 个参考音符超出对齐后的录音范围，未参与比较。录音另有 ${comparison.uncompared_recording_notes || 0} 个音符未在当前范围比较。以下为待确认差异，不是演奏成绩。`;
  $("practice-body").replaceChildren();
  const labels={pitch:"音高差异",timing:"起音差异",duration:"时长差异",missing:"参考有、当前无",extra:"当前有、参考无"};
  for (const issue of comparison.issues) {
    const tr=document.createElement("tr");
    cell(tr,labels[issue.kind]);cell(tr,issue.time.toFixed(3)+"s");
    const format=n=>n?`${noteName(n.pitch)} / ${n.start.toFixed(3)}—${n.end.toFixed(3)}s`:"无";
    cell(tr,`参考 ${format(issue.reference)}；当前 ${format(issue.actual)}`);
    const action=cell(tr,"");const button=document.createElement("button");button.type="button";button.className="secondary";button.textContent="定位原音";
    button.onclick=()=> {
      if (issue.note_id) selectNote(issue.note_id);
      else { selected=null; render(); $("selection-hint").textContent="参考位置未找到当前音符，请先听原音确认是否演奏或识别遗漏。"; }
      $("original-audio").currentTime=Math.max(0,issue.time-.15);
      excerptEnd=null;
      $("original-audio").scrollIntoView({behavior:"smooth",block:"center"});
      status("已定位差异位置，请播放原音确认，再决定是否修改音符初稿。");
    };
    action.appendChild(button);$("practice-body").appendChild(tr);
  }
  if (!comparison.issues.length) { const tr=document.createElement("tr");cell(tr,"当前对齐与容差下没有差异，仍需听音确认；不代表演奏完全正确。").colSpan=4;$("practice-body").appendChild(tr); }
}
$("reference-form").onsubmit=async event=> {
  event.preventDefault();if (!project) return;
  const file=$("reference-file").files[0];if (!file) return;
  if(file.size>1024*1024) {status("参考MIDI超过1MB，请导出练习短片段","error");return;}
  const body=new FormData();body.append("file",file);$("reference-upload").disabled=true;
  try { project=await request(`/api/projects/${project.id}/reference`,{method:"POST",body});render();status("参考曲谱已导入。请先对齐时间，再检查差异。"); }
  catch(error){status(error.message,"error");}
  finally{$("reference-upload").disabled=false;}
};
$("alignment-form").onsubmit=async event=> {
  event.preventDefault();if (!project) return;
  const settings={scale:Number($("reference-scale").value),shift:Number($("reference-shift").value),window:Number($("reference-window").value),timing_tolerance:Number($("reference-timing").value),duration_tolerance:Number($("reference-duration").value)};
  try { project=await request(`/api/projects/${project.id}/reference/alignment`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(settings)});render();status("参考对齐已更新；请对照录音核对提示。"); }
  catch(error){status(error.message,"error");}
};
$("remove-reference").onclick=async()=> {
  if (!project) return;
  try { project=await request(`/api/projects/${project.id}/reference`,{method:"DELETE"});render();status("已移除参考曲谱，仍可继续校对音符。"); }
  catch(error){status(error.message,"error");}
};

$("align-first-note").onclick=()=> {
  if (!project?.reference) return;
  const scale=Number($("reference-scale").value);
  const first=project.reference.notes[0].start;
  $("reference-shift").value=($("original-audio").currentTime-first*scale).toFixed(4);
  $("alignment-form").requestSubmit();
};

$("auto-align-reference").onclick=async()=> {
  if (!project) return;
  $("auto-align-reference").disabled=true;status("正在查找参考旋律对应的录音位置…");
  try { project=await request(`/api/projects/${project.id}/reference/auto-align`,{method:"POST"});render();status("已生成自动定位线索。请听原音确认；起音与时长暂不评定。"); }
  catch(error){status(error.message,"error");}
  finally{$("auto-align-reference").disabled=false;}
};

(async()=> {
  try {
    const response=await fetch("/api/practice-demo");if(!response.ok)return;
    const demo=await response.json();$("load-practice-demo").hidden=false;
    $("load-practice-demo").onclick=async()=> {
      try {
        stopSynth();stopLoop();$("original-audio").pause();
        project=await request("/api/practice-demo");selected=null;undoStack=[];
        localStorage.setItem("pu-yigai-project",project.id);setTab("notes");render();
        status("已打开你的春雨录音试用案例。参考仍为待确认草稿，差异只是线索。");
        $("workspace").scrollIntoView({behavior:"smooth",block:"start"});
      }catch(error){status(error.message,"error");}
    };
  }catch(_) {}
})();


// Workspace navigation, playback controls, and a real MusicXML renderer.
let looping = false, previewKey = null, previewPendingKey = null, previewToken = 0;
function setTab(name) {
  document.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.tab === name)));
  document.querySelectorAll('[data-panel]').forEach(p => p.hidden = p.dataset.panel !== name);
}
document.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => setTab(b.dataset.tab));
function timelineWidth() { return Math.max(820, project.duration * 45) * Number($('timeline-zoom').value); }
$('timeline-zoom').oninput = () => { $('zoom-value').textContent = $('timeline-zoom').value + '×'; if(project)drawTimeline(); };
for (let p=21;p<=108;p++) $('pitch-choice').add(new Option(noteName(p) + (p===60?' · 中央C':''),p));
$('pitch-choice').value='60';
$('pitch-choice').onchange=()=>{$('pitch').value=$('pitch-choice').value;$('pitch').dispatchEvent(new Event('input'));};
$('playback-rate').onchange=()=>{const a=$('original-audio');a.preservesPitch=true;a.playbackRate=Number($('playback-rate').value);};
function stopLoop(){looping=false;$('toggle-loop').textContent='开始循环';$('toggle-loop').setAttribute('aria-pressed','false');}
function loopRange(){const a=Number($('loop-start').value),b=Number($('loop-end').value);if(!project||$('loop-start').value===''||$('loop-end').value===''||!Number.isFinite(a)||!Number.isFinite(b)||a<0||b<=a||b>project.duration)throw Error('循环结束须晚于开始，且不能超出录音长度。');return [a,b];}
$('loop-selected').onclick=()=>{const n=project?.notes.find(n=>n.id===selected);if(!n){status('请先选中一个音符，再设置循环。');return;}$('loop-start').value=Math.max(0,n.start-.15).toFixed(3);$('loop-end').value=Math.min(project.duration,n.end+.2).toFixed(3);};
$('toggle-loop').onclick=async()=>{if(looping){stopLoop();$('original-audio').pause();return;}try{const [a,b]=loopRange();stopSynth();excerptEnd=null;looping=true;$('original-audio').currentTime=a;await $('original-audio').play();$('toggle-loop').textContent='停止循环';$('toggle-loop').setAttribute('aria-pressed','true');status('循环试听已开始；可慢放核对原音。');$('loop-hint').textContent=`循环 ${a.toFixed(2)}—${b.toFixed(2)} 秒。暂停原音即可暂停；修改范围后需重新开始。`;}catch(e){stopLoop();status(e.message,'error');}};
for(const id of ['loop-start','loop-end'])$(id).oninput=stopLoop;
$('original-audio').addEventListener('timeupdate',()=>{if(looping&&!$('original-audio').paused){const [a,b]=loopRange();if($('original-audio').currentTime>=b)$('original-audio').currentTime=a;}});
$('original-audio').addEventListener('ended',()=>{if(looping){$('original-audio').currentTime=Number($('loop-start').value);$('original-audio').play().catch(()=>stopLoop());}});
function scoreKey(){return project ? [project.id,project.revision,$('score-bpm').value,$('score-meter').value,$('score-origin').value,$('score-source').value].join(':') : null;}
function invalidatePreview(){const previous=previewKey||previewPendingKey;if(previous && previous!==scoreKey()){previewToken++;previewKey=null;previewPendingKey=null;$('preview-score').disabled=false;$('score-preview').hidden=true;$('score-preview-status').textContent='音符或制谱设置已改变，请重新生成预览。';}}
for(const id of ['score-bpm','score-meter','score-origin','score-source'])$(id).addEventListener('input',invalidatePreview);
$('preview-score').onclick=async()=>{
 if(!project)return;
 if(![$('score-bpm'),$('score-origin')].every(f=>f.value!==''&&f.reportValidity()))return;
 const key=scoreKey(),token=++previewToken;
 previewPendingKey=key;
 $('preview-score').disabled=true;$('score-preview-status').textContent='正在整理小节并生成五线谱草稿…';$('score-preview').hidden=true;
 try{
  const params=new URLSearchParams({bpm:$('score-bpm').value,meter:$('score-meter').value,origin:$('score-origin').value,original:$('score-source').value});
  const response=await fetch(`/api/projects/${project.id}/musicxml?${params}`);
  if(!response.ok){const error=await response.json();throw Error(typeof error.detail==='string'?error.detail:'请检查制谱设置');}
  const xml=await response.text();if(token!==previewToken||key!==scoreKey())return;
  $('score-preview').replaceChildren();$('score-preview').hidden=false;
  const display=new opensheetmusicdisplay.OpenSheetMusicDisplay($('score-preview'),{backend:'svg',autoResize:false,drawTitle:false,drawSubtitle:false,drawComposer:false,drawPartNames:false});
  await display.load(xml);if(token!==previewToken||key!==scoreKey()){$('score-preview').hidden=true;return;}
  display.render();previewKey=key;
  status('五线谱草稿已生成，可对照原音继续校对或导出。');
  $('score-preview-status').textContent=`${$('score-source').value==='true'?'原始模型初稿':'当前校对结果'} / 四分音符 ${$('score-bpm').value} BPM / ${$('score-meter').value} / 起拍 ${$('score-origin').value}s。固定十六分网格的五线谱草稿；技法和原曲节奏仍需确认。`;
 }catch(e){if(token===previewToken){$('score-preview').hidden=true;$('score-preview-status').textContent='预览未生成：'+e.message;}}
 finally{if(token===previewToken){previewPendingKey=null;$('preview-score').disabled=false;}}
};
async function refreshProjects(){
 try{const items=await request('/api/projects');$('project-total').textContent=`（${items.length}）`;$('project-list').replaceChildren();
 for(const item of items){const row=document.createElement('div');row.className='project-row';const text=document.createElement('span');text.textContent=`${item.filename} · ${item.duration.toFixed(1)}s · ${item.note_count}音符 · v${item.revision}`;const b=document.createElement('button');b.className='secondary';b.textContent='继续校对';b.onclick=async()=>{if(editing||$('upload-button').disabled||$('reference-upload').disabled||$('auto-align-reference').disabled){status('当前操作完成后再切换项目。');return;}try{const next=await request(`/api/projects/${item.id}`);stopSynth();stopLoop();$('original-audio').pause();project=next;selected=null;undoStack=[];excerptEnd=null;setTab('notes');localStorage.setItem('pu-yigai-project',project.id);render();status('已打开项目：'+item.filename);$('workspace').scrollIntoView({behavior:'smooth',block:'start'});}catch(e){status(e.message,'error');}};row.append(text,b);$('project-list').append(row);}
 if(!items.length)$('project-list').textContent='还没有项目。上传一段录音，开始第一次校对。';
 }catch{$('project-list').textContent='项目列表暂不可用，可重试刷新；不影响当前项目。';}
}
$('refresh-projects').onclick=refreshProjects;refreshProjects();

$('mark-note-start').onclick=()=>{$('start').value=$('original-audio').currentTime.toFixed(3);};
$('mark-note-end').onclick=()=>{$('end').value=$('original-audio').currentTime.toFixed(3);};

(async()=>{try{const state=await request('/api/health');$('storage-notice').hidden=!state.ephemeral_storage;}catch(_){}})();
