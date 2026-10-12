from fastapi.testclient import TestClient
import app

def test_online_missing_password_fails_closed(monkeypatch):
    monkeypatch.setenv('AIC_REQUIRE_AUTH','1');monkeypatch.delenv('AIC_ACCESS_PASSWORD',raising=False)
    with TestClient(app.app) as c:
        assert c.get('/').status_code==503
        assert c.get('/api/health').status_code==503

def test_login_protects_static_audio_metadata_and_mutation(monkeypatch):
    monkeypatch.setenv('AIC_REQUIRE_AUTH','1');monkeypatch.setenv('AIC_ACCESS_PASSWORD','TEST-only-password-1234')
    monkeypatch.setenv('AIC_ACCESS_USER','aic')
    with TestClient(app.app) as c:
        for route in ['/','/static/app.js','/api/projects','/api/practice-demo','/api/projects/not-a-project/audio']:
            assert c.get(route).status_code==401
        assert c.post('/api/transcribe').status_code==401
        assert c.delete('/api/projects/not-a-project').status_code==401
        assert c.get('/api/health').status_code==200
        assert c.get('/',auth=('aic','wrong')).status_code==401
        assert c.get('/',auth=('aic','TEST-only-password-1234')).status_code==200

def test_local_mode_and_malformed_credentials(monkeypatch):
    monkeypatch.delenv('AIC_REQUIRE_AUTH',raising=False);monkeypatch.delenv('AIC_ACCESS_PASSWORD',raising=False)
    with TestClient(app.app) as c:
        assert c.get('/').status_code==200
        monkeypatch.setenv('AIC_ACCESS_PASSWORD','TEST-only-password-1234')
        for value in ['Basic invalid!','Bearer token','Basic '+ 'x'*3000]:
            assert c.get('/',headers={'Authorization':value}).status_code==401
