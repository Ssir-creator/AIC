# AI+场景创新 · 源代码说明

一、作品与交付信息

作品名称：图溯

参赛赛题：赛题4 · AI+场景创新

参赛团队编号：AIC-2026-95418058

整理日期：2026年10月20日；程序版本：2026.10.20.2

源码基线：Ssir-creator/AIC，preview/enterprise-ui，提交 a3ca29a

材料用途：配套源码与运行包的交付说明。原模板标注AC1算法模型创新，本材料按已确定的AI+场景创新整理；提交前请确认系统实际栏目。

二、源代码交付内容

源代码包包含Python服务、原生网页界面、账户与密钥管理、图片处理、研究模型适配器、测试、配置示例和启动脚本。未包含账号数据库、会话、真实API密钥、历史业务图片、私人水印密钥或模型权重。

交付文件：按团队编号统一命名的源代码ZIP压缩包。包内提供Windows启动脚本start.bat和Linux/macOS启动脚本start.sh；Windows脚本仍需预装Python。

源码项目地址：https://github.com/Ssir-creator/AIC/tree/preview/enterprise-ui

百度网盘分享链接：待上传后填写；提取码：待填。不得将示例地址作为有效分享链接。

三、统一命名

网盘文件夹：AIC-2026-95418058-AI+场景创新-图溯-源代码。压缩包及内部目录均已按该名称统一命名。作品名称为“图溯”。

四、目录结构与文件职责

app.py                  HTTP接口、任务执行、图片处理和来源核验
service_store.py        账户、会话、密钥摘要、日志及SQLite存储
model_worker.py         独立模型环境的JSON调用适配器
index.html              页面结构与业务入口
assets/app.js           交互、异步任务、批量操作和报告下载
assets/app.css          网页样式
assets/fonts/           字体与许可
assets/demo/            实际操作录屏、配音、字幕和验证数据
config.example.json     模型路径配置示例，不含私密密钥
requirements-core.txt   本地演示所需Pillow与NumPy
requirements.txt        扩展模型依赖参考
test_app.py             图像流程与模型协议回归测试
test_service.py         身份、权限隔离、公开脱敏与接口测试
start.bat / start.sh    Python版便捷启动脚本
README.md               完整原型说明与当前限制

五、技术结构

界面层使用HTML/CSS/JavaScript，无需前端编译。业务层使用Python标准库HTTP服务，异步任务提交后轮询结果。数据层使用SQLite保存账户及请求日志，工作空间目录保存图片和来源JSON记录。模型层通过独立Python进程接入已有研究环境。

核心链路：上传或描述图片 → 标识处理 → 来源登记及业务关联 → 下载交付 → 上传待查图片 → 提取与匹配 → 返回允许公开的来源信息及报告。

六、球形水印与实现范围

主研究方法为球形水印：通过论文环境中的SphericalCodes和扩散模型封装在生成过程中嵌入消息，再对待查图反演、提取恢复消息，关联本服务登记记录。model_worker.py提供调用适配，不是上游论文算法完整源码。

完整球形水印运行需另备上游代码、Stable Diffusion本地权重、可信本地签名/密钥文件、相容的Python依赖和CUDA设备。当前交付环境未配置上述资源，未验证真实球形推理或论文效果；生成入口不会伪造成功结果。

内置轻量水印可在CPU完成真实嵌入与核验，仅用于流程演示。TrustMark是辅助已有图片的路径，PRC仅保留研究接口，均不等同于球形水印。

七、复现与验证

python -m pip install -r requirements-core.txt
python app.py --host 127.0.0.1 --port 8765
python -m unittest -v

浏览器打开http://127.0.0.1:8765，首次创建工作空间。已在Python 3.12验证22项自动化测试通过，覆盖图像流程、隔离、密钥撤销、公开脱敏、任务归属和错误处理。模型夹具只验证调用协议。

八、参考与边界

第三方许可说明见THIRD_PARTY_NOTICES.txt及字体许可。球形论文方法与项目适配层分别说明；上游代码、模型和论文成果不作为本项目原创。来源匹配仅提供身份线索，不能自动证明内容真实、版权归属或有效授权。