# 开发经验（TECH-COMFY-001）

按 `DEC-ORG-075`，四段式：现象 / 根因 / 修法 / 边界。

## 2026-11-16 · 工作流"没坏"是假象，要先验节点再验模型

- **现象**：同步盘里的模板只登记了 10 条工作流，运行时却有 28 条，直觉上以为有一批早已失效、跑不起来。
- **根因**：工作流失效有两种完全不同的原因——**节点类型不存在**（ComfyUI 升级、自定义节点包被删）和**模型文件缺失**（权重没同步）。前者会让工作流直接打不开，后者要到执行时才报错。只看文件在不在，两种都看不出来。
- **修法**：向运行中的 ComfyUI 要 `/object_info`（本次 1059 个节点类型），逐条比对工作流里出现的 `node.type`；模型则在 `models/` 下按文件名建索引比对。实测 28 条里 **0 条缺节点、1 条缺模型**（`flux1-dev-fp8.safetensors`，只影响 TT-IP 07）。
- **边界**：`/object_info` 只反映**当前进程加载**的节点；服务没起或加载失败时不能当"通过"。所以 `verify.mjs` 连不上 8188 一律失败，必须显式 `--offline` 才降级——降级后不做节点校验。

## 2026-11-16 · UI 格式转 API 格式：三种"数组"形态会骗人

- **现象**：写 UI→API 转换器时，`seed` 拿到了 `"randomize"`、`steps` 拿到了 `25` 但整体错位、`denoise` 直接消失。后来又有 5 类节点报"缺必填输入"，而它们在界面里明明有值。
- **根因**：`object_info` 的输入定义里有三种都长得像"数组"的形态——连线类型 `["MODEL", {}]`、嵌套数组枚举 `[["euler","dpmpp_2m"], {}]`、基本类型 `["INT", {}]`，另有逗号组合 `["FLOAT,INT", {}]` 和特殊控件 `COMFY_DYNAMICCOMBO_V3` / `COMFY_AUTOGROW_V3`。把连线类型当控件，会让 `widgets_values` 整体错位一格；漏认某种枚举写法，枚举字段就"消失"成必填缺失。第三个坑是界面专有控件 `control_after_generate`（值为 fixed/randomize/increment/decrement）紧跟在 seed 类输入之后，`widgets_values` 数组里有它、`object_info` 里没有。
- **修法**：按"首元素是数组 → 枚举；首元素是字符串且属于基本/特殊控件类型 → 控件；否则 → 连线"三者分离判断；逗号类型名拆开逐个判断；遇到 seed 类输入且下一值是控制词时跳过一个。覆盖率因此从 12/28 提到 18/28，再由默认值补齐提到 25/28。
- **边界**：节点升级后新增的必填字段（`SaveVideo.format`、`CreateVideo.codec`）在老工作流里根本不存在，只能靠 `object_info` 的 `default` / 枚举首项补齐——**补齐要打印日志**，否则等于悄悄替用户做决定。

## 2026-11-16 · 自写校验器不是事实源，服务端才是

- **现象**：3 条 Qwen 工作流转换后被自己的校验器判"缺必填 `images`"，我据此下了结论"这几条要手工导出 API"，还写进了 README 和操作日志。
- **根因**：`images` 是 `COMFY_AUTOGROW_V3` 容器，在 prompt 里展开成 `images.image_1` 这种子插槽，而 `object_info` 只声明容器名；文生图时子插槽一个都没有，容器仍被标 required。这两点我的校验器都不认，于是产生假失败。
- **修法**：直接 `POST /prompt` 验证——返回 **200 且 `node_errors` 为空**，证明转换器输出本来就对。随后把校验器改成"有子插槽即满足容器""容器允许为空"。
- **边界**：校验器只是**省排队开销的预检**，不是事实源。判断"能不能跑"要看服务端接受与否；预检报错时，先怀疑预检，别急着改产物，更别把预检结论写进文档当成事实——我这次就把错结论写进了 README，下一轮才纠正。

## 2026-11-16 · PS 5.1 的 `2>&1` 会把警告变成终止错误

- **现象**：批量转换脚本跑到一半整个中断，报 `NativeCommandError`，实际原因只是 `ui2api.mjs` 往 stderr 打了一行 `[WARN]`。
- **根因**：`$ErrorActionPreference='Stop'` 加 `2>&1` 时，原生命令的 stderr 会被 PowerShell 包装成 `ErrorRecord` 并当成终止错误抛出。这不是脚本错，是 PowerShell 的行为。
- **修法**：批处理里把 `2>&1` 换成 `2>$null`（丢弃 stderr），或在该段临时把 `$ErrorActionPreference` 降为 `Continue`。
- **边界**：同一个坑在本项目已反复出现（此前在 `git add` 被 git 的 CRLF 警告中断过一次）。凡是"循环调用外部命令 + Stop 模式"的脚本，一律不要用 `2>&1`。

## 2026-11-16 · 方舟插件并入统一仓库：节点类名保持不变，运行时靠 junction 对齐

- **现象**：`comfyui-ark-media` 原先放在 `E:\RAE_ToolRoot\comfyui\plugins\` 并另建独立 git；`nodes/README.md` 约定节点类名带 `TT` 前缀，但插件类名是 `ArkSeedream` / `ArkSeedanceSubmit` / `ArkSeedanceFetch`，已被 18–21 号工作流引用。
- **根因**：节点类名是工作流 ABI（`class_type`），改名会让已入库与用户目录里的工作流全部失效；`TT` 前缀只是新插件命名约定，不是迁移理由。
- **修法**：保留原节点类名（兼容优先），按目录约定收录到 `nodes/comfyui-ark-media/`；`ark.local.json` 由根 `.gitignore` 的 `*.local.json` 和插件自己的 `.gitignore` 双重排除；运行时 `custom_nodes/comfyui-ark-media` 改为指向本仓库的 junction，源码与运行不再双份。
- **边界**：`nodes/` 不是 ComfyUI 自动加载路径，必须 junction/安装后才生效；junction 变更需重启 ComfyUI 才被加载，重启前的 `/object_info` 不代表新状态。新插件仍按 `TT` 前缀命名。

## 2026-11-16 · 多机模型集合不对称时，verify.mjs 结果跨机不可比，必须做基线对照

- **现象**：同一仓库同一批工作流，他机 verify 报告「0 失败 / 1 警告」，本机跑出「6 失败 / 16 警告」，像仓库退化了。
- **根因**：FAIL 缺节点取决于各机 ComfyUI 实例加载的节点包（他机有 comfyui-ark-media / UniversalPrompter，本机没有）；WARN 缺模型取决于各机 `models/` 集合（他机 63 个、本机 20 个）。两者都是「机器现场」而非「仓库内容」。
- **修法**：迁移/大改前先跑一次 verify 存基线失败集合，改后重跑对照——只允许失败集合不变或缩小，不允许新增。T8 迁入 13 个文件后集合与基线完全一致（6 FAIL / 16 WARN），判定无新增失败。
- **边界**：节点包与模型集合不同的两台机之间，verify 的绝对数字不可比；跨机对比只看「相对基线的增量」。模型目录可用 `COMFY_MODELS` 环境变量覆盖默认路径。

