"""Real input, provisional reference and synthetic judgments: no user study."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1];out=root/'artifacts/website-v03-check';out.mkdir(exist_ok=True)
with sync_playwright() as p:
    b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=b.new_page(viewport={'width':1440,'height':1000});errors=[];ids=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        page.goto('http://127.0.0.1:8000')
        page.locator('#file').set_input_files(str(root/'artifacts/pipa-diagnostic-20261011/00/first-30s.wav'))
        page.locator('#upload-button').click();page.wait_for_selector('#workspace:not([hidden])',timeout=90000)
        ids.append(page.evaluate('project.id'));assert page.locator('#note-count').inner_text()=='77'
        original=page.evaluate('JSON.stringify(project.original_notes)')
        page.locator('[data-tab=reference]').click();page.locator('.numbered-entry summary').click()
        page.locator('#jianpu-text').fill("6 7 2' 2' | 1' 1' 6 5")
        page.locator('#jianpu-submit').click();page.wait_for_selector('#reference-workspace:not([hidden])')
        assert '草稿待确认' in page.locator('#reference-name').inner_text()
        page.locator('#auto-align-reference').click();page.wait_for_function("document.querySelector('#auto-alignment-note').textContent.includes('8/8')")
        form=page.locator('.issue-decision').first
        form.locator('select').select_option('uncertain');form.locator('input').fill('功能验证，不是实际音乐判断')
        form.locator('button').click();page.wait_for_function('Object.keys(project.issue_reviews||{}).length===1')
        assert page.evaluate('JSON.stringify(project.original_notes)')==original
        page.screenshot(path=str(out/'简谱与人工核对.png'),full_page=True)
        with page.expect_download() as d:page.locator('#export-backup').click()
        archive=out/'功能验证项目备份.zip';d.value.save_as(str(archive))
        page.locator('#restore-file').set_input_files(str(archive));page.locator('#restore-project').click()
        page.wait_for_function('project.restored_from!==undefined')
        ids.append(page.evaluate('project.id'));assert ids[0]!=ids[1]
        assert page.evaluate('JSON.stringify(project.original_notes)')==original
        assert page.evaluate('Object.keys(project.issue_reviews).length')==1
        page.locator('[data-tab=reference]').click();assert '草稿待确认' in page.locator('#reference-name').inner_text()
        page.locator('[data-tab=score]').click();page.locator('#score-grid').select_option('eighth_triplet')
        page.locator('#preview-score').click();page.wait_for_selector('#score-preview svg',timeout=45000)
        assert '三连音' in page.locator('#score-preview-status').inner_text()
        with page.expect_download() as d:page.locator('#export-score').click()
        xml=out/'功能示意三连音.musicxml';d.value.save_as(str(xml));assert b'time-modification' in xml.read_bytes()
        page.locator('#score-grid').select_option('sixteenth');assert page.locator('#score-preview').is_hidden()
        page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        result={'status':'passed','input':'user Spring30sec','tests':['numbered reference entry','unconfirmed source shown','8-note automatic motif location','human decision persists without changing original','complete ZIP download and restore to new ID','reference and decisions restored','triplet MusicXML SVG and export','grid change invalidates preview','mobile layout'],'js_errors':errors,'interpretation':'functional verification; reference rhythm unconfirmed; judgment is synthetic tool test, not actual user/music evidence'}
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
    finally:
        for id_ in ids:page.request.delete('http://127.0.0.1:8000/api/projects/'+id_)
        b.close()
