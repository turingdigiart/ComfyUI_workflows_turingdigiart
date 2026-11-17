# tt-tripo｜机构自研 Tripo 文生/图生/多视图生 3D 调用节点（v0.2.1）

在 ComfyUI 里提交 Tripo API 文生/图生/多视图生 3D 任务并取回结果（GLB + 渲染预览图）。

## 版本

- **v0.2.1（2026-11-17）**：修复 T19 暴露的列表输入缺陷——现象：`TTTripoMultiviewTo3D` 经 API 图连 2 路 `images` 被 ComfyUI 校验拒绝（`unhashable type: 'list'`），多视图链路不可执行；根因：`images` 声明为单输入 `("IMAGE",)`，不能承载多路连接；修法：节点加 `INPUT_IS_LIST = True`（`/object_info` 暴露 `is_input_list: true`，前端允许多路连接），`run()` 对控件单值解包，`images` 归一为张量列表（2–4 张、front/left/back/right 顺序不变），单图连接向后兼容；边界：已知本机 ComfyUI 0.43 构建级缺陷——`/prompt` 列表链接校验对所有节点一律失败（详见仓库 `docs/DEV_EXPERIENCE.md`），API 图路径仍受该缺陷阻塞，UI 手工多路连接为当前可用路径；Key 存储与付费 P1 口径不变。
- **v0.2.0（2026-11-17）**：新增「图生 3D」与「多视图生 3D」（负责人指示）。现象（需求）：只有文生 3D 一个入口，图生与多视图能力缺失；根因：节点未覆盖 `POST /generation/image-to-model` 与 `/generation/multiview-to-model` 及前置 `/files` 上传；修法：新增共享 `_upload_image`（IMAGE→临时 PNG→multipart 上传→file_token，上传后清理）与节点 `TTTripoImageTo3D`（input=file_token；texture_alignment=original_image|geometry、orientation=default|align_image、enable_image_autofix）、`TTTripoMultiviewTo3D`（2–4 张视图，**连接顺序=front/left/back/right、第一张视为 front、front 必填**，inputs 用 view-key 格式 `[{"front":token},…]`），失败均把 `ERROR:<原因>` 写入 task_id 输出；边界：`TTTripoFetch` 通用不改、enable_api 默认关、不自动重试提交、Key 存储与付费 P1 口径不变；示例工作流 27/28。
- **v0.1.1（2026-11-17）**：修复 E2E 测试暴露的缺陷——现象：`/prompt` 直接使用两节点图报 `prompt_no_outputs`，且节点输出不进 `/history`，任务失败后无法取证；根因：两节点均非 `OUTPUT_NODE`、task_id 未持久化；修法：`TTTripoFetch` 设 `OUTPUT_NODE=True`（图以它收尾、输出进 `/history`），每次执行写 `output/Tripo/<task_id>.meta.json`（task_id/status/model_path/preview_path/error/ts），Submit 失败把 `ERROR:<原因>` 写入 task_id 输出供 Fetch 透传取证，预览图同步落盘 `output/Tripo/<task_id>_preview.png`；边界：兜底空白图逻辑保留、不自动重试提交、不改变 Key 存储与付费 P1 口径。
- **v0.1.0（2026-11-16）**：初版（T14a/T14b）。

## 节点

| 节点 | 用途 | 输入 | 输出 |
|---|---|---|---|
| `TTTripoSubmit` | 提交 `POST /generation/text-to-model` | enable_api（默认关）、prompt、model、negative_prompt、face_limit、texture、pbr、seed（0=不传 model_seed） | `task_id`(STRING)、`调用信息`(STRING) |
| `TTTripoImageTo3D` | 上传 `/files` 并提交 `POST /generation/image-to-model` | image（IMAGE 必连）、enable_api（默认关）、model、face_limit、texture、pbr、texture_alignment（original_image/geometry）、orientation（default/align_image）、enable_image_autofix | `task_id`(STRING)、`调用信息`(STRING) |
| `TTTripoMultiviewTo3D` | 2–4 张视图逐张上传并提交 `POST /generation/multiview-to-model`（view-key 格式） | images（IMAGE 列表 2–4，**连接顺序=front/left/back/right，第一张视为 front**）、enable_api（默认关）、model、face_limit、texture、pbr、orientation | `task_id`(STRING)、`调用信息`(STRING) |
| `TTTripoFetch` | 轮询 `GET /tasks/{task_id}` 并取回 | task_id（可连线/手工粘贴）、wait_seconds(600)、poll_interval(5)、refresh_id | `模型路径`(STRING，GLB 存 `output/Tripo/`)、`预览图`(IMAGE)、`状态`(STRING) |

## Key 管理（DEC-ORG-094「本机配置 + 中控只验证约束」）

- Key 值只存各机本机：插件目录 `tripo.local.json` 的 `api_key` 字段，或环境变量 `TRIPO_API_KEY`（环境变量优先）；**不入画布、不入同步盘、不发聊天**。
- 仓库内只有 `tripo.local.json.example`（api_key 留空）；`tripo.local.json` 已被 `.gitignore` 排除，不会进 Git。
- 开工前三项机器检查：插件目录存在；`tripo.local.json` 可读且 `api_key` 非空（或环境变量存在）；`/object_info` 注册 `TTTripoSubmit`/`TTTripoFetch`。任一缺失即提示负责人补齐。

## 付费与边界（P1）

- 每次真实生成消耗 Tripo 额度；付费调用属 P1，**每次生成前确认预算**，不沿用历史授权。
- `enable_api` **默认关闭**：先确认参数与预算，再打开，防误扣费。
- `TTTripoFetch` 只查询与下载，**不自动重试提交**（防止同一任务重复计费）；超时后用同一 task_id 再次取回即可。
- 任务查询路径已按官方文档核验：`GET {base_url}/tasks/{task_id}`（2026-11-16，developers.tripo3d.com 任务查询页；候选的 `/generation/task/{task_id}` 不成立）。Base URL 默认 `https://openapi.tripo3d.ai/v3`（2026-11-16 零费用余额连通实测：本机构 Key 在 .ai 实例返回 200/code 0，.com 实例返回 401/code 2），可在 `tripo.local.json` 覆盖。

## 与官方 ComfyUI-Tripo 的关系

官方 `ComfyUI-Tripo`（1.3.0，11 节点）仅作设计参考；本插件为机构**自研替代**：只保留文生/图生/多视图生 3D 提交与任务取回的最小节点集、Key 走 DEC-ORG-094 本机配置模式、enable_api 默认关、不自动重试提交。代码全部自写，不复制官方源码。

## 示例工作流

- `workflows/model3d/tripo/26_Tripo_文生3D.json`（MarkdownNote 使用说明 → TTTripoSubmit → TTTripoFetch → PreviewImage/PreviewAny）。
- `workflows/model3d/tripo/27_Tripo_图生3D.json`（LoadImage 参考图 → TTTripoImageTo3D → TTTripoFetch → PreviewImage/PreviewAny×2）。
- `workflows/model3d/tripo/28_Tripo_多视图生3D.json`（4×LoadImage 正面/左/背/右 → TTTripoMultiviewTo3D → TTTripoFetch → 同上三输出；连接顺序=front/left/back/right）。
