# tt-tripo｜机构自研 Tripo 文生/图生/多视图生/重拓扑/SmartUV/格式转换 3D 调用节点（v0.4.0）

在 ComfyUI 里提交 Tripo API 文生/图生/多视图生 3D 任务、做重拓扑（带 UV）/SmartUV/格式转换并取回结果（GLB/FBX/OBJ… + 渲染预览图）。

## 版本

- **v0.4.0（2026-11-17）**：成本可控的「生成→拓扑/UV→转换→取回」管线与「已有模型优化」管线（负责人三点要求：保留 26/27/28/29 粗糙管线不动；新管线从生成到拓扑 UV，可选重拓扑/转换/SmartUV 控制消耗；已有模型可单独跑重拓扑(带UV)/转换/SmartUV）。现象：生成接口不含拓扑/UV 优化，重拓扑/SmartUV/转换均独立计费，成本叠加不可控；根因：插件缺少 Retopo/SmartUV 节点且 Convert 的 enable_api=false 会报错、无法串成可跳过的阶段链；修法：新增 `TTTripoRetopo`（`POST /v3/mesh/decimate`：model v3.0/v2.0/v1.0、face_limit>0 才传、quad、smart_uv 仅 v3.0 有效（v1/v2+true 客户端拦截）、bake v1.0 不传）与 `TTTripoSmartUV`（`POST /v3/mesh/uv`：bake、export_orientation 非默认才传、compress=geometry 才传；输入 ≤8 万等效三角面）；**阶段开关语义**：Retopo/SmartUV/Convert 的 enable_api=false 时**不联网、原样透传 task_id、不报错**（调用信息注明「已跳过」），true 才提交付费任务；Fetch 不变（沿用 v0.3.1 重试 + v0.3.2 扩展名/zip 逻辑）；示例工作流 30/31。边界：26/27/28/29 模板与既有节点行为不变；成本口径写进节点调用信息与模板说明卡（生成 30；重拓扑 v3.0 35 / quad 40；SmartUV 20；转换 5 credits）。
- **v0.3.2（2026-11-17）**：修复 T24 暴露的两个缺陷——现象：①28t 多视图经 ImageBatch 后 `_upload_image` 收到 3D 切片（H,W,C）仍按 4D 取 `tensor[0]`，PIL 报 `Invalid mode for data type`、任务零扣费失败；②OBJ 转换产物实为 ZIP（obj+mtl+贴图），URL 后缀不在已知列表→按 .glb 落盘、meta format 记录错误；③ERROR 透传的 meta 文件名含 ASCII 冒号被写入 NTFS 备用流（0 字节 ERROR 文件）。根因：上传函数假设 4D；扩展名推断无内容嗅探；取证文件名未清洗。修法：`_upload_image` 兼容 3D/4D 输入；下载后 URL 后缀未知时**嗅探文件头**（`PK\x03\x04`→存 `.zip` 并解包到 `<task_id>_<format>/`，meta 记 `archive=true`、`format`（优先任务回显的 input.format）、`files` 清单、解包目录）；meta 文件名非法字符清洗为 `_`。边界：非 zip 仍按既有扩展名逻辑；提交接口不重试口径不变。
- **v0.3.1（2026-11-17）**：轮询与下载的网络抖动韧性修复——现象：负责人 16:19 的生成任务已在 Tripo 侧 success，但 Fetch 轮询遇本机系统代理瞬时断连（ProxyError/RemoteDisconnected）直接报错，已成功任务被当成失败丢弃；根因：查询与下载均无重试、无断点续传；修法：`TTTripoFetch` 查询任务状态对**网络类异常**（连接错误/超时/代理故障/流中断）做有界重试（最多 3 次、指数退避 2/4/8 秒、期间可中断），任务终态与业务错误不重试；GLB/预览下载同样有界重试并支持 **HTTP Range 断点续传**（从 .part 已下载字节继续，校验最终大小与 Content-Length 一致，不一致重试）；meta.json 新增 `retries`/`recovered` 字段（现有字段兼容）；边界：**提交接口绝不重试**（提交仍单次，防重复计费），HTTP 状态错误与业务错误不重试。
- **v0.3.0（2026-11-17）**：新增「格式转换」节点（负责人指示「返回 obj 或 fbx 模型，这很重要」）。现象：生成接口固定输出 GLB，交付 FBX/OBJ 需手工转换；根因：插件未覆盖 `POST /models/convert`；修法：新增 `TTTripoConvert`（task_id 可粘贴/连线，format=FBX/OBJ/GLTF/USDZ/STL/3MF，quad、face_limit(0=不传)、texture_size，异步返回新 task_id 交给 `TTTripoFetch` 轮询），`TTTripoFetch` 下载扩展名从 `output.model_url` URL 后缀推断（.fbx/.obj/.glb/.gltf/.stl/.3mf/.usdz，无法推断回退 .glb），meta.json 新增 `ext/format` 字段；边界：OBJ 无动画、STL/3MF 仅几何、quad=true 强制输出 FBX（且未设 face_limit 时平台默认 1 万面）；Key 存储与付费 P1 口径不变；示例工作流 29。
- **v0.2.2（2026-11-17）**：紧急回退 T20 的列表输入方案——现象：`INPUT_IS_LIST=True` 使 ComfyUI 0.43 前端把 `TTTripoMultiviewTo3D` 全部控件（enable_api/model/…）渲染成不可交互输入槽，用户无法勾选 enable_api；根因：`INPUT_IS_LIST` 是整节点列表化语义，且本构建 `/prompt` 列表链接校验对所有节点失败；修法：删除 `INPUT_IS_LIST`，`images` 恢复**单 IMAGE 输入承载图像批次**（`(B,H,W,C)` 按 batch 维拆分，batch 顺序=front/left/back/right），多图用 ComfyUI 自带 `ImageBatch` 串联成单链输入（4 张 = 3 个 ImageBatch），API/UI 两条路径可用；边界：多图必须经 ImageBatch 单链入 `images`，直接多路连线仍会被校验拒绝；Key 存储与付费 P1 口径不变。
- **v0.2.1（2026-11-17）**：修复 T19 暴露的列表输入缺陷（`INPUT_IS_LIST=True` 方案）——已被 v0.2.2 回退，仅作历史记录。
- **v0.2.0（2026-11-17）**：新增「图生 3D」与「多视图生 3D」（负责人指示）。现象（需求）：只有文生 3D 一个入口，图生与多视图能力缺失；根因：节点未覆盖 `POST /generation/image-to-model` 与 `/generation/multiview-to-model` 及前置 `/files` 上传；修法：新增共享 `_upload_image`（IMAGE→临时 PNG→multipart 上传→file_token，上传后清理）与节点 `TTTripoImageTo3D`（input=file_token；texture_alignment=original_image|geometry、orientation=default|align_image、enable_image_autofix）、`TTTripoMultiviewTo3D`（2–4 张视图，**连接顺序=front/left/back/right、第一张视为 front、front 必填**，inputs 用 view-key 格式 `[{"front":token},…]`），失败均把 `ERROR:<原因>` 写入 task_id 输出；边界：`TTTripoFetch` 通用不改、enable_api 默认关、不自动重试提交、Key 存储与付费 P1 口径不变；示例工作流 27/28。
- **v0.1.1（2026-11-17）**：修复 E2E 测试暴露的缺陷——现象：`/prompt` 直接使用两节点图报 `prompt_no_outputs`，且节点输出不进 `/history`，任务失败后无法取证；根因：两节点均非 `OUTPUT_NODE`、task_id 未持久化；修法：`TTTripoFetch` 设 `OUTPUT_NODE=True`（图以它收尾、输出进 `/history`），每次执行写 `output/Tripo/<task_id>.meta.json`（task_id/status/model_path/preview_path/error/ts），Submit 失败把 `ERROR:<原因>` 写入 task_id 输出供 Fetch 透传取证，预览图同步落盘 `output/Tripo/<task_id>_preview.png`；边界：兜底空白图逻辑保留、不自动重试提交、不改变 Key 存储与付费 P1 口径。
- **v0.1.0（2026-11-16）**：初版（T14a/T14b）。

## 节点

| 节点 | 用途 | 输入 | 输出 |
|---|---|---|---|
| `TTTripoSubmit` | 提交 `POST /generation/text-to-model` | enable_api（默认关）、prompt、model、negative_prompt、face_limit、texture、pbr、seed（0=不传 model_seed） | `task_id`(STRING)、`调用信息`(STRING) |
| `TTTripoImageTo3D` | 上传 `/files` 并提交 `POST /generation/image-to-model` | image（IMAGE 必连）、enable_api（默认关）、model、face_limit、texture、pbr、texture_alignment（original_image/geometry）、orientation（default/align_image）、enable_image_autofix | `task_id`(STRING)、`调用信息`(STRING) |
| `TTTripoMultiviewTo3D` | 2–4 张视图逐张上传并提交 `POST /generation/multiview-to-model`（view-key 格式） | images（IMAGE 单输入承载 batch 2–4，**batch 顺序=front/left/back/right，第一张视为 front**，多图用 ImageBatch 串联）、enable_api（默认关）、model、face_limit、texture、pbr、orientation | `task_id`(STRING)、`调用信息`(STRING) |
| `TTTripoRetopo` | 重拓扑（可带 UV）：`POST /v3/mesh/decimate`（**阶段开关**：enable_api=false 时透传跳过不报错） | task_id（粘贴/连线）、enable_api（默认关）、model（v3.0/v2.0/v1.0）、face_limit（默认 10000，0=不传）、quad（true 约 40 credits）、smart_uv（仅 v3.0 有效）、bake（v1.0 不传） | `task_id`(STRING，新任务 ID；跳过时=透传)、`调用信息`(STRING) |
| `TTTripoSmartUV` | SmartUV：`POST /v3/mesh/uv`（**阶段开关**；输入 ≤8 万等效三角面） | task_id、enable_api（默认关）、bake(true)、export_orientation（默认(不传)/+x/-x/+y/-y）、compress（无/geometry） | `task_id`(STRING，新任务 ID；跳过时=透传)、`调用信息`(STRING) |
| `TTTripoConvert` | 提交 `POST /models/convert` 把已有生成任务转为 FBX/OBJ/GLTF/USDZ/STL/3MF（异步；**阶段开关**：enable_api=false 时透传跳过不报错） | task_id（粘贴或连线）、enable_api（默认关）、format（默认 FBX）、quad（true 强制 FBX）、face_limit（0=不传）、texture_size（默认 4096） | `task_id`(STRING，转换任务 ID，交 Fetch 轮询；跳过时=透传)、`调用信息`(STRING) |
| `TTTripoFetch` | 轮询 `GET /tasks/{task_id}` 并取回 | task_id（可连线/手工粘贴）、wait_seconds(600)、poll_interval(5)、refresh_id | `模型路径`(STRING，存 `output/Tripo/`，扩展名按 URL 后缀推断 .fbx/.obj/.glb/.gltf/.stl/.3mf/.usdz)、`预览图`(IMAGE)、`状态`(STRING) |

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
- `workflows/model3d/tripo/28_Tripo_多视图生3D.json`（4×LoadImage 正面/左/背/右 → TTTripoMultiviewTo3D → TTTripoFetch → 同上三输出；batch 顺序=front/left/back/right）。
- `workflows/model3d/tripo/29_Tripo_格式转换.json`（TTTripoConvert → TTTripoFetch → PreviewAny 模型路径/状态；粘贴生成任务 ID 或连线）。
- `workflows/model3d/tripo/30_Tripo_生成到拓扑UV优化.json`（LoadImage → ImageTo3D → Retopo → SmartUV → Convert → Fetch；每阶段 enable_api=付费开关默认关，推荐组合与成本表见说明卡）。
- `workflows/model3d/tripo/31_Tripo_已有模型优化.json`（Retopo → SmartUV → Convert → Fetch；task_id 粘贴生成任务 ID，本地模型需先上传平台取得 file_token/URL）。
