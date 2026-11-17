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

## 2026-11-17 · PowerShell 5.1 经 /prompt 提交含中文 SaveImage 前缀时文件名编码成 ??? 导致落盘失败

- **现象**：脚本用 `Invoke-RestMethod -Body ($payload | ConvertTo-Json)` 提交 API 图，SaveImage `filename_prefix` 含中文（如 `Ark/IP_三视图`），节点执行到写盘时报 `[Errno 22] Invalid argument: ...\output\Ark\IP_???_00001_.png`，整图报错，已生成的付费图片未落盘。
- **根因**：PowerShell 5.1 把字符串请求体按非 UTF-8 默认编码序列化，中文字符在到达 ComfyUI 前已被破坏为 `?`；Windows 文件名不允许 `?`，open() 失败。生成侧（节点 4）已成功，仅保存侧（节点 5）失败。
- **修法**：脚本/API 提交路径一律用 **ASCII 前缀**（如 `Ark/IP_sanshi`）；UI 手工运行不受影响（前端按 UTF-8 提交）。付费生成已成功而落盘失败时，可先从插件私有缓存（如方舟 `user/ark-media-private/`）恢复成图，不重跑生成（防重复扣费）。
- **边界**：仅影响「脚本提交 + 中文路径片段」组合；纯 ASCII 图、UI 提交、`ConvertTo-Json` 深度不足导致的截断是另一类问题。T19 A 线即受此坑，T20 改用 ASCII 前缀规避。

## 2026-11-17 · ComfyUI 0.43 本机构建缺陷：/prompt 列表链接（多路输入）校验对所有节点一律失败

- **现象**：API 图给列表输入（`INPUT_IS_LIST` 节点或新式 `io.Schema(is_input_list=True)` 节点）传 `[["1",0],["2",0]]` 时，3 路报 `bad_linked_input`、2 路报 `unhashable type: 'list'`（execution.py validate_inputs L931-947：任何 list 值都按单链接 `[node_id, slot_index]` 处理，`val[0]` 是 list 时 `prompt[o_id]` 键查找崩溃）。T20 实测三种节点全中招：旧式 `ArkSeedream`（加 `INPUT_IS_LIST=True` 前后）、旧式 `TTTripoMultiviewTo3D`、核心新式 `ImageMergeTileList`。
- **根因**：本构建 `execution.py` 的 `validate_inputs` 只实现了「单链接」分支（`isinstance(val, list)` → `len!=2` 即拒绝），没有「列表链接」分支；`is_input_list` 仅在 server.py 暴露给前端、未被校验逻辑消费。校验先于执行，因此**零扣费**。
- **修法（插件侧已做）**：节点照常加 `INPUT_IS_LIST = True` 并在 `run()` 内解包单值（向后兼容单图连接）；这是正确的 schema 声明，UI 手工多路连接可用。API 图路径需等 ComfyUI 上游修复校验（或升级到修复版本）后解锁，勿自行 patch 校验层绕过。
- **边界**：判断「列表输入是否真生效」不能只看 `/object_info` 的 `is_input_list: true`，必须以一次 `/prompt` 提交实测为准；失败属构建级阻塞时如实记录、不重试付费调用（防重复扣费），并把核心节点 `ImageMergeTileList` 的同样失败作为「非插件缺陷」证据保留。

## 2026-11-17 · 3D 资产链路 v001 实测汇总（Tripo 五节点 + 方舟三视图 + F3D 预览）

- **现象**：负责人要求「全部跑一遍给我看结果」与「保存现在的工作流」——需要一份覆盖文生/图生/多视图/格式转换/预览全链路的实测结论作为推荐工作流方法的证据。
- **根因**：链路长、坑分散（上传维度、ZIP 交付、代理抖动、多路连线校验缺陷、F3D 参数），单点结论不足以支撑方法沉淀。
- **修法**：以 TECH-COMFY-001 母版工作流逐一 E2E——26 文生（T16，credits 20）、27 图生（T19/T24，credits 30）、28 多视图（T25，credits 30，两视图同图仅链路验证）、29 格式转换（T22 FBX credits 5；T25 OBJ→zip 自动解包 obj+mtl+贴图）、25 方舟三视图（T24，doubao-seedream-5-0-flash 2K 出图 1.7MB）；F3D 4.0.1 恢复安装后 `preview.ps1` 五模型（GLB×3/FBX/OBJ，1400×1000 house style）全 exit 0。方法沉淀为技术域 Skill `tt-3d-asset-pipeline`（S-TECH-002，母版 `../TuringTechLab/.agents/skills/tt-3d-asset-pipeline/SKILL.md`，本仓库只存工作流/插件/经验，不复制 Skill 正文）。
- **边界**：实测参数（face_limit/texture/pbr/orientation 等）为最小验证口径，非效果承诺；成本口径为实测值（文生 20–50、图生 30、多视图 30、转换 5），随平台计价变化；测试副本（25t/26t/27t/28t API 图）不入库，仓库只保留 25–29 母版模板。

## 2026-11-17 · Tripo 布线/UV 全流程成本叠加，需阶段开关式成本可控管线

- **现象**：生成接口只给「原始 GLB」，布线/UV 优化与格式转换都要在生成之后另起任务，逐项独立计费；若不控制，一次「生成+重拓扑+SmartUV+转 FBX」成本无声叠加（30+35+20+5≈90 credits），且转换节点 enable_api=false 会报错，无法把多阶段串成一条可跳过的链。
- **根因**：Tripo 将生成（text/image/multiview）、重拓扑（mesh/decimate）、SmartUV（mesh/uv）、转换（models/convert）拆为独立异步任务，各自计费；旧版 Convert 的开关语义与生成节点一致（false=报错），不适合作「可跳过阶段」。
- **修法**（tt-tripo v0.4.0，commit `3ee654e`）：新增 `TTTripoRetopo` 与 `TTTripoSmartUV`，并把 Retopo/SmartUV/Convert 统一为**阶段开关语义**——enable_api=false 时不联网、原样透传 task_id、不报错（调用信息注明「已跳过」+预计成本），true 才提交；模板 30（生成→Retopo→SmartUV→Convert→Fetch）与 31（已有模型优化）按阶段裁剪；smart_uv 仅 Retopo v3.0（v1/v2+true 客户端拦截），SmartUV 输入 ≤8 万等效三角面。离线 mock 5 场景 + /object_info 7 节点 + catalog 48 条验证，零付费。
- **边界**：26/27/28/29 粗糙管线与既有节点行为保持不变；成本为实测口径，随平台计价变化；阶段链的每个新 task_id 都要由 Fetch 依次取回，中间任务产物同样落 output/Tripo 三件套。

## 2026-11-17 · Tripo 分件链路与下游 task_id 限制（分件 ID 需 file_token/URL 桥接）

- **现象**：平台分件（mesh/segment）产出新任务 ID，但下游重拓扑/UV/转换接口用 task_id 作 input 时只接受「生成任务」（文生/图生/多视图）；直接把分件任务 ID 传给下游会被平台拒绝，链路中断。
- **根因**：Tripo 各阶段接口的 input 语义不同——生成/分件接受任务 ID，而 retopo/uv/convert 的 task_id 输入限定为生成任务，分件产物需以文件形式（file_token 或公网 URL）重新入参。
- **修法**（tt-tripo v0.5.0，commit `aa6ff88`）：插件侧加共享 `_source` 输入源三选一校验（生成任务 UUID / file_* token / http(s) URL）并应用到 Retopo/SmartUV/Convert/Segment/Complete；文档与节点 tooltip 明示「分件任务 ID 需经 file_token 或 URL 桥接」；当前不实现上传节点，桥接手工完成（本地模型同理需先上传平台）。分件产物 GLB 的 `tripo_part_*` 节点名由 Fetch 最小解析写入 meta.parts，供补洞 part_names 复用。
- **边界**：分件不改变面数（面数控制在生成/重拓扑 face_limit）；分件 v1 忽略 v2 独有参数（granularity/connectivity/ref_image）并提示；补洞费用文档未标、以平台计费为准。

## 2026-11-17 · 重拓扑/平滑/预览三条工具经验（Blender 4.x 属性、F3D 输出路径、decimate 面数近似）

- **现象**：①T30 的 Blender 无头平滑脚本首跑 `AttributeError: 'Mesh' object has no attribute 'use_auto_smooth'`；②f3d-console 渲染 exit 0 但目标 PNG 不落盘；③face_limit=5000 与 20000 的重拓扑实测面数分别为 5335 与 19899，均非精确值。
- **根因**：①Blender 4.1+ 移除了 `use_auto_smooth`（自动平滑改为 Smooth by Angle 修改器），旧 API 直接报错；②f3d-console 的 `--output` 值含反斜杠 Windows 路径时被静默丢弃（exit 0 无任何提示，也不写默认位置）；③Tripo decimate 的 face_limit 是**目标近似值**，平台按网格结构取接近值。
- **修法**：①平滑着色只按面设置 `poly.use_smooth = True`（无头脚本无需 auto smooth）；②`--output` 一律用**正斜杠**绝对路径（`D:/tmp/.../x.png`）；③报告与断言用 Blender/GLB 解析实测面数，不以 face_limit 输入值当实际值。
- **边界**：f3d 该坑只在反斜杠路径触发，正斜杠/默认输出均正常；面数近似幅度随模型拓扑变化，不存在固定换算系数。T30/T31 均按此经验执行成功。

## 2026-11-17 · 平滑前必须先焊接顶点：直接 smooth_vert 会沿 UV 接缝把模型推开（T32）

- **现象**：T30/T31 的 Blender 平滑（shade_smooth + bmesh smooth_vert×2）在 F3D 预览里模型沿 UV 接缝**裂开/分块**——负责人复查发现 seam 处重复顶点各自移动、裂缝张开。
- **根因**：Tripo 导出的 GLB 在 UV 接缝/法线断开处**顶点重复**（5000 面版实测 4,005 顶点、**2,419 条边界边**）；直接对全部顶点做拉普拉斯平滑时，同一几何点的各份顶点被分别位移，接缝张开。
- **修法**：平滑前先 `bmesh.ops.remove_doubles(dist=1e-5)` 焊接 → `recalc_face_normals` → shade_smooth → smooth_vert×2（同参数）。实测 5000 面版：顶点 4,005→**2,663**、边界边 2,419→**6**、面数 5,335 不变（UV 由 loop 数据保留）；导出 `astro_p5000_smooth2.glb/.fbx`。20000 面版同法（Lead 实测 12,875→9,964、边界 5,529→88）。
- **边界**：焊接阈值 1e-5 只合并接缝重复点，真实开放边界（如底部开口）保留；必须先焊接再平滑，禁止对 split geometry 直接 smoothing。旧流程产物（retopo5000_smooth.glb、retopo20000_smooth.glb、astro_p20000_smooth.fbx）为错误流程产物，已被 `_smooth2` 系列取代（文件保留、仅标注）。

## 2026-11-17 · 曲率加权自适应减面：Decimate 顶点组在本构建无效，改用 dissolve_limit 角阈值（T33）

- **现象**：负责人反馈 20000 面重拓扑后头盔护目镜弧面有折痕/凹凸感，需要「弧面保面、平整区简化」；尝试 Blender Decimate COLLAPSE + 曲率顶点组做加权减面时，顶点组完全不生效（invert 两方向、factor 0→0.5、权重分布 min-max 归一与秩归一化，结果全部 ≈ 全局无权重减面，探针+主跑双重证实）。
- **根因**：Blender 4.3 的 Decimate COLLAPSE 对本机构建基本不采纳 vertex_group（factor/invert 影响可忽略）；API 侧 Tripo 也无权重面数控制参数。
- **修法**：改用 `bmesh.ops.dissolve_limit(angle_limit=radians(5), use_dissolve_boundaries=False, delimit={"NORMAL","UV"})`——二面角阈值即逐边曲率加权等价物：只溶解 ≤5° 的平整边（19,899→**11,979 面**，目标 12,000 的 0.2% 内），曲率 >5° 的边 100% 保留；delimit NORMAL+UV 保护法线接缝与 UV 岛；先 remove_doubles(1e-5) 再溶解，最后 recalc normals + shade_smooth + smooth_vert×2；顶点仅 9,964→9,320（dissolve 不并点，弧面更平滑）。导出 GLB 2,678,112 B / FBX 1,061,292 B，TEXCOORD_0 校验在。
- **边界**：角阈值是全局单参数（如需区域分级可用多网格/多次溶解组合）；目标面数可配置；弧面观感仍需 F3D 目检（33_curvweighted.png / GUI）。

## 2026-11-17 · QuadriFlow vs Tripo quad 对比实验：两条线均失败，如实记录（T34）

- **现象**：①本地 QuadriFlow（Blender 4.3.2）在 Tripo 原始生成网格（96,492 面，54,773 顶点，12,618 边界边）上每次 0 秒拒绝：`QuadriFlow: The mesh needs to be manifold and have face normals that point in a consistent direction`；做了 remove_doubles(1e-5)（边界 12,618→78）+ holes_fill（创建 0 面，边界链非闭合洞）后仍拒绝。②Tripo quad 重拓扑（face_limit=50000, quad=true, smart_uv=true, bake=true）提交被 **HTTP 400** 拒绝（错误体为空），零扣费。
- **根因**：①生成网格含非流形结构（开放边界链、内部非流形顶点），QuadriFlow 要求严格闭合流形；跑通需先体素重网格化（voxel remesh），会破坏 UV/细节，与「保留贴图对比」目标冲突。Blender 4.3.2 的 quadriflow_remesh 签名已变：无 `use_preserve_paint_mask`，新增 `preserve_attributes`（理论可保 UV，但本次因流形拒绝未验证）。②平台拒绝 quad+50000 组合（具体参数限制未知，错误体为空）。
- **修法**：①QF 路线对非流形生成网格不可直接用——当前可用路线仍是已交付的 tri 重拓扑（5000/20000）+ dissolve_limit 自适应减面；②Tripo quad 可改试更小 face_limit（如 20000），需另获授权，本次按「失败不重试」未再提交。两线失败均原样记录；本任务刚生成的两个「未重网格」导出（astro_quadriflow_20k.glb/.fbx）已删除（属本次误产物）。
- **边界**：QF 对严格流形 CAD/雕刻模型仍适用；quad 布线质量对比实验待 Lead 决定参数后重开。

## 2026-11-17 · Tripo quad 重拓扑 400 排查结论：quad=true 与 v3.0 组合不可用（T35）

- **现象**：两次提交 `POST /v3/mesh/decimate`（model=v3.0、quad=true）均被 **HTTP 400** 拒绝且错误体为空——T34 为 face_limit=50000+smart_uv=true，T35 排除变量后为 face_limit=20000+smart_uv=false，仍 400；对照组 tri（quad=false）同接口 5000/20000 面均成功（T30/T31）。零扣费。
- **根因**：**quad=true 与 v3.0 组合被平台拒绝**（错误体空、文档未标）；face_limit 大小与 smart_uv 开/关均非诱因（两变量已排除）。
- **修法**：本机构建下 quad 布线路线不可用，终点记录；**可用路线=tri 重拓扑（5000/20000，smart_uv 正常）+ dissolve_limit 自适应减面（T33）**。若后续需要 quad，候选路径：换 model 版本（v2.0/v1.0）或向 Tripo 官方确认 quad 支持范围——需另获授权。
- **边界**：两次失败均未重试（防重复扣费）、零计费；脱敏 payload 已入 OPERATION_LOG 取证。

## 2026-11-17 · 低面数小特征修复实验：优先零位移平滑着色，位移平滑要极轻（T36）

- **现象**：负责人反馈 20000 面版近景小细节（通气孔/螺丝/边缘）碎面、尖刺、破洞。候选根因=①拉普拉斯平滑直接位移顶点在小特征上产生尖刺；②减面吞小细节。
- **根因**：之前 T30/T31 用 smooth_vert(factor=0.5)×2 是全局顶点位移，在低面数小特征/细边上放大了位移误差，形成尖刺；破洞来自未焊接接缝（weld 后边界 5,529→88，剩余 88 条非闭合边界链）。
- **修法**（T36 三候选实测，19,899 面）：A=**仅平滑着色**（`p.use_smooth=True`，零顶点位移；面/顶点/边界 19,899/9,964/88 全不变）→ `astro_fix_A_shadesmooth`；B=A+`holes_fill(sides=0)` 补洞（本网格补成 7 面、边界 88→64、面 19,906）+平滑着色 → `astro_fix_B_fillholes`；C=A+`smooth_vert(factor=0.15)`×2 轻量位移（计数全不变）→ `astro_fix_C_lightsmooth`。**建议首选 A/C**（零/极轻位移，不会产生新尖刺；B 补洞会改拓扑、需目检）。
- **边界**：补洞改变拓扑、可能引入新面方向问题，需 F3D 目检；细节观感以负责人 F3D 目检为准（36_A/B/C/raw96k 四张预览 + GUI 已开 A/C）。附带更正 T30 归因：f3d-console 不写文件的真正原因是 **PowerShell 5.1 实参模式不展开 `--output=(内联括号表达式)`**（参数被传成含字面括号的字符串）——正斜杠与否无关，正确做法=先把参数拼进变量再传。
