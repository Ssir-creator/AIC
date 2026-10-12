"""Private, offline source-only listening tool with no predicted notes."""
import base64,hashlib,json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
root=Path(__file__).resolve().parents[1]
out=root/'artifacts/独立听音核对';out.mkdir(exist_ok=True)
inputs=[]
for i,title in enumerate(['春雨','新翻羽调绿腰','彝族舞曲']):
    audio=(root/f'artifacts/pipa-diagnostic-20261011/{i:02d}/first-30s.wav').read_bytes()
    inputs.append({'id':f'pipa-{i:02d}','title':title,'duration':30,
                   'sha256':hashlib.sha256(audio).hexdigest(),
                   'audio':'data:audio/wav;base64,'+base64.b64encode(audio).decode()})
template=(root/'review_tool/index.html').read_text()
(out/'打开这个页面.html').write_text(template.replace('__INPUTS__',json.dumps(inputs,ensure_ascii=False)),encoding='utf-8')
(out/'先读说明.txt').write_text('这是私有核对包，含本人演奏三首琵琶曲前30秒，不可自动公开传播。\n解压后用Edge或Chrome双击HTML；无需安装Python、服务器或联网。\n请未看模型结果的识谱者结合已提供谱页和原音独立核对。页面无模型提示。\n先只核对春雨开头一小段即可：暂停后记录开始/结束，选绝对音高，添加音符。\n不确定就选待确认，不要猜；关闭前保存JSON。\n独立且完整核对范围后可导出CSV及配套JSON，两份都交回。\n页面不自动保证音高/时间正确；模型评测须按核对范围裁剪，不用部分标注测整段准确率。\n谱页没有嵌入，请参赛者私下提供已有谱页。')
output=root/'artifacts/谱易改-独立听音核对包.zip'
with ZipFile(output,'w',ZIP_DEFLATED) as z:
    for p in out.iterdir():
        if p.suffix in ('.html','.txt'):z.write(p,p.name)
with ZipFile(output) as z:assert z.testzip() is None
print(output,output.stat().st_size,'bytes')
