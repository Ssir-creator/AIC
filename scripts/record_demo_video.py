"""Captioned, real browser operations. Requires Playwright, Chromium, server.

Edits demonstrate controls, not verified corrections or musician user feedback.
"""
import argparse,base64,json,time,os
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(root/'.cache/playwright'))
parser=argparse.ArgumentParser();parser.add_argument('--base-url',default='http://127.0.0.1:8000')
parser.add_argument('--output',type=Path,default=root/'artifacts/video-review')
args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
clip=root/'artifacts/pipa-diagnostic-20261011/00/first-30s.wav'
reference=root/'artifacts/春雨开头-旋律提纲待确认/旋律提纲-非正式参考.mid'
if not clip.is_file() or not reference.is_file():raise SystemExit('Private input or provisional outline missing')
log={'status':'running','video_type':'real automated browser operation, captioned review draft',
     'edits':'control demonstration only, not verified musical corrections',
     'reference':'unverified score outline, NOT ground truth','audio_events':[],'chapters':[]}
errors=[]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 context=browser.new_context(viewport={'width':1280,'height':800},record_video_dir=str(out/'raw'),
                             record_video_size={'width':1280,'height':800},accept_downloads=True)
 page=context.new_page();video=page.video;started=time.monotonic()
 page.on('pageerror',lambda e:errors.append(str(e)))
 def elapsed():return time.monotonic()-started
 def hold(until):
  while elapsed()<until:page.wait_for_timeout(min(500,(until-elapsed())*1000))
 def caption(title,text,full=False):
  page.evaluate('''({title,text,full})=>{
   document.querySelector('#recording-caption')?.remove();
   const box=document.createElement('div');box.id='recording-caption';
   Object.assign(box.style,{position:'fixed',zIndex:'99999',left:full?'0':'24px',right:full?'0':'24px',
    top:full?'0':'auto',bottom:full?'0':'18px',background:full?'#f4f5ef':'rgba(37,57,45,.96)',
    color:full?'#25392d':'#fff',padding:full?'100px 100px':'15px 22px',borderRadius:full?'0':'12px',
    display:'flex',flexDirection:'column',justifyContent:full?'center':'flex-start',pointerEvents:'none',
    fontFamily:'"Noto Sans CJK SC",sans-serif'});
   const h=document.createElement('strong');h.textContent=title;h.style.fontSize=full?'42px':'22px';
   const body=document.createElement('div');body.textContent=text;body.style.cssText=`font-size:${full?25:17}px;line-height:1.8;white-space:pre-line;margin-top:${full?28:5}px`;
   box.append(h,body);document.body.append(box);
  }''',{'title':title,'text':text,'full':full})
  log['chapters'].append({'seconds':round(elapsed(),2),'title':title,'text':text})
  (out/'recording-log.json').write_text(json.dumps(log,indent=2,ensure_ascii=False))
  print(f'{elapsed():.1f}s / {title}',flush=True)
 def focus(selector):page.locator(selector).scroll_into_view_if_needed();page.wait_for_timeout(300)
 try:
  page.goto(args.base_url);page.evaluate('document.body.style.zoom="0.85"')
  caption('谱易改 / 琵琶短录音转谱与纠谱','2026 AIC / AI+软件创新\n音频识别 → 听原音校对 → 参考旋律定位 → 乐谱草稿\n字幕版操作审核视频 / 非提交定稿',True);hold(15)
  caption('真实输入，明确贡献','案例：参赛者本人演奏录制《春雨》前30秒。\n基础识别：Spotify Basic Pitch 0.4.0 / ONNX CPU，未训练。\n本视频由自动化操作录制；修改仅展示功能，不作为音乐纠错效果。',True);hold(30)
  caption('01 / 上传录音，生成音符初稿','单段最长60秒、20MB。当前使用真实琵琶录音；识别输出不等于正确答案。')
  focus('#upload-form');page.locator('#file').set_input_files(str(clip));page.locator('#upload-button').click()
  page.wait_for_selector('#workspace:not([hidden])',timeout=90000)
  assert page.locator('#note-count').inner_text()=='77'
  hold(45)
  caption('02 / 音符时间轴与原音定位','灰色轮廓保留模型初稿，实心色块是当前结果。点击音符可定位原音。')
  focus('.timeline-card');page.locator('#notes-body tr.selectable').first.click();focus('.timeline-card')
  page.evaluate('document.querySelector("#original-audio").currentTime=1.3')
  audio_start=elapsed();page.locator('#original-audio').evaluate('(a)=>a.play()')
  log['audio_events'].append({'video_seconds':audio_start,'source_seconds':1.3,'duration':9.2,
                              'source':str(clip),'note':'original excerpt added during video encoding'})
  page.wait_for_timeout(9200);page.locator('#original-audio').evaluate('(a)=>a.pause()');hold(65)
  caption('原音与提示分开判断','短音、弱音提示是试听优先规则，不是模型置信度。\n视频音轨中的原音片段在后期加入，不是自动录屏捕获。');hold(80)
  caption('03 / 修改与撤销：操作演示','下面演示编辑音高后撤销。参考尚未确认，不将这次修改宣称为正确修复。')
  focus('.edit-card');before=page.locator('#pitch').input_value();page.locator('#pitch').fill(str(int(before)+1))
  page.locator('#save-note').click();page.wait_for_function("document.querySelector('#revision').textContent==='v1'");hold(91)
  page.locator('#undo').click();page.wait_for_function("document.querySelector('#revision').textContent==='v2'");hold(105)
  caption('补音与删除同样留痕','演示新增一个音符再删除。原始模型音符始终保留，演示操作不作为实际纠错成果。')
  page.locator('#add-note').click();page.locator('#pitch').fill('60');page.locator('#start').fill('0.2');page.locator('#end').fill('0.4')
  page.locator('#save-note').click();page.wait_for_function("document.querySelector('#revision').textContent==='v3'");hold(115)
  page.locator('#delete-note').click();page.wait_for_function("document.querySelector('#revision').textContent==='v4'");hold(125)
  caption('04 / 导入参考，定位旋律','《春雨》开头8音提纲来自谱面数字；八度和节奏待确认，不作为正式真值。')
  focus('.practice-card');page.locator('#reference-file').set_input_files(str(reference));page.locator('#reference-upload').click()
  page.wait_for_selector('#reference-workspace:not([hidden])');hold(140)
  page.locator('#auto-align-reference').click();page.wait_for_function("document.querySelector('#auto-alignment-note').textContent.includes('8/8')")
  caption('局部速度变化 / 自动定位线索','自动定位约1.52—10.04秒，参考只覆盖开头片段。\n位置来自模型初稿，所以起音和时长显示“未评定”。')
  focus('#reference-workspace');hold(160)
  caption('候选八度差异：先定位，后判断','本例出现D5与D4差异。可能来自参考、技法或识别，不能据此认定演奏错音。')
  page.locator('#practice-body button').first.click();focus('.timeline-card');hold(180)
  caption('05 / 导出乐谱草稿与校对记录','MIDI保留秒级音符。MusicXML按用户设置整理小节，仍需确认原曲节奏与技法。')
  focus('.score-export');page.locator('#score-bpm').fill('60');page.locator('#score-meter').select_option('3/4')
  with page.expect_download() as d:page.locator('#export-score').click()
  d.value.save_as(str(out/'operation-demo.musicxml'))
  with page.expect_download() as d:page.locator('#export-report').click()
  d.value.save_as(str(out/'operation-demo-record.json'))
  report=json.loads((out/'operation-demo-record.json').read_text())
  assert report['notes']==report['original_notes'],'Demonstration edits were not completely undone'
  assert len(report['history'])==4
  hold(200)
  caption('功能验证与实际效果分开','51项测试通过，三段真实琵琶前30秒均跑通。\n吉他固定诊断F1：起音/音高0.7975，加入结束0.5660。\n吉他训练重叠未核实；没有独立琵琶标注，不报告琵琶准确率。',True);hold(220)
  caption('当前边界与下一步','不自动识别简谱图片；八度、技法、自由节奏及MuseScore实际使用仍需验证。\n下一步：独立核对参考，再做真实使用者同任务对比。\n不虚构用户、专利、软著或模型精度提升。',True);hold(237)
  caption('谱易改 / 审核版本','核心价值：连接原音校对、参考定位与后续制谱。\n基础模型与数据保留署名；开发使用AI辅助。\n本视频为研发审核稿，尚未作为参赛材料提交。',True);hold(242)
  log.update(status='completed',duration_seconds=elapsed(),js_errors=errors)
  assert not errors,errors
 finally:
  context.close();video.save_as(str(out/'browser-recording.webm'));browser.close()
  (out/'recording-log.json').write_text(json.dumps(log,indent=2,ensure_ascii=False))
print('Recording complete',flush=True)
