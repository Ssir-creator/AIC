"""Single-command private trial startup; --check makes no configuration changes."""
import argparse
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description='安装依赖、导入私有案例并启动谱易改')
parser.add_argument('--check',action='store_true',help='仅检查当前运行前提，不安装、不启动')
parser.add_argument('--port',type=int,default=8765,help='网站端口，默认8765以避开其他项目')
args=parser.parse_args()
if not 1024<=args.port<=65535:
    raise SystemExit('端口须为1024—65535。')
host=os.environ.get('AIC_HOST','127.0.0.1')
try:
    with socket.create_server((host,args.port)):
        pass
except OSError as exc:
    raise SystemExit(f'无法使用{host}:{args.port}：{exc}。不会停止其他项目；请用--port选择其他端口。')
if sys.version_info[:2]!=(3,12):
    raise SystemExit('需要Python 3.12。Linux请用python3.12运行；Windows请用py -3.12运行。')
if not shutil.which('ffmpeg'):
    raise SystemExit('当前系统未找到ffmpeg。请先安装并加入PATH；安装命令需按服务器系统确定。')
python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
if not args.check:
    subprocess.run([sys.executable,str(root/'scripts/install.py')],cwd=root,check=True)
if not python.is_file():
    raise SystemExit('尚未安装应用依赖；不带--check运行可完成安装。')
subprocess.run([str(python),'-c',"from app import get_model; print('官方ONNX模型可加载:', get_model().model_type)"],cwd=root,check=True)
if args.check:
    print('运行前提检查通过；未安装、导入案例或启动服务。')
    raise SystemExit(0)
if (root/'var/demo-import/project.json').is_file():
    subprocess.run([str(python),str(root/'scripts/import_practice_demo.py')],cwd=root,check=True)
print(f'启动谱易改，地址：http://{host}:{args.port} 。终端保持运行，Ctrl+C停止。',flush=True)
environment=os.environ.copy()
environment['AIC_PORT']=str(args.port)
subprocess.run([str(python),str(root/'scripts/start.py')],cwd=root,env=environment,check=True)
