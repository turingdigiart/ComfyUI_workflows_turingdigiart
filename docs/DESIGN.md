# TECH-COMFY-001 设计（2026-11-16）

本文件定义这套 ComfyUI 工作流体系的**分层、分类、命名、接入、产出路由与扩展方式**。
与中控既有规范对齐：`DEC-ORG-092`（母版迁入本仓）、`DEC-ORG-074`（运行时分层）、
`工具配置/ComfyUI/README.md`（L1/L2/L3 三层）。**本文件不重复它们的正文，只写本仓的落地规则。**

## 一、五层分工（谁放哪，谁不复制谁）

```
L0  运行内核      ${TOOLS_ROOT}/comfyui/ComfyUI_windows_portable       本机安装，不进同步盘、不进 Git
L1  同步配置      中控 工具配置/ComfyUI/（settings、插件锁、模型清单、recipes）   同步盘，小文件
L2  通用资产      本仓 TECH-COMFY-001（workflows + nodes + catalog + scripts）  Git，机构号推送
L3  项目微调      <项目>/workflow/（小写单数）                            随项目（Git 或同步盘）
L4  产出         测试→本仓 output/（忽略）；项目正式产出→项目空间
```

判断归属只问一句：**这条工作流只服务一个项目吗？** 是 → L3；否 → L2。

## 二、workflows/ 分类体系

两级：**第一级是产出形态，第二级是模型族或用途**。第一级固定五类，不随意新增。

| 一级 | 含义 | 现有二级 |
|---|---|---|
| `image` | 静态图（文生图、改图、海报、放大） | `sdxl` `flux` `qwen` `zimage` `sd15` `ark` `api` `poster` |
| `video` | 视频（文生、图生、有声） | `wan` `ltx` `ark` |
| `model3d` | 图/文生 3D | `hunyuan` `tripo` |
| `identity` | 人物一致性、形象复用 | `tt-ip-写实版` |
| `audio` | 音频/配音/音效 | `ace` |

二级目录的取舍：
- 按**模型族**建（`sdxl`/`flux`/`qwen`…）——同一族共享模型与参数习惯，放一起好找
- 按**用途**建（`poster`/`api`）——跨模型族的固定产出形态
- 新增二级目录的门槛：**同一族或同一用途积累到 2 条以上**才建，只有 1 条就放在最接近的已有目录里

## 三、命名与版本

```
workflows/<一级>/<二级>/<用途描述>.json              首版，无版本号
workflows/<一级>/<二级>/<用途描述>_vNNN_<变更>.json   派生版本（永不覆盖）
```

- 用途描述用中文，能一眼看出「拿来做什么」，例如 `写实版_Apose全身`、`方舟Seedream_写实IP三视图`
- 派生一律走 `node scripts/bump.mjs --workflow <x.json> --label <变更>`，自动递增、拒绝覆盖
- **不手工改名**：改名会让 ComfyUI 界面里的收藏与历史引用失效；确需改名时同一次提交里更新台账

## 四、元数据与台账（唯一状态源）

工作流本体是**原样 ComfyUI JSON**，不加私有字段（UI 保存会丢）。元数据全在台账：

| 产物 | 用途 | 生成方式 |
|---|---|---|
| `catalog/registry.json` | 机器读：路径、SHA-256、节点类型、模型、参数、说明 | `scripts/catalog.mjs` |
| `catalog/WORKFLOWS.md` | 人读总表：说明 + 参数 + 校验状态 | 同上 |
| `catalog/INDEX.md` | 检索索引：按类别列路径/参数/模型/说明 | 同上 |

**台账是生成物，不手改**。改了工作流必须重跑 `catalog.mjs`，否则 `verify` 会报「内容与台账不一致」。

说明来源：优先取画布里的 `MarkdownNote` 首行；没有说明节点的，台账标「靠文件名判断」。

## 五、插件层（nodes/）

```
nodes/<插件名>/          ← 源码母版，进 Git
   __init__.py           NODE_CLASS_MAPPINGS
   nodes.py / requirements.txt / README.md
```

与运行时的关系：ComfyUI 只从 `custom_nodes/` 加载，所以 `nodes/<插件>` 需要**链接或复制**进
`custom_nodes/`。**当前状态（2026-11-16 收口）：`comfyui-ark-media` 随运行时安装；
自研 `tt-tripo` 已建 junction 接入并重启生效**，`/object_info` 节点库 1059 → **1061**，
`TTTripoSubmit` / `TTTripoFetch` 可查，`model3d/tripo/26_Tripo_文生3D.json` 校验转为通过。

接线命令（换机时照做）：

```powershell
mklink /J "<runtime>\ComfyUI\custom_nodes\tt-tripo" "<repo>\nodes\tt-tripo"
# 重启 ComfyUI 后在 /object_info 里确认 TTTripoSubmit 出现
```

命名：目录小写短横线（`tt-tripo`），节点类前缀 `TT`（在 ComfyUI 搜索框输 `TT` 就知道哪些是自研）。

## 六、项目接入（L3）

1. 项目里新建 `workflow/`（小写单数），放**只服务该项目**的工作流
2. 需要通用能力时，不复制本仓文件，而是**引用**：在项目记录里写清使用的 `workflow_id`（台账路径）与版本
3. 项目里改顺了、且发现对别的项目也有用 → **抽掉项目专属值**再提升进 L2（见 README「微调回流」）

## 七、产出路由（output）

| 产出性质 | 落地位置 | 是否入库 |
|---|---|---|
| 测试、调参、日常随手跑 | 本仓 `output/` | 否（`.gitignore`：`output/*`，保留 `.gitkeep` 与 README） |
| 项目正式交付 | 项目空间对应目录 | 视项目而定 |
| 需要长期留档的样张 | 项目空间历史版本或交付批次 | 是（按 `file-governance`） |

`SaveImage`/`SaveVideo` 的 `filename_prefix` 指向 `output/`，出图后能就地找到。

## 八、扩展开关（加新东西时照这个走）

| 要加什么 | 步骤 |
|---|---|
| **新模型** | 先按 `WEIGHTS_REGISTRY` / `P-ORG-005` 把权重放进权重根并登记 → 再建工作流 → 台账自动校验模型在位 |
| **新任务** | 放最接近的二级目录；若无合适二级目录且已有 ≥2 条同类，才新建二级目录 |
| **新插件** | `nodes/<name>/` 建源码 + `requirements.txt` → 链接进 `custom_nodes/` → 重启运行时 → 在 `/object_info` 里确认节点出现 → 才有工作流可以引用它 |
| **项目微调** | 在项目 `workflow/` 里派生，不改进本仓；提升时抽掉专属值 |

## 九、验收标准（一条工作流算"可用"需同时满足）

1. `node scripts/verify.mjs` 对该条无 FAIL（节点类型全部存在）
2. 引用的模型在磁盘上（有则 WARN 可接受，但要在台账里可见）
3. 台账有条目且 `sha256` 与磁盘一致
4. 至少 `run.mjs --dry-run` 通过；关键工作流应真跑一次并记录产出

## 十、当前基线（2026-11-16 收口）

```
工作流 43 条：image 16 / identity 16 / video 8 / model3d 2 / audio 1
        其中 UI 格式 42 条、API 格式 1 条（image/poster/POSTER_LAYERED_v001_api.json）
插件 2 个：comfyui-ark-media（随运行时）、tt-tripo（junction 已接，重启后生效）
台账：registry.json / WORKFLOWS.md / INDEX.md
校验：**通过**（FAIL 0 / WARN 6 缺模型）；缺说明 0；节点库 1061
```

**待办一件**：6 条缺模型（`flux1-dev-fp8` ×3、`flux-union-pro-2.0`、`turingteacher_v002_quick`、
`v1-5-pruned-emaonly-fp16`、`wan2.1_t2v_1.3B_fp16`）——补权重或标 `Blocked`，待负责人定。

## 十一、两种文件格式（2026-11-16 补）

`workflows/` 下允许并存两种 JSON，台账用 `format` 字段区分：

| 格式 | 结构 | 来源 | 用途 |
|---|---|---|---|
| `ui` | `{ nodes:[...], links:[...] }` | ComfyUI 界面保存 | 在界面里打开、手工改 |
| `api` | `{ "<id>": { class_type, inputs } }` | 「导出(API)」或脚本生成 | `run.mjs` 直接提交 |

规则：
- API 格式文件**必须以 `_api.json` 结尾**，一眼能分辨（否则在界面里点开是空的）
- 两种格式都进台账、都被 `verify` 校验节点类型与模型；API 格式的节点从 `class_type` 读取
- 说明文字优先取画布里的 MarkdownNote；API 格式没有画布，取同级 `README.md` 的首行标题
- 同一份工作流的两种格式并存时，**UI 格式是母版**，API 格式是导出物；改完 UI 要重新导出

## 十二、权重怎么进运行时（不复制、不搬动）

三类资产用**三种不同**的接线方式，别混：

| 资产 | 接线方式 | 为什么 |
|---|---|---|
| `workflows/`（UI 工作流） | **Junction** 替换 ComfyUI 的 `user/default/workflows` | 要的是"同一份文件"，界面保存即 Git 改动 |
| `nodes/<插件>` | **Junction** 到 `custom_nodes/<插件>` | 插件是目录，ComfyUI 按目录加载 |
| 权重（LoRA/底模/ControlNet） | **`extra_model_paths.yaml`** 追加路径 | **不能**替换 `models/loras`——那会把已有 32 个模型藏起来 |

### extra_model_paths 的实际配置

`ComfyUI/extra_model_paths.yaml`（本机 2026-11-16 建立）：

```yaml
tt_ip_realistic:
  base_path: J:/BaiduSyncdisk/TuringDigiArt/运营内容/常用人物/写实版/权重
  is_default: false
  loras: loras
  checkpoints: checkpoints
  vae: vae
  controlnet: controlnet
  clip_vision: clip_vision
  upscale_models: upscale_models
```

对应登记：`WEIGHTS_REGISTRY` 的 `W-IP-REALISTIC-001`（`comfyui_layout: true`）。
效果：`LoraLoader` 的候选从 32 → **37**，`turingteacher_v002_quick` 可直接选用。

**改这个文件必须重启 ComfyUI 才生效**，且重启会丢未保存的画布改动。

### 为什么不用 junction 挂 loras

`models/loras` 现有 32 个模型。用 junction 替换该目录 = 那 32 个当场消失。
`extra_model_paths` 是**追加**，两边都在，文件名冲突时 ComfyUI 自己处理。

### 生效时机（容易记错）

| 改动 | 需要重启 ComfyUI 吗 |
|---|---|
| 往 `models/` 里放新模型文件 | **不需要**（实测 ControlNet 下完立刻出现在候选列表） |
| 改 `extra_model_paths.yaml` | **需要** |
| 改 `custom_nodes/`（装/删插件） | **需要** |

### 校验器如何判断"模型在不在"

`scripts/verify.mjs` 与 `scripts/catalog.mjs` 共用 `lib/model-index.mjs`，索引来源两处：
- 运行时 `models/` 目录（递归）
- `extra_model_paths.yaml` 声明的权重根

2026-11-16 之前只扫前者，导致挂在权重根的 `turingteacher_v002_quick` 被误报缺失。
现在模型索引 73 个（`models/` 67 + 权重根 6），**台账与你实际能用的一致**。