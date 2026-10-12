"""PRIVATE user trial bundle; never include it in a public code/evidence release."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
root=Path(__file__).resolve().parents[1]
output=root/'artifacts/谱易改-春雨私有试用包.zip'
with ZipFile(output,'w',ZIP_DEFLATED) as target:
    with ZipFile(root/'artifacts/谱易改-开发包.zip') as source:
        for name in source.namelist():target.writestr(name,source.read(name))
    for file in (root/'var/demo-import').iterdir():
        if file.is_file():target.write(file,'AIC/var/demo-import/'+file.name)
    target.write(root/'artifacts/谱易改-技术方案审核稿.pdf','AIC/审核材料/技术方案审核稿.pdf')
    target.write(root/'artifacts/谱易改-答辩审核稿.pdf','AIC/审核材料/答辩审核稿.pdf')
    target.write(root/'artifacts/谱易改-研发验证佐证审核稿.pdf','AIC/审核材料/研发验证佐证审核稿.pdf')
    target.writestr('AIC/先读-怎么运行.txt',
        '这是你的私有试用包，含本人演奏春雨录音，不作为公开代码包或公开数据集。\n'
        '解压后进入AIC文件夹。需要Python3.12和ffmpeg；安装方法见README.md。\n'
        'Windows优先双击Start-Windows.cmd，启动后浏览器打开本机8765端口。\n也可在PowerShell手动运行：\npy -3.12 scripts/install.py\n'
        '.\\.venv\\Scripts\\python.exe scripts\\import_practice_demo.py\n'
        '$env:AIC_PORT=\"8765\"\n.\\.venv\\Scripts\\python.exe scripts\\start.py\n'
        '在Linux服务器运行：\npython3 scripts/install.py\n'
        '.venv/bin/python scripts/import_practice_demo.py\n.venv/bin/python scripts/start.py\n'
        'Windows浏览器打开本机服务8765端口（上述Linux默认启动方式为8000），点击“打开春雨试用案例”。\n'
        '不需要自己制作MIDI或填写CSV。先听录音，再点差异定位原音。\n'
        '参考草稿的八度、时值尚未核实；自动对齐来自模型初稿，起音/时长不评定。\n'
        '不要把待核对的差异当作演奏错误或模型准确率。')
with ZipFile(output) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(set(z.namelist()))
print(output,output.stat().st_size,'bytes')
