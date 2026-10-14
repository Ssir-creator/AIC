# 图溯——AIGC电商素材可信流转

面向品牌方、电商运营和设计服务团队，为营销图片嵌入匿名来源标识，并在图片经过压缩、缩放或裁剪后重新核验来源线索。

## 本地启动

```bash
python -m pip install -r requirements.txt
python app.py --host 0.0.0.0 --port 8765
```

打开 `http://127.0.0.1:8765`。

内置轻量水印、可见署名、图片压缩、缩放、裁剪、来源核验和 CSV 导出可直接使用。TrustMark、PRC 与球形水印需要按 `config.example.json` 配置已有论文模型环境。

## Render 部署

仓库根目录包含 `render.yaml`。Render 会安装 Pillow 和 NumPy，运行 `app.py`，并通过 `/health` 检查服务状态。

## Codespaces 在线预览

在 GitHub 仓库点击 **Code → Codespaces → Create codespace on main**。容器会自动安装依赖、运行测试、启动端口 8765，并在浏览器打开完整功能预览，无需本地下载或绑定银行卡。

## 验证

### 轻量AI生图

图片保护页支持 `segmind/tiny-sd` 的CPU文生图，生成512×512配图后按所选方式添加水印。首次使用从Hugging Face下载模型；需要足够内存、磁盘和网络，CPU耗时取决于机器配置。默认15步，建议英文描述。模型安全检查保留。该入口不是PRC或球形水印的复现，不能据此报告论文实验成绩。

若生图依赖未安装，在Codespaces执行 `bash .devcontainer/update-preview.sh`。原生论文路线仍需独立配置。当前Codex环境无法访问Hugging Face，实际模型推理尚未在该环境验证；生成—保护—登记—溯源链路通过测试夹具验证。

```bash
python -m unittest -v
```

测试覆盖图片处理、内置水印嵌入与检测、传播变换、记录持久化和错误语义。
