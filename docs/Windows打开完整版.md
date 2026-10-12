# Windows打开完整版

1. 下载“谱易改-春雨私有试用包.zip”，解压，不要直接在压缩包中运行。进入AIC目录。
2. 双击Start-Windows.cmd。它会检查Python3.12和ffmpeg，安装应用依赖、导入春雨案例并启动服务。第一次安装需要网络，运行窗口保持打开。
3. 如果提示缺少Python或ffmpeg，打开PowerShell执行相应安装命令：

```powershell
winget install --id Python.Python.3.12 -e
winget install --id Gyan.FFmpeg -e
```

只安装缺少的前提；安装完成后关闭旧窗口，再双击Start-Windows.cmd，以刷新PATH。若系统没有winget，不要反复重试；保留提示，改用官方Python3.12安装器和FFmpeg安装方式。

4. 窗口显示Uvicorn运行在8765端口之后，在同一台Windows机器上用Edge或Chrome打开 http://127.0.0.1:8765 。此地址是你正在运行网站的Windows机器，不能当作Codex云环境的在线预览链接。
5. 点“打开春雨试用案例”，即可真正试听、编辑音符、参考对照与导出。录音与编辑数据保存在解压目录下的var文件夹。Ctrl+C停止服务。

如果Windows是远程服务器，先通过远程桌面在服务器自身浏览器访问。其他电脑直接访问需要另外配置服务器地址、访问控制和网络入口；默认启动只监听本机，不会生成公共网址。

Windows双击脚本尚未在真实Windows设备上测试；Python启动流程及应用已在Linux验证。出现报错时把完整文字发回，不要把安装失败当作启动成功。

如果8000打开了正畸等其他项目，这是地址对应的服务不同。谱易改Windows启动入口改用8765；不要关闭其他项目。如果8765被占用，启动检查会明确报错，不会自动接管端口。
