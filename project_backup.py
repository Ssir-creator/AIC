"""Bounded private ZIP snapshots; never extract supplied archive paths."""
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED,BadZipFile

LIMITS={'project.json':8*1024*1024,'audio.wav':8*1024*1024,'source.audio':20*1024*1024,'manifest.json':65536}

def make_backup(folder,project):
    files={'project.json':json.dumps(project,ensure_ascii=False,allow_nan=False).encode(),
           'audio.wav':(folder/'audio.wav').read_bytes()}
    if (folder/'source').is_file():files['source.audio']=(folder/'source').read_bytes()
    if any(len(data)>LIMITS[name] for name,data in files.items()):
        raise ValueError('项目记录过大，不能打包；请先导出记录并缩短操作历史')
    manifest={'schema':'puyigai-backup-v1','files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()},
              'warning':'private source snapshot; contains recording; not certified ground truth'}
    result=io.BytesIO()
    with ZipFile(result,'w',ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
        z.writestr('manifest.json',json.dumps(manifest))
    return result.getvalue()

def unpack_backup(content):
    try:
        with ZipFile(io.BytesIO(content)) as z:
            names=z.namelist()
            if len(names)!=len(set(names)) or not {'project.json','audio.wav','manifest.json'}<=set(names) or not set(names)<=set(LIMITS):
                raise ValueError('备份文件名或结构无效')
            if any(info.file_size>LIMITS[info.filename] for info in z.infolist()):
                raise ValueError('备份解压后过大')
            files={name:z.read(name) for name in names}
        def invalid_constant(value):raise ValueError('备份包含非有限数值')
        manifest=json.loads(files.pop('manifest.json'),parse_constant=invalid_constant)
        if manifest.get('schema')!='puyigai-backup-v1' or set(manifest.get('files',{}))!=set(files):
            raise ValueError('备份清单无效')
        for name,data in files.items():
            if hashlib.sha256(data).hexdigest()!=manifest['files'][name]:raise ValueError('备份校验失败')
        project=json.loads(files['project.json'],parse_constant=invalid_constant)
        if not isinstance(project,dict):raise ValueError('备份项目格式无效')
        if project.get('audio_sha256'):
            if 'source.audio' not in files or hashlib.sha256(files['source.audio']).hexdigest()!=project['audio_sha256']:
                raise ValueError('备份缺失或不匹配原始上传音频')
        return project,files
    except (BadZipFile,KeyError,TypeError,UnicodeError,RuntimeError,json.JSONDecodeError) as exc:
        raise ValueError('无法读取有效项目备份') from exc
