"""Local enterprise accounts, hashed API credentials and actual request audit events.

Storage is per installation. Production use needs TLS, backups and deployment controls.
"""
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time


class AccessError(ValueError):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
              company TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
              digest TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS api_keys (
              id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
              digest TEXT UNIQUE NOT NULL, prefix TEXT NOT NULL, created REAL NOT NULL,
              revoked INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY, user_id TEXT NOT NULL, action TEXT NOT NULL,
              state TEXT NOT NULL, channel TEXT NOT NULL, application TEXT NOT NULL,
              seconds REAL NOT NULL, created REAL NOT NULL, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS inquiries (
              id TEXT PRIMARY KEY, company TEXT NOT NULL, email TEXT NOT NULL,
              service TEXT NOT NULL, note TEXT NOT NULL, created REAL NOT NULL);
            ''')

    @contextmanager
    def db(self):
        with sqlite3.connect(self.root / 'service.sqlite', timeout=20) as db:
            db.row_factory = sqlite3.Row
            yield db

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def signup(self, q):
        email = str(q.get('email', '')).strip().lower()
        company = str(q.get('company', '')).strip()
        password = str(q.get('password', ''))
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 200:
            raise ValueError('请填写有效的邮箱。')
        if not company or len(company) > 80:
            raise ValueError('请填写工作空间名称，最多80字。')
        if not 10 <= len(password) <= 128:
            raise ValueError('密码长度应为10至128个字符。')
        salt = secrets.token_hex(16)
        hashed = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        uid = secrets.token_hex(16)
        try:
            with self.db() as db:
                db.execute('INSERT INTO users VALUES(?,?,?,?,?)',
                           (uid, email, salt + ':' + hashed, company, time.time()))
        except sqlite3.IntegrityError:
            raise ValueError('该邮箱已注册，请直接登录。')
        return self.new_session(uid)

    def login(self, q):
        with self.db() as db:
            user = db.execute('SELECT * FROM users WHERE email=?',
                              (str(q.get('email', '')).strip().lower(),)).fetchone()
        password = str(q.get('password', ''))
        if len(password) > 128:
            raise AccessError('邮箱或密码不正确。')
        salt, expected = user['password'].split(':') if user else ('unregistered', '0' * 128)
        actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        if not user or not hmac.compare_digest(actual, expected):
            raise AccessError('邮箱或密码不正确。')
        return self.new_session(user['id'])

    def new_session(self, uid):
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)',
                       (self.digest(token), uid, time.time() + 7 * 86400))
        return token, self.user(uid)

    def user(self, uid):
        with self.db() as db:
            row = db.execute('SELECT id,email,company,created FROM users WHERE id=?', (uid,)).fetchone()
        return dict(row) if row else None

    def authenticate(self, cookie='', bearer=''):
        with self.db() as db:
            if bearer:
                row = db.execute('SELECT user_id,name FROM api_keys WHERE digest=? AND revoked=0',
                                 (self.digest(bearer),)).fetchone()
                if row:
                    return self.user(row['user_id']), 'api', row['name']
            elif cookie:
                row = db.execute('SELECT user_id FROM sessions WHERE digest=? AND expires>?',
                                 (self.digest(cookie), time.time())).fetchone()
                if row:
                    return self.user(row['user_id']), 'console', '控制台'
        raise AccessError('请登录企业工作空间，或提供有效的API密钥。')

    def logout(self, token):
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE digest=?', (self.digest(token),))

    def keys(self, uid):
        with self.db() as db:
            return [dict(r) for r in db.execute(
                'SELECT id,name,prefix,created,revoked FROM api_keys WHERE user_id=? ORDER BY created DESC', (uid,))]

    def create_key(self, uid, name):
        name = str(name).strip()
        if not name or len(name) > 60:
            raise ValueError('请填写应用名称，最多60字。')
        with self.db() as db:
            count = db.execute('SELECT COUNT(*) FROM api_keys WHERE user_id=? AND revoked=0', (uid,)).fetchone()[0]
            if count >= 10:
                raise ValueError('最多保留10个有效密钥，请先撤销不用的密钥。')
            token = 'ts_live_' + secrets.token_urlsafe(32)
            db.execute('INSERT INTO api_keys VALUES(?,?,?,?,?,?,0)',
                       (secrets.token_hex(12), uid, name, self.digest(token), token[:15], time.time()))
        return {'key': token, 'name': name}

    def revoke(self, uid, key_id):
        with self.db() as db:
            if not db.execute('UPDATE api_keys SET revoked=1 WHERE id=? AND user_id=?', (key_id, uid)).rowcount:
                raise ValueError('密钥不存在。')
        return {'ok': True}

    def event(self, uid, action, state, channel='console', application='控制台', seconds=0, detail=''):
        rid = 'req_' + secrets.token_hex(10)
        with self.db() as db:
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)',
                       (rid, uid, action, state, channel, application, seconds, time.time(), str(detail)[:240]))
        return rid

    def events(self, uid):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM events WHERE user_id=? ORDER BY created DESC LIMIT 500', (uid,))]

    def update_company(self, uid, company):
        company = str(company).strip()
        if not company or len(company) > 80:
            raise ValueError('工作空间名称应为1至80字。')
        with self.db() as db:
            db.execute('UPDATE users SET company=? WHERE id=?', (company, uid))
        return self.user(uid)

    def inquiry(self, q):
        company, email = str(q.get('company', '')).strip(), str(q.get('email', '')).strip()
        service, note = str(q.get('service', '')).strip(), str(q.get('note', '')).strip()
        if not company or len(company) > 80 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 200:
            raise ValueError('请填写工作空间名称和有效邮箱。')
        if service not in ('API按量服务', '企业年度订阅', '私有化部署') or len(note) > 1000:
            raise ValueError('请选择服务方案，需求描述最多1000字。')
        rid = 'inquiry_' + secrets.token_hex(8)
        with self.db() as db:
            db.execute('INSERT INTO inquiries VALUES(?,?,?,?,?,?)', (rid, company, email, service, note, time.time()))
        return {'id': rid, 'note': '需求已保存在本服务中，可下载留存；当前未接入邮件通知或销售跟进系统。'}
