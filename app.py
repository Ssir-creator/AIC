import base64
import csv
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import importlib.util
from pathlib import Path
import subprocess
import threading
import uuid
import sys
import time
import traceback
import contextvars
import re
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from service_store import Store, AccessError
import numpy as np

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
MODEL_LOCK = threading.Lock()
DB_LOCK = threading.Lock()
VERSION = '2026.10.20.2'
WORKSPACE = contextvars.ContextVar('workspace', default=None)


def data_dir():
    uid = WORKSPACE.get()
    path = DATA / 'workspaces' / uid if uid else DATA
    path.mkdir(parents=True, exist_ok=True)
    return path


def store():
    return Store(DATA / '_service')
JOBS = {}
JOBS_LOCK = threading.Lock()
JOB_SLOT = threading.BoundedSemaphore(1)


def read_image(encoded):
    if not isinstance(encoded, str) or ',' not in encoded:
        raise ValueError('图片数据不完整，请重新选择原始图片。')
    raw = base64.b64decode(encoded.split(',', 1)[1], validate=True)
    image = Image.open(io.BytesIO(raw))
    if image.width * image.height > 16_000_000:
        raise ValueError('图片分辨率过大，请先缩小到1600万像素以内后重试。')
    return image.convert('RGB')


def start_job(action, payload, identity=None, public=False):
    if action not in ('watermark', 'generate', 'trace'):
        raise ValueError('不支持的任务类型。')
    if not JOB_SLOT.acquire(blocking=False):
        raise ValueError('已有图片任务正在处理，请等待完成后重试。')
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        for key in list(JOBS):
            if JOBS[key]['state'] != 'running' and (time.monotonic() - JOBS[key]['created'] > 3600 or len(JOBS) >= 32):
                del JOBS[key]
        JOBS[job_id] = {'state': 'running', 'created': time.monotonic(),
                        'workspace': 'public' if public else identity[0]['id'] if identity else None}

    context = contextvars.copy_context()

    def work():
        outcome = {'state': 'error', 'error': '图片任务被中断，请检查日志后重试。'}
        try:
            result = public_trace(payload) if public else run_action(action, payload, identity) if identity else handle(action, payload)
            outcome = {'state': 'done', 'result': result}
        except Exception as exc:
            traceback.print_exc()
            outcome = {'state': 'error', 'error': '公开核验未完成，请稍后重试。' if public else str(exc)}
        finally:
            with JOBS_LOCK:
                JOBS[job_id].update(outcome)
            JOB_SLOT.release()

    threading.Thread(target=lambda: context.run(work), daemon=True).start()
    return {'job_id': job_id}


def builtin_embed(image, bits, strength=1.5):
    """Embed a short repeated payload using regional luminance differences.

    This lightweight local method exists so the complete product workflow can be
    demonstrated without a GPU. It is deliberately identified separately from
    the paper models and is not presented as their implementation.
    """
    rgb = np.array(image.convert('RGB'), dtype=np.float32)
    height, width = rgb.shape[:2]
    if min(width, height) < 128:
        raise ValueError('图片宽高至少为128像素。')
    luminance = rgb.mean(axis=2)
    grid = 32
    for cell in range(grid * grid):
        row, col = divmod(cell, grid)
        y0, y1 = round(row * height / grid), round((row + 1) * height / grid)
        x0, x1 = round(col * width / grid), round((col + 1) * width / grid)
        vertical = (row + col) % 2 == 0
        if vertical:
            mid = (x0 + x1) // 2
            first, second = luminance[y0:y1, x0:mid], luminance[y0:y1, mid:x1]
            first_rgb, second_rgb = rgb[y0:y1, x0:mid], rgb[y0:y1, mid:x1]
        else:
            mid = (y0 + y1) // 2
            first, second = luminance[y0:mid, x0:x1], luminance[mid:y1, x0:x1]
            first_rgb, second_rgb = rgb[y0:mid, x0:x1], rgb[mid:y1, x0:x1]
        if not first.size or not second.size:
            continue
        correction = strength if bits[(cell * 13) % len(bits)] else -strength
        first_rgb += correction
        second_rgb -= correction
        first += correction
        second -= correction
    np.clip(rgb, 0, 255, out=rgb)
    return Image.fromarray(rgb.astype(np.uint8))


def builtin_detect(image, expected_bits):
    rgb = np.asarray(image.convert('RGB'), dtype=np.float32)
    height, width = rgb.shape[:2]
    luminance = rgb.mean(axis=2)
    votes = [[] for _ in expected_bits]
    margins = []
    grid = 32
    for cell in range(grid * grid):
        row, col = divmod(cell, grid)
        y0, y1 = round(row * height / grid), round((row + 1) * height / grid)
        x0, x1 = round(col * width / grid), round((col + 1) * width / grid)
        if (row + col) % 2 == 0:
            mid = (x0 + x1) // 2
            first, second = luminance[y0:y1, x0:mid], luminance[y0:y1, mid:x1]
        else:
            mid = (y0 + y1) // 2
            first, second = luminance[y0:mid, x0:x1], luminance[mid:y1, x0:x1]
        if first.size and second.size:
            diff = float(first.mean() - second.mean())
            votes[(cell * 13) % len(expected_bits)].append(1 if diff >= 0 else 0)
            margins.append(abs(diff))
    recovered = [int(sum(v) >= len(v) / 2) for v in votes]
    accuracy = sum(a == b for a, b in zip(recovered, expected_bits)) / len(expected_bits)
    confidence = min(1.0, (sum(margins) / max(1, len(margins))) / 10.0)
    return {'detected': accuracy >= .875, 'bit_accuracy': accuracy,
            'full_message_match': accuracy == 1.0, 'confidence': confidence,
            'recovered_bits': recovered, 'seconds': 0,
            'note': '图溯内置轻量水印检测；不代表TrustMark、PRC或球形水印结果'}


def database():
    path = data_dir() / 'records.json'
    return json.loads(path.read_text()) if path.exists() else {}


def save_record(record):
    with DB_LOCK:
        records = database()
        records[record['id']] = record
        tmp = data_dir() / 'records.tmp'
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        tmp.replace(data_dir() / 'records.json')


def transform(image, operation):
    image = image.convert('RGB')
    if operation.startswith('jpeg'):
        stream = io.BytesIO()
        image.save(stream, format='JPEG', quality=int(operation[4:]))
        stream.seek(0)
        return Image.open(stream).copy()
    if operation == 'resize50':
        return image.resize((max(1, image.width // 2), max(1, image.height // 2)), Image.Resampling.LANCZOS)
    if operation == 'crop70':
        width, height = max(1, round(image.width * .7)), max(1, round(image.height * .7))
        left, top = (image.width - width) // 2, (image.height - height) // 2
        return image.crop((left, top, left + width, top + height))
    if operation == 'original':
        return image.copy()
    raise ValueError('Unsupported transformation')


def execute(method, request):
    config_path = ROOT / 'config.json'
    if method in ('trustmark', 'local-image'):
        config = json.loads(config_path.read_text()).get(method, {}) if config_path.exists() else {}
        python = config.pop('python', sys.executable)
    elif not config_path.exists():
        raise ValueError('尚未配置推理环境：复制 config.example.json 为 config.json 并填写本地路径。')
    else:
        config = json.loads(config_path.read_text())[method]
        python = config.pop('python')
    for name in ([] if method in ('trustmark', 'local-image') else ['repo', 'model', 'key']):
        if not Path(config[name]).exists():
            raise ValueError(f'本地配置路径不存在：{name}')
    payload = {**config, **request, 'method': method}
    with MODEL_LOCK:
        result = subprocess.run([python, str(ROOT / 'model_worker.py')],
            input=json.dumps(payload), text=True, capture_output=True, timeout=1800)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError('推理进程未返回有效结果；检查对应环境依赖。')
    if result.returncode or 'error' in value:
        raise RuntimeError(value.get('error', '模型执行失败'))
    return value


def handle(action, q):
    if action == 'trace':
        image = read_image(q['image'])
        upload_id = 'upload-' + uuid.uuid4().hex
        path = data_dir() / (upload_id + '.png')
        image.save(path)
        matches = []
        errors = []
        registered = database()
        trustmark_records = [r for r in registered.values() if r['method'] == 'trustmark']
        for record in registered.values():
            if record['method'] != 'builtin':
                continue
            value = builtin_detect(image, record['expected_bits'])
            if value['full_message_match']:
                matches.append((record, value))
        if trustmark_records:
            try:
                value = execute('trustmark', {'action': 'detect', 'image': str(path)})
                message = value.get('message')
                for record in trustmark_records:
                    if value.get('detected') and message == record['id'][:8]:
                        matches.append((record, value))
            except Exception as exc:
                errors.append(str(exc))
        detected_types = []
        spherical_records = [r for r in registered.values() if r['method'] == 'spherical']
        if spherical_records:
            try:
                value = execute('spherical', {'action': 'detect', 'image': str(path)})
                for record in spherical_records:
                    if record.get('expected_bits') and value.get('recovered_bits') == record['expected_bits']:
                        matches.append((record, {**value, 'full_message_match': True}))
            except Exception as exc:
                errors.append(str(exc))
        if any(r['method'] == 'prc' for r in registered.values()):
            try:
                value = execute('prc', {'action': 'detect', 'image': str(path)})
                if value.get('detected'):
                    detected_types.append('PRC')
            except Exception as exc:
                errors.append(str(exc))
        if len(matches) == 1:
            record, value = matches[0]
            result = {**value, 'state': 'executed', 'image': '/images/' + path.name,
                      'operation': 'uploaded', 'checked': datetime.now(timezone.utc).isoformat()}
            if q.get('_record_result', True):
                record['results'][upload_id] = result
                save_record(record)
            path.unlink(missing_ok=True)
            return {'state': 'matched', 'record': {k: v for k, v in record.items()
                    if k not in ('expected_bits', 'results')}, 'image': result['image'],
                    'note': '匹配到登记标识；短标识匹配仅提供来源线索，仍需人工核对。'}
        path.unlink(missing_ok=True)
        return {'state': 'ambiguous' if len(matches) > 1 else 'detected_only' if detected_types else 'incomplete' if errors else 'unmatched',
                'detected_types': detected_types,
                'image': '/images/' + path.name, 'errors': errors,
                'note': '找到多个可能的登记记录，请人工复核。' if len(matches) > 1 else
                '检出支持的PRC水印，但该适配器不提供唯一任务标识，无法关联单张图片来源。' if detected_types else
                '部分模型未完成检测，不能据此判断未检出。' if errors else
                '未找到可关联的登记标识。图片可能未经登记、标识已受损或使用了尚未支持的检测方法。'}
    if action == 'watermark':
        image = read_image(q['image'])
        record_id = uuid.uuid4().hex
        before = data_dir() / (record_id + '-before.png')
        after = data_dir() / (record_id + '.png')
        image.save(before)
        method = q.get('method', 'trustmark')
        owner = str(q.get('owner', '')).strip()[:60]
        if method == 'visible' and not owner:
            raise ValueError('请填写要显示在图片上的署名。')
        if method == 'visible':
            overlay = Image.new('RGBA', image.size)
            draw = ImageDraw.Draw(overlay)
            font_size = max(14, min(image.size) // 28)
            font_paths = [str(ROOT / 'assets/fonts/NotoSansCJKsc-Regular.otf'),
                          '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                          '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
                          '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
            font = next((ImageFont.truetype(p, font_size) for p in font_paths if Path(p).exists()), ImageFont.load_default())
            box = draw.textbbox((0, 0), owner, font=font)
            width, height = box[2] - box[0], box[3] - box[1]
            margin = max(8, min(image.size) // 40)
            while width + margin * 3 > image.width and font_size > 1:
                font_size -= 1
                font = next((ImageFont.truetype(p, font_size) for p in font_paths if Path(p).exists()), ImageFont.load_default())
                box = draw.textbbox((0, 0), owner, font=font)
                width, height = box[2] - box[0], box[3] - box[1]
            draw.rounded_rectangle((image.width-width-margin*3, image.height-height-margin*3,
                                    image.width-margin, image.height-margin), radius=6, fill=(16, 28, 25, 155))
            draw.text((image.width-width-margin*2, image.height-height-margin*2-box[1]), owner, font=font, fill='white')
            Image.alpha_composite(image.convert('RGBA'), overlay).convert('RGB').save(after)
            value = {'seconds': 0, 'note': '真实可见署名，不包含隐形水印'}
        elif method == 'builtin':
            bits = [int(x) for x in f'{int(record_id[:4], 16):016b}']
            builtin_embed(image, bits).save(after)
            value = {'seconds': 0, 'expected_bits': bits,
                     'note': '图溯内置轻量水印，可在无GPU环境完成演示'}
        elif method == 'trustmark':
            value = execute(method, {'action': 'watermark', 'image': str(before),
                            'output': str(after), 'message': record_id[:8]})
        else:
            raise ValueError('照片加水印仅支持可见署名或TrustMark。')
        record = {'id': record_id, 'method': method, 'title': q.get('title', '摄影作品'),
                  'owner': owner, 'origin': '实际加水印输出', 'positive': True,
                  'created': datetime.now(timezone.utc).isoformat(), 'results': {}}
        if method == 'builtin':
            record['expected_bits'] = value['expected_bits']
        save_record(record)
        return {'id': record_id, 'before': '/images/' + before.name,
                'after': '/images/' + after.name, 'method': method, **value}
    if action == 'register':
        raw = base64.b64decode(q['image'].split(',', 1)[1], validate=True)
        image = Image.open(io.BytesIO(raw))
        image.load()
        record_id = uuid.uuid4().hex
        image.convert('RGB').save(data_dir() / (record_id + '.png'))
        record = {'id': record_id, 'method': q['method'], 'title': q.get('title', ''),
                  'origin': '导入图片，水印状态尚未验证', 'positive': q.get('positive', True),
                  'created': datetime.now(timezone.utc).isoformat(), 'results': {}}
        if q.get('bits'):
            bits = ''.join(q['bits'].split())
            if not bits or set(bits) - {'0', '1'} or len(bits) > 16384:
                raise ValueError('预期消息必须是二进制字符串，最长16384位。')
            record['expected_bits'] = list(map(int, bits))
        save_record(record)
        return record
    if action == 'generate':
        prompt = str(q.get('prompt', '')).strip()
        if not prompt or len(prompt) > 1000:
            raise ValueError('请填写图片描述，最多1000个字符。')
        if q.get('method') == 'local-image':
            watermark_method = q.get('watermark_method', 'trustmark')
            if watermark_method not in ('trustmark', 'builtin', 'visible'):
                raise ValueError('请选择可用的图片保护方式。')
            if watermark_method == 'visible' and not str(q.get('owner', '')).strip():
                raise ValueError('使用可见署名时，请先填写署名。')
            generated = data_dir() / ('draft-' + uuid.uuid4().hex + '.png')
            value = execute('local-image', {'prompt': prompt, 'output': str(generated),
                                           'seed': int(q.get('seed', 42))})
            encoded = base64.b64encode(generated.read_bytes()).decode()
            result = handle('watermark', {'image': 'data:image/png;base64,' + encoded,
                          'method': watermark_method, 'owner': q.get('owner', ''),
                          'title': q.get('title', '') or 'AI营销配图'})
            record = database()[result['id']]
            record.update({'prompt': prompt, 'generation_model': 'segmind/tiny-sd',
                           'generation_seconds': value['seconds'], 'generation_route': '生成后添加水印'})
            save_record(record)
            generated.unlink(missing_ok=True)
            return {**result, 'generation_seconds': value['seconds'], 'route': '生成后添加水印'}
        record_id = uuid.uuid4().hex
        value = execute(q['method'], {'action': 'generate', 'prompt': q['prompt'],
                        'output': str(data_dir() / (record_id + '.png')), 'seed': int(q.get('seed', 42))})
        record = {'id': record_id, 'method': q['method'], 'title': q.get('title') or q['prompt'],
                  'owner': str(q.get('owner', ''))[:60], 'prompt': q['prompt'],
                  'origin': '模型实际生成', 'positive': True,
                  'created': datetime.now(timezone.utc).isoformat(), 'results': {},
                  'generation_seconds': value['seconds']}
        if 'expected_bits' in value:
            record['expected_bits'] = value['expected_bits']
        save_record(record)
        return record
    record = database()[q['id']]
    operation = q.get('operation', 'original')
    image = transform(Image.open(data_dir() / (record['id'] + '.png')), operation)
    path = data_dir() / (record['id'] + '-' + operation + '.png')
    image.save(path)
    if action == 'transform':
        return {'image': '/images/' + path.name, 'size': image.size,
                'operation': operation, 'note': '仅完成传播处理，尚未检测水印'}
    if action == 'detect':
        try:
            if record['method'] == 'builtin':
                value = builtin_detect(image, record['expected_bits'])
            elif record['method'] == 'visible':
                raise ValueError('该素材只有可见署名，没有可检测的隐形标识。')
            else:
                value = execute(record['method'], {'action': 'detect', 'image': str(path),
                                                   'expected_bits': record.get('expected_bits')})
            value.update({'state': 'executed', 'image': '/images/' + path.name,
                          'operation': operation, 'checked': datetime.now(timezone.utc).isoformat()})
        except Exception as exc:
            value = {'state': 'error', 'error': str(exc), 'image': '/images/' + path.name,
                     'operation': operation, 'checked': datetime.now(timezone.utc).isoformat()}
        record['results'][operation] = value
        save_record(record)
        return value
    raise ValueError('Unknown operation')


def report():
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(['record_id', 'method', 'title', 'positive', 'operation', 'state',
                     'detected', 'bit_accuracy', 'full_message_match', 'seconds', 'error'])
    for record in database().values():
        for operation, result in (record['results'] or {'original': {'state': 'unrun'}}).items():
            title = str(record['title'])
            if title.lstrip().startswith(('=', '+', '-', '@')):
                title = "'" + title
            writer.writerow([record['id'], record['method'], title, record['positive'],
                operation, result['state'], result.get('detected', ''), result.get('bit_accuracy', ''),
                result.get('full_message_match', ''), result.get('seconds', ''), result.get('error', '')])
    return ('\ufeff' + stream.getvalue()).encode('utf-8')


def clean_record(record):
    return {k: v for k, v in record.items() if k != 'expected_bits'}


def run_action(action, payload, identity):
    user, channel, application = identity
    started = time.perf_counter()
    try:
        if action not in ('watermark', 'generate', 'trace', 'transform', 'detect', 'register', 'metadata'):
            raise ValueError('不支持的操作。')
        if action == 'metadata':
            record = database()[payload['id']]
            record['visibility'] = 'public' if payload.get('visibility') == 'public' else 'private'
            save_record(record)
            result = clean_record(record)
        else:
            result = handle(action, payload)
        if action in ('watermark', 'generate', 'register'):
            record = database()[result['id']]
            record.update({'task_id': str(payload.get('task_id', ''))[:120] or 'task_' + uuid.uuid4().hex[:12],
                           'platform': str(payload.get('platform', ''))[:80] or user['company'],
                           'application': application,
                           'visibility': 'public' if payload.get('visibility') == 'public' else 'private'})
            save_record(record)
        failed = result.get('state') in ('error', 'incomplete')
        rid = store().event(user['id'], action, 'error' if failed else 'success', channel, application,
                            time.perf_counter() - started, result.get('error', ''))
        result = {**result, 'request_id': rid}
        return {k: v for k, v in result.items() if k not in ('expected_bits', 'recovered_bits')}
    except Exception as exc:
        store().event(user['id'], action, 'error', channel, application, time.perf_counter()-started, str(exc))
        raise


def public_trace(payload):
    # Detection searches only locally registered content; it is not a universal AI classifier.
    read_image(payload.get('image'))
    directories = [None]
    root = DATA / 'workspaces'
    if root.exists():
        directories += [p.name for p in root.iterdir() if p.is_dir()]
    matches, errors, detected = [], [], False
    for uid in directories:
        token = WORKSPACE.set(uid)
        try:
            if not database():
                continue
            result = handle('trace', {**payload, '_record_result': False})
            if result['state'] == 'ambiguous':
                return {'state': 'ambiguous', 'note': '存在多个匹配标识，暂时无法唯一关联来源。'}
            if result['state'] == 'matched':
                matches.append(result['record'])
            detected = detected or result['state'] == 'detected_only'
            errors += result.get('errors', [])
        finally:
            WORKSPACE.reset(token)
    if len(matches) > 1:
        return {'state': 'ambiguous', 'note': '存在多个匹配标识，请进一步人工核对。'}
    if matches:
        record = matches[0]
        if record.get('visibility') != 'public':
            return {'state': 'restricted', 'note': '已匹配登记标识。来源记录由登记方设为非公开，未披露内部信息。'}
        return {'state': 'matched', 'record': {k: record.get(k, '') for k in ('id', 'title', 'platform', 'created')},
                'note': '标识与公开登记记录匹配；登记信息由提交方声明，不构成版权或事实真实性证明。'}
    return {'state': 'detected_only' if detected else 'incomplete' if errors else 'unmatched',
            'note': '检出支持的水印，但无法关联唯一来源记录。' if detected else
                    '部分检测未完成，请稍后重试。' if errors else
                    '未检出可关联的支持水印，不代表该图片不是AI生成。'}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, mime='application/json; charset=utf-8', cookie=None, extra_headers=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        if cookie is not None:
            secure = '; Secure' if self.headers.get('X-Forwarded-Proto') == 'https' else ''
            self.send_header('Set-Cookie', 'tusu_session=' + cookie + '; Path=/; HttpOnly; SameSite=Strict' + secure + ('; Max-Age=0' if not cookie else '; Max-Age=604800'))
        self.end_headers()
        self.wfile.write(body)

    def json(self, value, status=200, cookie=None):
        return self.send(status, json.dumps(value, ensure_ascii=False).encode(), cookie=cookie)

    def session_cookie(self):
        jar = SimpleCookie()
        jar.load(self.headers.get('Cookie', ''))
        return jar['tusu_session'].value if 'tusu_session' in jar else ''

    def identity(self):
        auth = self.headers.get('Authorization', '')
        return store().authenticate(self.session_cookie(), auth[7:] if auth.startswith('Bearer ') else '')

    def do_GET(self):
        token = None
        try:
            path = urlsplit(self.path).path
            if path == '/':
                return self.send(200, (ROOT / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            if path.startswith('/assets/'):
                asset = (ROOT / path[1:]).resolve()
                if not asset.is_relative_to((ROOT / 'assets').resolve()) or not asset.is_file():
                    return self.json({'error': '文件不存在。'}, 404)
                mime = {'.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
                        '.svg': 'image/svg+xml', '.otf': 'font/otf', '.html': 'text/html; charset=utf-8',
                        '.mp4': 'video/mp4', '.png': 'image/png', '.srt': 'text/plain; charset=utf-8',
                        '.csv': 'text/csv; charset=utf-8'}.get(asset.suffix, 'application/octet-stream')
                if asset.suffix == '.mp4':
                    size = asset.stat().st_size
                    requested = self.headers.get('Range')
                    if requested:
                        match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
                        if not match or not any(match.groups()):
                            return self.send(416, b'', mime, extra_headers={'Content-Range': f'bytes */{size}'})
                        first, last = match.groups()
                        start = int(first) if first else max(0, size-int(last))
                        end = min(size-1, int(last)) if first and last else size-1
                        if start >= size or start > end or (not first and int(last) == 0):
                            return self.send(416, b'', mime, extra_headers={'Content-Range': f'bytes */{size}'})
                        with asset.open('rb') as stream:
                            stream.seek(start)
                            body = stream.read(end-start+1)
                        return self.send(206, body, mime, extra_headers={
                            'Accept-Ranges': 'bytes', 'Content-Range': f'bytes {start}-{end}/{size}'})
                    return self.send(200, asset.read_bytes(), mime, extra_headers={'Accept-Ranges': 'bytes'})
                return self.send(200, asset.read_bytes(), mime)
            if path == '/health':
                return self.json({'status': 'ok', 'version': VERSION})
            if path == '/api/capabilities':
                config_path = ROOT / 'config.json'
                configured = json.loads(config_path.read_text()) if config_path.exists() else {}
                return self.json({'builtin': True, 'visible': True,
                    'trustmark': importlib.util.find_spec('trustmark') is not None or 'trustmark' in configured,
                    'spherical': 'spherical' in configured, 'prc': 'prc' in configured,
                    'local-image': all(importlib.util.find_spec(m) is not None for m in ('torch','diffusers','transformers'))})
            if path.startswith('/api/public/jobs/'):
                job_id = path.removeprefix('/api/public/jobs/')
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                    value = {k: v for k, v in job.items() if k not in ('created', 'workspace')} if job and job.get('workspace') == 'public' else None
                return self.json(value) if value else self.json({'error': '核验任务不存在或服务已重启。'}, 404)
            if path == '/api/session':
                try:
                    return self.json({'user': self.identity()[0]})
                except AccessError:
                    return self.json({'user': None})
            identity = self.identity()
            user = identity[0]
            token = WORKSPACE.set(user['id'])
            if path.startswith('/api/jobs/'):
                job_id = path.removeprefix('/api/jobs/')
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                    value = {k: v for k, v in job.items() if k not in ('created', 'workspace')} if job and job.get('workspace') == user['id'] else None
                return self.json(value, 200) if value else self.json({'error': '任务不存在或服务已重启。'}, 404)
            if path == '/api/records':
                if identity[1] == 'api':
                    store().event(user['id'], 'records', 'success', 'api', identity[2])
                return self.json([clean_record(r) for r in database().values()])
            if path == '/api/keys':
                return self.json(store().keys(user['id']))
            if path == '/api/events':
                return self.json(store().events(user['id']))
            if path == '/report.csv':
                return self.send(200, report(), 'text/csv; charset=utf-8')
            if path.startswith('/images/'):
                name = path.removeprefix('/images/')
                if '/' not in name and '\\' not in name and name.endswith('.png'):
                    image = data_dir() / name
                    if image.is_file():
                        return self.send(200, image.read_bytes(), 'image/png')
            return self.json({'error': '请求的资源不存在。'}, 404)
        except AccessError as exc:
            return self.json({'error': str(exc)}, 401)
        except Exception:
            traceback.print_exc()
            return self.json({'error': '读取失败，请查看服务日志。'}, 500)
        finally:
            if token is not None:
                WORKSPACE.reset(token)

    def do_POST(self):
        token = None
        try:
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                return self.json({'error': '不允许跨站提交。'}, 403)
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 16 * 1024 * 1024:
                raise ValueError('请求大小必须在16MB以内。')
            q = json.loads(self.rfile.read(length))
            if not isinstance(q, dict):
                raise ValueError('请求应为JSON对象。')
            path = urlsplit(self.path).path
            if path in ('/api/signup', '/api/login'):
                session, user = store().signup(q) if path == '/api/signup' else store().login(q)
                return self.json({'user': user}, cookie=session)
            if path == '/api/logout':
                store().logout(self.session_cookie())
                return self.json({'ok': True}, cookie='')
            if path == '/api/inquiry':
                return self.json(store().inquiry(q))
            if path == '/api/public/jobs':
                return self.json(start_job('trace', q, public=True), 202)
            if path == '/api/public/trace':
                if not JOB_SLOT.acquire(blocking=False):
                    raise ValueError('检测服务繁忙，请稍后重试。')
                try:
                    return self.json(public_trace(q))
                finally:
                    JOB_SLOT.release()
            identity = self.identity()
            user = identity[0]
            token = WORKSPACE.set(user['id'])
            if path == '/api/keys':
                return self.json(store().create_key(user['id'], q.get('name', '')))
            if path == '/api/keys/revoke':
                return self.json(store().revoke(user['id'], q.get('id')))
            if path == '/api/profile':
                return self.json({'user': store().update_company(user['id'], q.get('company'))})
            if path == '/api/jobs':
                return self.json(start_job(q['action'], q['payload'], identity), 202)
            action = path.removeprefix('/api/')
            if action in ('watermark', 'generate', 'trace'):
                if not JOB_SLOT.acquire(blocking=False):
                    raise ValueError('已有图片任务正在执行，请稍后重试。')
                try:
                    return self.json(run_action(action, q, identity))
                finally:
                    JOB_SLOT.release()
            return self.json(run_action(action, q, identity))
        except AccessError as exc:
            return self.json({'error': str(exc)}, 401)
        except (ValueError, KeyError) as exc:
            return self.json({'error': str(exc)}, 400)
        except Exception:
            traceback.print_exc()
            return self.json({'error': '处理未完成，请检查模型环境或服务日志后重试。'}, 500)
        finally:
            if token is not None:
                WORKSPACE.reset(token)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()
    print(f'图溯服务启动，地址 {args.host}:{args.port}；模型结果仅在实际执行后记录。', flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
