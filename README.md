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

## 验证

```bash
python -m unittest -v
```

测试覆盖图片处理、内置水印嵌入与检测、传播变换、记录持久化和错误语义。
