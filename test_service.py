"""Integration checks for tenant boundaries and actual enterprise workflows."""
import base64
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from PIL import Image
import app


class EnterpriseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(app, 'DATA', Path(self.temp.name))
        self.patch.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.cookie = ''
        _, q, self.cookie = self.call('POST', '/api/signup',
            {'company':'甲方工作空间','email':'a@example.com','password':'test password 123'})
        self.uid = q['user']['id']
        img = io.BytesIO()
        Image.new('RGB', (512,512), '#7799bb').save(img, format='PNG')
        self.image = 'data:image/png;base64,' + base64.b64encode(img.getvalue()).decode()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.patch.stop()
        self.temp.cleanup()

    def call(self, method, path, body=None, cookie=None, key=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        headers = {'Content-Type':'application/json'}
        if cookie is not None or self.cookie:
            headers['Cookie'] = self.cookie if cookie is None else cookie
        if key:
            headers['Authorization'] = 'Bearer ' + key
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        raw = response.read()
        result = json.loads(raw) if response.getheader('Content-Type','').startswith('application/json') else raw
        cookie_out = (response.getheader('Set-Cookie') or '').split(';')[0]
        status = response.status
        conn.close()
        return status, result, cookie_out

    def create_image(self, visibility='private'):
        status, result, _ = self.call('POST', '/api/watermark',
            {'image':self.image,'method':'builtin','title':'新品图','task_id':'internal-42',
             'owner':'私有声明','platform':'甲平台','visibility':visibility})
        self.assertEqual(status, 200)
        self.assertNotIn('expected_bits', result)
        image = Path(self.temp.name) / 'workspaces' / self.uid / (result['id'] + '.png')
        return result['id'], 'data:image/png;base64,' + base64.b64encode(image.read_bytes()).decode()

    def test_workspace_and_image_isolation(self):
        rid, _ = self.create_image()
        self.assertEqual(self.call('GET', '/images/' + rid + '.png', cookie='')[0], 401)
        _, other, cookie = self.call('POST', '/api/signup',
            {'company':'乙方','email':'b@example.com','password':'different password'})
        self.assertNotEqual(other['user']['id'], self.uid)
        self.assertEqual(self.call('GET', '/api/records', cookie=cookie)[1], [])
        self.assertEqual(self.call('GET', '/images/' + rid + '.png', cookie=cookie)[0], 404)
        self.assertEqual(self.call('POST', '/api/metadata', {'id':rid,'visibility':'public'}, cookie=cookie)[0],400)

    def test_public_verification_redacts_private_and_allowlists_public_fields(self):
        rid, encoded = self.create_image()
        q = self.call('POST','/api/public/trace',{'image':encoded},cookie='')[1]
        self.assertEqual(q['state'],'restricted')
        self.assertNotIn('record',q)
        self.call('POST','/api/metadata',{'id':rid,'visibility':'public'})
        q = self.call('POST','/api/public/trace',{'image':encoded},cookie='')[1]
        self.assertEqual(q['state'],'matched')
        self.assertEqual(set(q['record']),{'id','title','platform','created'})
        self.assertNotIn('internal-42',json.dumps(q))
        self.assertFalse(list(Path(self.temp.name).rglob('upload-*.png')))

    def test_keys_can_access_only_owner_and_revocation_is_effective(self):
        status,key,_ = self.call('POST','/api/keys',{'name':'生成业务'})
        self.assertEqual(status,200)
        self.assertEqual(self.call('GET','/api/records',cookie='',key=key['key'])[0],200)
        keys = self.call('GET','/api/keys')[1]
        self.assertNotIn(key['key'],json.dumps(keys))
        raw = (Path(self.temp.name) / '_service' / 'service.sqlite').read_bytes()
        self.assertNotIn(key['key'].encode(),raw)
        self.call('POST','/api/keys/revoke',{'id':keys[0]['id']})
        self.assertEqual(self.call('GET','/api/records',cookie='',key=key['key'])[0],401)
        self.assertTrue(any(e['channel']=='api' for e in self.call('GET','/api/events')[1]))

    def test_async_job_keeps_workspace_and_metadata(self):
        status,q,_ = self.call('POST','/api/jobs',{'action':'watermark','payload':
            {'image':self.image,'method':'builtin','title':'异步任务','task_id':'task-abc'}})
        self.assertEqual(status,202)
        for _ in range(100):
            result = self.call('GET','/api/jobs/'+q['job_id'])[1]
            if result['state'] != 'running': break
            time.sleep(.02)
        self.assertEqual(result['state'],'done')
        self.assertNotIn('expected_bits',result['result'])
        records = self.call('GET','/api/records')[1]
        self.assertEqual(records[0]['task_id'],'task-abc')
        self.assertEqual(records[0]['platform'],'甲方工作空间')
        _,_,other = self.call('POST','/api/signup',
            {'company':'乙方','email':'b@example.com','password':'different password'})
        self.assertEqual(self.call('GET','/api/jobs/'+q['job_id'],cookie=other)[0],404)

    def test_login_logout_and_password_storage(self):
        self.assertEqual(self.call('POST','/api/login',{'email':'a@example.com','password':'wrong'})[0],401)
        status,_,cookie = self.call('POST','/api/login',{'email':'a@example.com','password':'test password 123'})
        self.assertEqual(status,200)
        self.call('POST','/api/logout',{},cookie=cookie)
        self.assertEqual(self.call('GET','/api/records',cookie=cookie)[0],401)
        self.assertNotIn(b'test password 123',(Path(self.temp.name)/'_service'/'service.sqlite').read_bytes())

    def test_public_and_empty_states_are_not_fake_results(self):
        self.assertEqual(self.call('GET','/api/records')[1],[])
        result=self.call('POST','/api/public/trace',{'image':self.image},cookie='')[1]
        self.assertEqual(result['state'],'unmatched')
        self.assertNotIn('record',result)
        status,q,_=self.call('POST','/api/inquiry',{'company':'测试企业','email':'contact@example.com',
          'service':'私有化部署','note':'需要本地GPU部署'},cookie='')
        self.assertEqual(status,200)
        self.assertTrue(q['id'].startswith('inquiry_'))
        self.assertIn('未接入邮件',q['note'])

    def test_public_async_job_only_exposes_public_result(self):
        _, encoded = self.create_image('public')
        status,q,_ = self.call('POST','/api/public/jobs',{'image':encoded},cookie='')
        self.assertEqual(status,202)
        for _ in range(100):
            status,result,_=self.call('GET','/api/public/jobs/'+q['job_id'],cookie='')
            if result['state'] != 'running': break
            time.sleep(.02)
        self.assertEqual(result['state'],'done')
        self.assertEqual(result['result']['state'],'matched')
        self.assertNotIn('internal-42',json.dumps(result))
        self.assertNotIn('workspace',result)
        self.assertEqual(self.call('GET','/api/jobs/'+q['job_id'])[0],404)

    def test_demo_video_range_and_content_type(self):
        root=Path(self.temp.name)/'static'
        (root/'assets').mkdir(parents=True)
        (root/'assets'/'demo.mp4').write_bytes(b'0123456789abcdef')
        with patch.object(app,'ROOT',root):
            conn=http.client.HTTPConnection('127.0.0.1',self.port)
            conn.request('GET','/assets/demo.mp4',headers={'Range':'bytes=2-5'})
            response=conn.getresponse()
            self.assertEqual(response.status,206)
            self.assertEqual(response.getheader('Content-Type'),'video/mp4')
            self.assertEqual(response.getheader('Content-Range'),'bytes 2-5/16')
            self.assertEqual(response.read(),b'2345')
            conn.close()
            conn=http.client.HTTPConnection('127.0.0.1',self.port)
            conn.request('GET','/assets/demo.mp4',headers={'Range':'bytes=99-'})
            response=conn.getresponse()
            self.assertEqual(response.status,416)
            response.read()
            conn.close()

    def test_failed_model_does_not_register_or_claim_success(self):
        with patch.object(app,'execute',side_effect=RuntimeError('model unavailable')):
            status,_,_=self.call('POST','/api/watermark',{'image':self.image,'method':'trustmark'})
        self.assertEqual(status,500)
        self.assertEqual(self.call('GET','/api/records')[1],[])
        events=self.call('GET','/api/events')[1]
        self.assertEqual(events[0]['state'],'error')


if __name__=='__main__':
    unittest.main()
