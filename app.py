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
import numpy as np

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
MODEL_LOCK = threading.Lock()
DB_LOCK = threading.Lock()


def builtin_embed(image, bits, strength=1.5):
    """Embed a short repeated payload using regional luminance differences.

    This lightweight local method exists so the complete product workflow can be
    demonstrated without a GPU. It is deliberately identified separately from
    the paper models and is not presented as their implementation.
    """
    rgb = np.asarray(image.convert('RGB'), dtype=np.float32).copy()
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
    return Image.fromarray(np.uint8(np.clip(rgb, 0, 255)))


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
    path = DATA / 'records.json'
    return json.loads(path.read_text()) if path.exists() else {}


def save_record(record):
    with DB_LOCK:
        records = database()
        records[record['id']] = record
        tmp = DATA / 'records.tmp'
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        tmp.replace(DATA / 'records.json')


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
    if method == 'trustmark':
        config = json.loads(config_path.read_text()).get(method, {}) if config_path.exists() else {}
        python = config.pop('python', sys.executable)
    elif not config_path.exists():
        raise ValueError('尚未配置推理环境：复制 config.example.json 为 config.json 并填写本地路径。')
    else:
        config = json.loads(config_path.read_text())[method]
        python = config.pop('python')
    for name in ([] if method == 'trustmark' else ['repo', 'model', 'key']):
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
        raw = base64.b64decode(q['image'].split(',', 1)[1], validate=True)
        image = Image.open(io.BytesIO(raw)).convert('RGB')
        upload_id = 'upload-' + uuid.uuid4().hex
        path = DATA / (upload_id + '.png')
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
        if len(matches) == 1:
            record, value = matches[0]
            result = {**value, 'state': 'executed', 'image': '/images/' + path.name,
                      'operation': 'uploaded', 'checked': datetime.now(timezone.utc).isoformat()}
            record['results'][upload_id] = result
            save_record(record)
            return {'state': 'matched', 'record': {k: v for k, v in record.items()
                    if k not in ('expected_bits', 'results')}, 'image': result['image'],
                    'note': '匹配到登记标识；短标识匹配仅提供来源线索，仍需人工核对。'}
        return {'state': 'ambiguous' if len(matches) > 1 else 'unmatched',
                'image': '/images/' + path.name, 'errors': errors,
                'note': '找到多个可能的登记记录，请人工复核。' if len(matches) > 1 else
                '未找到可关联的登记标识。图片可能未经登记、标识已受损或使用了尚未支持的检测方法。'}
    if action == 'watermark':
        raw = base64.b64decode(q['image'].split(',', 1)[1], validate=True)
        image = Image.open(io.BytesIO(raw)).convert('RGB')
        record_id = uuid.uuid4().hex
        before = DATA / (record_id + '-before.png')
        after = DATA / (record_id + '.png')
        image.save(before)
        method = q.get('method', 'trustmark')
        owner = q.get('owner', 'Photo Studio').strip()[:60] or 'Photo Studio'
        if method == 'visible':
            overlay = Image.new('RGBA', image.size)
            draw = ImageDraw.Draw(overlay)
            font_size = max(14, min(image.size) // 28)
            font_paths = ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                          '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
                          '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
            font = next((ImageFont.truetype(p, font_size) for p in font_paths if Path(p).exists()), ImageFont.load_default())
            box = draw.textbbox((0, 0), owner, font=font)
            width, height = box[2] - box[0], box[3] - box[1]
            margin = max(8, min(image.size) // 40)
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
        image.convert('RGB').save(DATA / (record_id + '.png'))
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
        record_id = uuid.uuid4().hex
        value = execute(q['method'], {'action': 'generate', 'prompt': q['prompt'],
                        'output': str(DATA / (record_id + '.png')), 'seed': int(q.get('seed', 42))})
        record = {'id': record_id, 'method': q['method'], 'title': q['prompt'],
                  'origin': '模型实际生成', 'positive': True,
                  'created': datetime.now(timezone.utc).isoformat(), 'results': {},
                  'generation_seconds': value['seconds']}
        if 'expected_bits' in value:
            record['expected_bits'] = value['expected_bits']
        save_record(record)
        return record
    record = database()[q['id']]
    operation = q.get('operation', 'original')
    image = transform(Image.open(DATA / (record['id'] + '.png')), operation)
    path = DATA / (record['id'] + '-' + operation + '.png')
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
            value.update({'state': 'executed', 'image': '/images/' + path.name})
        except Exception as exc:
            value = {'state': 'error', 'error': str(exc), 'image': '/images/' + path.name}
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
            writer.writerow([record['id'], record['method'], record['title'], record['positive'],
                operation, result['state'], result.get('detected', ''), result.get('bit_accuracy', ''),
                result.get('full_message_match', ''), result.get('seconds', ''), result.get('error', '')])
    return ('\ufeff' + stream.getvalue()).encode('utf-8')


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, mime='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/health':
            return self.send(200, b'{"status":"ok"}')
        if self.path == '/':
            return self.send(200, (ROOT / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        if self.path == '/assets/gsap.min.js':
            return self.send(200, (ROOT / 'assets' / 'gsap.min.js').read_bytes(), 'text/javascript; charset=utf-8')
        if self.path == '/api/records':
            # Never serve expected messages or private key material to the browser.
            records = [{k: v for k, v in r.items() if k != 'expected_bits'} for r in database().values()]
            return self.send(200, json.dumps(records, ensure_ascii=False).encode())
        if self.path == '/api/capabilities':
            config_path = ROOT / 'config.json'
            configured = json.loads(config_path.read_text()) if config_path.exists() else {}
            capabilities = {
                'builtin': True,
                'visible': True,
                'trustmark': importlib.util.find_spec('trustmark') is not None or 'trustmark' in configured,
                'spherical': 'spherical' in configured,
                'prc': 'prc' in configured,
            }
            return self.send(200, json.dumps(capabilities).encode())
        if self.path == '/report.csv':
            return self.send(200, report(), 'text/csv; charset=utf-8')
        if self.path.startswith('/images/'):
            name = self.path.removeprefix('/images/')
            if '/' in name or '\\' in name or not name.endswith('.png'):
                return self.send(404, b'{}')
            path = DATA / name
            if path.is_file():
                return self.send(200, path.read_bytes(), 'image/png')
        self.send(404, b'{}')

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 16 * 1024 * 1024:
                raise ValueError('请求大小必须在16MB以内。')
            q = json.loads(self.rfile.read(length))
            result = handle(self.path.removeprefix('/api/'), q)
            self.send(200, json.dumps(result, ensure_ascii=False).encode())
        except Exception as exc:
            self.send(400, json.dumps({'error': str(exc)}, ensure_ascii=False).encode())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()
    print(f'演示服务启动，地址 {args.host}:{args.port}；模型结果仅在实际执行后记录。', flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
