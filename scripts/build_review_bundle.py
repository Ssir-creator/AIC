"""Bundle current review drafts; recordings make this a private review artifact."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
root=Path(__file__).resolve().parents[1]
files=['谱易改-技术方案审核稿.pdf','谱易改-答辩审核稿.pdf',
       '谱易改-研发验证佐证审核稿.pdf','谱易改-竞品文档核查审核稿.pdf',
       '谱易改-演示审核稿.mp4','提交材料机械检查.json']
output=root/'artifacts/谱易改-审核材料合集.zip'
with ZipFile(output,'w',ZIP_DEFLATED) as z:
    for name in files:z.write(root/'artifacts'/name,name)
    z.write(root/'docs/作品简介.txt','作品简介.txt')
    z.writestr('先读说明.txt','研发审核稿，尚未提交。视频含本人演奏录音，仅供私有审核。\n'
        '视频录制时为51项测试，本轮新增独立标注验证后为56项测试；不是音乐效果指标。\n'
        '竞品仅核查上游文档，未安装比较，不宣称精度或效率胜出。\n'
        '参考八度与节奏待确认，演示编辑不等于纠错效果。\n'
        '仍需官方模板、匿名复查、参赛编号、真实试用和独立效果验证。')
with ZipFile(output) as z:assert z.testzip() is None
print(output,output.stat().st_size,'bytes')
