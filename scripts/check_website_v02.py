"""Real pipa input: website controls, preview, project switching and layout."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
out=root/'artifacts/website-v02-real';out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];external=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:external.append(r.url) if r.url.startswith(('https:','http:')) and not r.url.startswith('http://127.0.0.1:8000') else None)
    page.goto('http://127.0.0.1:8000')
    page.locator('#file').set_input_files(str(root/'artifacts/pipa-diagnostic-20261011/00/first-30s.wav'))
    page.locator('#upload-button').click();page.wait_for_selector('#workspace:not([hidden])',timeout=90000)
    pid=page.evaluate('project.id')
    try:
        assert page.locator('#note-count').inner_text()=='77'
        page.locator('#notes-body tr.selectable').first.click()
        page.locator('#pitch-choice').select_option('72');assert page.locator('#pitch').input_value()=='72'
        page.locator('#original-audio').evaluate('(a)=>a.currentTime=1.7')
        page.locator('#mark-note-start').click();assert page.locator('#start').input_value()=='1.700'
        # No save: selecting a control value is not a verified music correction.
        page.locator('#playback-rate').select_option('0.5')
        assert page.locator('#original-audio').evaluate('(a)=>a.playbackRate')==.5
        page.locator('#timeline-zoom').fill('2');page.locator('#timeline-zoom').dispatch_event('input')
        assert page.locator('#timeline').evaluate('(s)=>parseFloat(s.style.width)')==2700
        page.locator('#loop-start').fill('3');page.locator('#loop-end').fill('2');page.locator('#toggle-loop').click()
        assert '循环结束' in page.locator('#status').inner_text()
        page.locator('#loop-selected').click();page.locator('#toggle-loop').click()
        page.wait_for_function("document.querySelector('#toggle-loop').getAttribute('aria-pressed')==='true'")
        assert page.locator('#status').get_attribute('class')!='error'
        a=float(page.locator('#loop-start').input_value());b=float(page.locator('#loop-end').input_value())
        page.locator('#original-audio').evaluate('(a)=>a.currentTime=Number(document.querySelector("#loop-end").value)')
        page.wait_for_function('document.querySelector("#original-audio").currentTime < Number(document.querySelector("#loop-end").value)')
        page.locator('#toggle-loop').click()
        page.locator('[data-tab="score"]').click()
        page.locator('#score-bpm').fill('60');page.locator('#score-meter').select_option('3/4')
        def change_during_request(route):
            page.locator('#score-bpm').fill('70')
            route.continue_()
        page.route('**/musicxml?*',change_during_request,times=1)
        page.locator('#preview-score').click()
        page.wait_for_function("document.querySelector('#score-preview-status').textContent.includes('已改变')")
        assert page.locator('#score-preview').is_hidden()
        page.unroute('**/musicxml?*',change_during_request)
        page.locator('#score-bpm').fill('60')
        page.locator('#preview-score').click();page.wait_for_selector('#score-preview svg',timeout=45000)
        assert '60 BPM' in page.locator('#score-preview-status').inner_text()
        assert page.locator('#status').get_attribute('class')!='error'
        page.locator('.score-export').scroll_into_view_if_needed()
        page.screenshot(path=str(out/'乐谱预览.png'))
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(out/'手机乐谱预览.png'))
        page.set_viewport_size({'width':1440,'height':1000})
        page.locator('#score-source').select_option('true');assert page.locator('#score-preview').is_hidden()
        page.locator('#preview-score').click();page.wait_for_selector('#score-preview svg')
        assert '原始模型初稿' in page.locator('#score-preview-status').inner_text()
        page.locator('.project-library summary').click();page.locator('#refresh-projects').click()
        page.wait_for_function('document.querySelectorAll(".project-row").length>0')
        page.locator('.project-row').filter(has_text='pipa').count() # metadata may use original filename
        page.locator('.project-row button').first.click()
        page.wait_for_function("document.querySelector('[data-tab=notes]').getAttribute('aria-pressed')==='true'")
        assert page.locator('[data-tab="notes"]').get_attribute('aria-pressed')=='true'
        assert not errors,errors
        assert not external,external
        result={'status':'passed','input':'user Spring first30 seconds','model_notes':77,
            'verified':['pitch name selector','playback-position start field','half-speed original audio','2x timeline','invalid loop rejected','selected-note loop and wrap','real MusicXML SVG preview','original/current preview selector','outdated and in-flight preview invalidated','mobile layout','recent project switch'],
            'js_errors':errors,'external_requests':external,
            'interpretation':'functional verification, not musician trial or pipa accuracy'}
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
    finally:
        page.request.delete('http://127.0.0.1:8000/api/projects/'+pid)
        browser.close()
