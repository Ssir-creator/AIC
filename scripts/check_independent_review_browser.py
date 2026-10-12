"""Exercise offline annotation, export guards, and mismatched restore."""
import json,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
path=root/'artifacts/独立听音核对/打开这个页面.html'
with tempfile.TemporaryDirectory() as tmp,sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(accept_downloads=True);errors=[];network=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:network.append(r.url) if r.url.startswith(('http:','https:')) else None)
    # Cloud Chromium disallows file navigation. Load the same self-contained
    # document into a blank page; Windows file-opening remains a device check.
    page.set_content(path.read_text());page.wait_for_function('buffer!==null')
    page.locator('#csv').click();assert '暂不能' in page.locator('#status').inner_text()
    page.locator('#start').fill('1');page.locator('#end').fill('0.5');page.locator('#add').click()
    assert page.locator('#rows tr').count()==0
    page.locator('#end').fill('1.5');page.locator('#add').click();assert page.locator('#rows tr').count()==1
    page.locator('#reviewer').fill('TEST-NOT-REAL-USER');page.locator('#independent').check();page.locator('#complete').check()
    page.locator('#csv').click();assert '暂不能' in page.locator('#status').inner_text()
    page.get_by_role('button',name='修改',exact=True).click();page.locator('#certainty').select_option('confirmed');page.locator('#add').click()
    assert not page.locator('#complete').is_checked()
    page.locator('#complete').check()
    downloads=[];page.on('download',lambda d:downloads.append(d));page.locator('#csv').click();page.wait_for_timeout(400)
    assert len(downloads)==2
    for d in downloads:d.save_as(str(Path(tmp)/d.suggested_filename))
    r=json.loads(next(Path(tmp).glob('*.json')).read_text());assert r['scope']=={'start':0,'end':30}
    assert r['status']=='human_confirmed_not_automatically_verified'
    assert next(Path(tmp).glob('*.csv')).read_text()=='pitch,start,end\n60,1,1.5\n'
    record=next(Path(tmp).glob('*.json'));page.locator('#restore').set_input_files(str(record))
    page.wait_for_function("document.querySelector('#status').textContent.includes('已恢复')")
    assert not page.locator('#independent').is_checked() and not page.locator('#complete').is_checked()
    r['audio_sha256']='wrong-recording';wrong=Path(tmp)/'wrong-recording.json';wrong.write_text(json.dumps(r))
    page.locator('#restore').set_input_files(str(wrong))
    page.wait_for_function("document.querySelector('#status').textContent.includes('恢复失败')")
    assert page.locator('#rows tr').count()==1
    page.screenshot(path=str(root/'artifacts/独立听音核对/工具功能测试.png'),full_page=True)
    assert not errors,errors
    assert not network,network
    browser.close()
print('Offline review checks passed: export guards, edits, downloads, restore, zero network requests. Synthetic test only; no user evidence generated.')
