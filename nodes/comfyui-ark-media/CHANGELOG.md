# 开发记录

## 1.0.0 — 2026-10-30

- 火山方舟个人Key直连：Seedream图片、Seedance创建任务、Seedance获取视频3节点。
- 图片和视频参考输入、原生IMAGE/VIDEO输出、音轨保留由原生SaveVideo处理。
- 本地提交回执防重复，未确认提交不自动重试，独立任务恢复入口。
- 密钥配置隔离、媒体下载不附带API鉴权、白名单迁移包。
- 默认关闭API调用，18～21示例；无Key阶段仅模拟验收，不产生真实平台调用费用。

## 1.0.0 实机验证 — 2026-11-16

- 负责人实测全部通过：`doubao-seed-2-1-pro-260915` 聊天、`doubao-seedream-5-0-flash-260915` / `doubao-seedream-5-5-261028` 同步生图（2K）、`doubao-seedance-2-5-260628` 视频任务（succeeded，下载 mp4）；插件代码路径端到端验证（core.Client + submit_once + download）。
- 关键口径确认：Seedream 只能走同步 `/images/generations`（异步 tasks 报 `does not support content generation`）；视频走异步 `/contents/generations/tasks` + 轮询；`watermark:false` 可去"AI生成"角标（对外发布需自行补显式标识）；`ratio` 参数名与官方一致，无需改代码。
- 环境事实：本机便携包位于 `E:\RAE_ToolRoot\comfyui\ComfyUI_windows_portable`，启动 `run_nvidia_gpu.bat`（CWD 必须为便携包根目录）；示例工作流 18–21 由 `tools/create_workflows.py` 生成到 `ComfyUI\user\default\workflows`。
- 安全：部署副本 `ark.local.json` 存 Key，不入同步盘；已暴露的 Key 建议轮换（只需改此一处）。

## 纳入统一仓库 — 2026-11-16

- 源码母版迁入 `turingdigiart/ComfyUI_workflows_turingdigiart` 的 `nodes/comfyui-ark-media/`；本地运行时 `custom_nodes/comfyui-ark-media` 改为 junction 指向本仓库，避免双份正文。
- 示例工作流路径更新为仓库内 `workflows/image/ark/`、`workflows/video/ark/`；默认模型标注为 2026-11-16 实机验证（Seedream 5.0-flash / 5.5、Seedance 2.5）。

## 1.0.1 — 2026-11-17｜机构规则：所有生成一律不加水印

- 负责人「记住 所有水印都不要加！」→ 节点 `ArkSeedream` / `ArkSeedanceSubmit` 的 `watermark` 默认值由 true 改为 false；`tools/create_workflows.py` 生成的示例也改为 false。
- 仓库工作流 18/19/21/25 的 `watermark` 参数批量固化为 false（20 号为任务取回，无提交节点）；脚本调用须显式传 `watermark: false`。
- 合规：对外发布仍须按《人工智能生成合成内容标识办法》由使用方自行补显式标识，本规则不解除该义务。
- 补充（2026-11-17）：负责人确认「不需要补」——不额外添加 AI 显式标识，对外发布亦不加。

## 1.0.2 — 2026-11-17｜ArkSeedream 参考图输入改为列表（T20）

- 现象：T19 用 API 图给 `reference_images` 连三路参考图，`/prompt` 校验拒绝（`bad_linked_input` / `unhashable type: 'list'`），三视图多参考链路走不通；且核心代码 `references()` 本就按列表设计（≤10 张），仅输入声明为单输入，前后矛盾。
- 根因：节点 `INPUT_TYPES` 把 `reference_images` 声明为单个 `("IMAGE",)`，ComfyUI 视为单连接输入。
- 修法：`ArkSeedream` 增加 `INPUT_IS_LIST = True`（`/object_info` 暴露 `is_input_list: true`，前端允许多路连接）；`run()` 对各输入做单值解包（向后兼容：单图连接与 18–21 号工作流不受影响），`reference_images` 统一归一为张量列表后交给既有 `references()`。
- 边界：已知本机 ComfyUI 0.43 构建级缺陷——`/prompt` 的列表链接 `[["1",0],["2",0]]` 校验在旧式与新式节点（含核心 `ImageMergeTileList`）一律失败（详见仓库 `docs/DEV_EXPERIENCE.md`），因此本修复的 API 图路径仍受该缺陷阻塞，UI 手工多路连接为当前可用路径；此为本构建问题，非插件缺陷。不改变 Key 存储与付费 P1 口径。
- 部署：机器 B 若为 `manage.py install` 安装副本，需重新执行 `python manage.py install` 后生效；本机 junction 指向仓库母版，即时生效。

## 1.0.3 — 2026-11-17｜紧急回退 INPUT_IS_LIST，改单输入承载图像批次（T21）

- 现象：T20 加的 `INPUT_IS_LIST = True` 在 ComfyUI 0.43 前端把 `ArkSeedream` 的全部控件（enable_api/prompt/model/size…）渲染成不可交互的输入槽，用户在 UI 勾不上 enable_api，节点无法使用。
- 根因：`INPUT_IS_LIST` 是「整节点列表化」语义——前端据此把所有输入（含控件）按列表输入处理，与本插件「仅参考图为多图」的意图不符；且 T20 已证实本构建 `/prompt` 列表链接校验对所有节点失败。
- 修法：删除 `INPUT_IS_LIST` 与 run() 内解包，恢复原始单输入签名；`references()` 增加 batch 张量拆分（`(B,H,W,C)` 按 batch 维拆为逐张，3D 单张包装），**多参考图改为 ComfyUI 自带 `ImageBatch` 节点串联成单链输入**（3 张参考 = 2 个 ImageBatch），API/UI 两条路径均可用，并绕开 `/prompt` 列表链接校验缺陷。
- 边界：多图连接必须经 ImageBatch（或其它输出 batch 张量的节点）；直接多路连线仍会被校验拒绝。单图连接行为不变，18–21 号工作流不受影响。版本 1.0.3。
