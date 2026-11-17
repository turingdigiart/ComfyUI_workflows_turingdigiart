# 火山方舟 Seedream / Seedance 插件 1.0.0

> 源码母版：本仓库 `nodes/comfyui-ark-media/`（`turingdigiart/ComfyUI_workflows_turingdigiart`）。运行时加载自便携版 `custom_nodes/comfyui-ark-media`（可为 junction 或安装副本），本仓是源、运行时不复制正文。

本插件直接使用用户自己的 **火山方舟 API Key 和额度**。不是 Comfy Partner Nodes，不消耗 Comfy 积分。所有图片/视频生成在火山云端进行，参考图及提示词会发往火山方舟。

现有 ComfyUI 环境即可运行：HTTP客户端仅用Python标准库；图片、视频处理使用ComfyUI已有的Pillow、NumPy、Torch、PyAV。不安装新依赖，不替换CUDA。

## 你需要准备的内容

1. 登录[火山方舟控制台](https://ark.volcengine.com/region:cn-beijing)，完成账户要求。
2. 在API Key管理页面创建 **方舟 API Key**，不是火山账号的AccessKey/SecretKey。
3. 在模型管理中开通Seedream与Seedance，并确认账户有可用额度。开通条件/计费以控制台为准；创建Key不等于已开通模型。
4. 在本机 `ComfyUI_windows_portable/ComfyUI/custom_nodes/comfyui-ark-media/ark.local.json` 中填 `api_key`，不要发到聊天或粘到工作流。
5. `seedream_model` / `seedance_model` 填账户已开通的Model ID或Endpoint ID。节点的model留空时使用此配置。
6. 刷新ComfyUI页面，打开18或19；确认参数后将提交节点的 `enable_api` 打开，再运行。默认关闭，所以刚导入不会自动产生费用。

```json
{
  "base_url": "https://ark.cn-beijing.volces.com/api/v3",
  "api_key_env": "ARK_API_KEY",
  "api_key": "在本地这里填写",
  "proxy": "system",
  "seedream_model": "doubao-seedream-5-0-flash-260915",
  "seedance_model": "doubao-seedance-2-5-260628",
  "request_timeout": 180,
  "poll_interval": 5
}
```

上述默认模型于 2026-11-16 实机验证可用（聊天 `doubao-seed-2-1-pro-260915`、`doubao-seedream-5-0-flash-260915` / `doubao-seedream-5-5-261028` 同步生图、`doubao-seedance-2-5-260628` 视频任务）；其他模型不代表账户一定有调用权限。`ARK_API_KEY` 环境变量若非空则优先使用；更新系统环境变量后需重启ComfyUI。直接修改本地JSON无需重启。`COMFY_ARK_CONFIG` 可指向另一个私密配置文件。

proxy支持 `system`（环境变量/Windows代理）、`direct`、指定HTTP代理地址。普通使用不要开启 `allow_local_test`；该字段仅供本机模拟测试。

## 节点和工作流

| 节点 | 能力 |
|---|---|
| 火山方舟 Seedream 图片 | 文生图、单张或批量参考图编辑，返回IMAGE，可连SaveImage |
| 火山方舟 Seedance 提交任务 | 文生视频、首帧/首尾帧、参考图生视频，返回任务ID |
| 火山方舟 Seedance 获取视频 | 查询已有任务、等待完成、下载，返回原生VIDEO，可连SaveVideo并保留音轨 |

示例工作流在本仓库 `workflows/`（ComfyUI 用户工作流目录已 junction 到本仓库）：

- **18_方舟Seedream_机器人改图**（`workflows/image/ark/`）：参考机器人 → Seedream → 本地保存。移除参考图连接可文生图。
- **19_方舟Seedance_机器人图生视频**（`workflows/video/ark/`）：参考机器人 → 创建5秒720p有声视频 → 显示任务ID → 获取 → 保存。
- **20_方舟Seedance_已有任务取回**（`workflows/video/ark/`）：填控制台或之前返回的任务ID，恢复下载；不创建新生成任务。
- **21_方舟Seedance_文生视频**（`workflows/video/ark/`）：纯文字 → 5秒720p有声视频。
- **25_方舟Seedream_写实IP三视图_表情_细节**（`workflows/image/ark/`）：参考图 → 三视图/表情/细节关联图。

结果保存至 `output/Ark/`。已有通用提示词节点可把STRING输出接到本插件的prompt输入。把Seedream图片输出接到Seedance参考图输入即可串联，但会分别产生图片和视频调用费用。

Seedream默认单图2K。size也可填模型支持的4K或具体宽高。不同版本的分辨率/计费限制不同。参考图最多10张，批量IMAGE必须能被上游节点组成同尺寸批次。本版不做多图输出/图层拆分。

Seedance默认5秒、720p、有声音；首帧模式必须一张首帧，可接一张尾帧，自动使用adaptive比例。reference_images模式支持1～9张参考图；text模式需要断开图片。当前UI范围为2.0/2.5的常用参数；不含参考音视频输入、视频编辑、延长或Draft转正式视频功能。不同版本和Endpoint的限制最终由平台验证。

平台的内容/人物素材要求以官方文档为准。例如Seedance对真人肖像有单独的授权素材流程；本示例使用机器人，不提供绕过方式。

## 避免重复创建任务

付费POST不会自动重试。相同账户、节点ID、请求内容和refresh_id，会使用本地提交记录；关闭重开ComfyUI也可复用。想明确生成一个新结果才增加 `refresh_id`。修改提示词、模型、尺寸、参考图或节点ID也会形成新请求。

视频ID收到后立即持久保存。获取节点超时或本地停止时，云端可能仍在运行；再次运行原流程会复用已有ID。也可用工作流20单独取回。**停止ComfyUI并不取消云端任务或撤销费用。** 本版不提供云端取消按钮。

如果POST超时、报错或程序意外退出，记录可能处于“提交未确认”状态，插件会阻止同请求自动重发。先到方舟控制台核对任务/账单；找到任务ID用20恢复。确认需要重试后再增加refresh_id。成功响应后的磁盘写入失败也可能产生这种状态。此机制是本地防重复，不是服务端严格幂等保证。

私有缓存位于 ComfyUI `user/ark-media-private/`，包含任务回执、图片/视频和可能尚未过期的签名URL，**不要公开或打包**。不存API Key或原始参考图请求体。保留此目录有助于跨重启恢复；删除它后同请求可能重新计费。云端任务及结果URL有有效期，完成后及时保存。长期输出请使用SaveImage/SaveVideo，不依赖私有缓存。

## 安装、迁移和开发

将插件文件夹复制到目标ComfyUI的custom_nodes并重启，或在源码目录执行：

```powershell
python manage.py install --comfy "D:\ComfyUI"
python -m unittest discover -s tests -v
python manage.py package --output "D:\releases\comfyui-ark-media-1.0.0.zip"
```

工程源码母版在本仓库 `nodes/comfyui-ark-media/`，部署副本在便携版custom_nodes（可为 junction 指向本仓库，或 manage.py 安装副本）；安装保留已有ark.local.json。迁移时密钥单独安全配置，发布包不含Key和运行缓存。支持当前ComfyUI的原生VIDEO类型，较旧版本可能需升级。

v1.0.3 起 `ArkSeedream` 的 `reference_images` 为**单输入承载图像批次**：多参考图用 ComfyUI 自带 `ImageBatch` 节点串联成单链接入（3 张参考 = 2 个 ImageBatch），请勿多路直连该输入。**机器 B 若为 `manage.py install` 安装副本，需重新执行 `manage.py install` 后生效；本机 junction 指向仓库母版即时生效，无需重装**。

`tools/create_workflows.py --project-root <工程目录>` 从运行中后台节点schema生成示例。`tools/smoke_test.py --project-root <工程目录>` 使用本机模拟API及已有机器人/LTX样例测试，期间临时替换部署配置，finally恢复。请仅在队列空闲、无人编辑配置时运行；异常断电后检查配置文件。它不会发起真实方舟调用。

目前验证的是请求结构和本机集成；真实平台认证、账户额度、生成质量，需用户配置Key后验证。模拟视频/图片为原有样例回放，不是Seed模型生成结果。

## 官方接口依据

- [图片生成API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)
- [视频任务创建API](https://ark.volcengine.com/region:cn-beijing/docs/create-video-generation-task-api)
- [Seedance 2.5 使用说明](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh)

接口：`POST /images/generations`、`POST /contents/generations/tasks`、`GET /contents/generations/tasks/{id}`，基址为配置中的 `/api/v3`。
