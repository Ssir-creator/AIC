from pathlib import Path
import sys,tempfile,time,json,base64,io,csv,platform,statistics
import numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[2]));import app
out=Path(__file__).resolve().parent;out.mkdir(exist_ok=True)
f='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
def make(i):
 rng=np.random.default_rng(20261015+i);pal=[('#EEE4D2','#245047'),('#E9E7EF','#51406B'),('#E8EDF2','#2C4659')][i%3]
 im=Image.new('RGB',(640,640),pal[0]);d=ImageDraw.Draw(im)
 d.text((40,35),['咖啡新品','文创礼盒','春日家居'][i%3],font=ImageFont.truetype(f,39),fill=pal[1]);d.text((42,98),f'DESIGN SAMPLE {i:02d}',font=ImageFont.truetype(f,17),fill=pal[1])
 for j in range(6):
  x,y=rng.integers(80,500,2);w,h=rng.integers(40,130,2);col=tuple(int(k) for k in rng.integers(70,220,3));d.rounded_rectangle((int(x),int(y),int(x+w),int(y+h)),radius=10,fill=col)
 d.text((40,574),'原创设计测试样张 · 非商户实拍',font=ImageFont.truetype(f,18),fill=pal[1]);return im

def encode(im):
 b=io.BytesIO();im.save(b,format='PNG');return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
rows=[];quality=[];times=[];n=24
with tempfile.TemporaryDirectory() as td:
 app.DATA=Path(td);records=[]
 for i in range(n):
  im=make(i);start=time.perf_counter();r=app.handle('watermark',{'image':encode(im),'method':'builtin','owner':'演示设计组','title':f'试验样张{i:02d}'})
  times.append(time.perf_counter()-start);marked=Image.open(app.DATA/(r['id']+'.png')).convert('RGB');mse=float(np.mean((np.asarray(im,dtype=float)-np.asarray(marked,dtype=float))**2));quality.append(10*np.log10(255**2/mse));records.append((r,marked.copy()))
  if i<3:im.save(out/f'case-{i}-before.png');marked.save(out/f'case-{i}-after.png')
 print('generated',n,flush=True)
 for op in ['original','jpeg90','jpeg50','resize50','crop70']:
  for i,(r,marked) in enumerate(records):
   trial=app.transform(marked,op);t=time.perf_counter();res=app.handle('trace',{'image':encode(trial)});elapsed=time.perf_counter()-t
   correct=res['state']=='matched' and res['record']['id']==r['id'];rows.append({'sample':i,'operation':op,'state':res['state'],'correct':int(correct),'seconds':round(elapsed,5)})
  print(op,sum(x['correct'] for x in rows if x['operation']==op),flush=True)
 for i in range(n):
  t=time.perf_counter();res=app.handle('trace',{'image':encode(make(100+i))});rows.append({'sample':i,'operation':'negative','state':res['state'],'correct':int(res['state']=='unmatched'),'seconds':round(time.perf_counter()-t,5)})
summary={'date':'2026-10-15','method':'内置轻量水印（非球形水印）','dataset':'24张程序自绘640×640设计样张，3类布局；另24张无水印负样张','hardware':platform.machine(),'n_positive':n,'n_negative':n,'quality_psnr_mean':round(statistics.mean(quality),2),'embed_seconds_median':round(statistics.median(times),4),'conditions':{}}
for op in ['original','jpeg90','jpeg50','resize50','crop70','negative']:
 rr=[r for r in rows if r['operation']==op];summary['conditions'][op]={'correct':sum(r['correct'] for r in rr),'n':len(rr),'median_seconds':round(statistics.median(r['seconds'] for r in rr),4),'states':{s:sum(r['state']==s for r in rr) for s in ['matched','unmatched','ambiguous']}}
summary['limitations']=['受控软件试验，不是商户试点或用户调研','仅内置轻量方法，不是球形水印/TrustMark的模型性能','单进程小样本，不能推断大规模误检率或GPU速度','耗时包含本地编码、磁盘与登记遍历，不含公网延时']
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
with (out/'raw-results.csv').open('w') as fh:
 wr=csv.DictWriter(fh,fieldnames=rows[0].keys());wr.writeheader();wr.writerows(rows)
print(json.dumps(summary,ensure_ascii=False,indent=2))
