"""Optional single-user HTTP Basic gate behind the host's HTTPS endpoint."""
import base64
import binascii
import os
import secrets
from starlette.responses import JSONResponse

async def access_gate(request,call_next):
    password=os.environ.get('AIC_ACCESS_PASSWORD','')
    required=os.environ.get('AIC_REQUIRE_AUTH')=='1'
    if required and len(password)<16:
        return JSONResponse({'detail':'线上访问保护尚未配置，服务暂不可用'},status_code=503)
    if not password:
        return await call_next(request)
    if request.url.path=='/api/health':
        return await call_next(request)
    header=request.headers.get('authorization','')
    valid=False
    try:
        scheme,value=header.split(' ',1)
        if scheme.lower()=='basic' and len(value)<=2048:
            login,supplied=base64.b64decode(value,validate=True).split(b':',1)
            valid=secrets.compare_digest(login,os.environ.get('AIC_ACCESS_USER','aic').encode())
            valid=secrets.compare_digest(supplied,password.encode()) and valid
    except (ValueError,binascii.Error):
        pass
    if not valid:
        return JSONResponse({'detail':'请登录后使用谱易改'},status_code=401,
                            headers={'WWW-Authenticate':'Basic realm="PuYiGai", charset="UTF-8"'})
    return await call_next(request)
