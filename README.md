# TECH-COMFY-001｜ComfyUI 工作流与节点开发

机构 ComfyUI 生产环境的**版本化工作流仓库**。运行时（ComfyUI 本体、模型权重）不在本仓库，
由 `TOOL-ORG-COMFYUI-001` 与 `WEIGHTS_REGISTRY` 管理；这里只管"怎么连、怎么用、改过什么"。

## 为什么存在

工作流只存在 ComfyUI 的 `user/default/workflows/` 里时，改了就没了、换机就丢了、
没人知道 v002 比 v001 改了什么。本仓库把它变成可 diff、可回滚、可交接的代码资产。

## 结构

```
workflows/<类别>/<名称>.json    工作流本体（原样 ComfyUI JSON，不做任何封装）
catalog/registry.json           机器读台账（由脚本生成，勿手改）
catalog/WORKFLOWS.md            人读台账（由脚本生成，勿手改）
lib/comfy-api.mjs               本地 API 客户端
scripts/catalog.mjs             扫工作流 → 重建台账
scripts/verify.mjs              JSON + 节点 + 模型三重校验
scripts/setup.ps1               把 ComfyUI 工作流目录接到本仓库（junction）
docs/DEV_EXPERIENCE.md          踩坑记录（DEC-ORG-075）
```

## 三条硬约束（保证手工开发兼容）

1. **工作流就是原样 ComfyUI JSON**，不加私有字段——UI 保存不会丢掉我们的元数据，因为元数据不在 JSON 里。
2. **元数据放台账**（`registry.json`），不塞进工作流。
3. **文件名带 `_vNNN_` 永不覆盖**：新版本另存，旧版本留着。

## 日常用法

```powershell
# 0) 开工前环境自检：真跑一次最小 SDXL 链路，确认能出图（约 2~30 秒）
node scripts/smoke.mjs

# 1) 改了工作流之后，重建台账
node scripts/catalog.mjs

# 2) 提交前校验（JSON 可解析 + 节点存在 + 模型在位）
node scripts/verify.mjs

# 3) 派生新版本（不覆盖旧版，版本号自动递增）
node scripts/bump.mjs --workflow workflows/image/sdxl/01_SDXL_文生图.json --label 高清

# 4) UI 格式 → API 格式（省掉手工导出；有局限，见下）
node scripts/ui2api.mjs --workflow workflows/image/sdxl/01_SDXL_文生图.json

# 5) 跑一条工作流（先 dry-run 校验，再真跑）
node scripts/run.mjs --prompt <api.json> --dry-run
node scripts/run.mjs --prompt <api.json> --set 6.text="一只猫" --wait

# 6) 换机后把 ComfyUI 接到本仓库（先预演，确认后 -Apply；本机 2026-11-16 已完成）
powershell -File scripts/setup.ps1
```

### 关于 `run.mjs` 的输入格式

ComfyUI 保存的工作流是 **UI 格式**（`nodes` + `links`），而 `/prompt` 接口要 **API 格式**（节点字典）。
所以执行前需在 ComfyUI 界面里「导出（API）」得到 `*api.json`，再交给 `run.mjs`。

`run.mjs` 会先用 `/object_info` 校验每个节点的**必填输入是否齐全、有没有写错输入名**，
校验不过直接退出、不排队——避免把坏图塞进队列才发现。

## 校验的三种结果

| 结果 | 含义 | 处理 |
|---|---|---|
| `[FAIL] 缺节点` | ComfyUI 升级或删了自定义节点包，工作流跑不了 | 装回节点包，或改工作流 |
| `[WARN] 缺模型` | 权重不在本机 | 按 `WEIGHTS_REGISTRY` 补齐，或把工作流标 Blocked |
| 通过 | 现在就能跑 | — |

`verify.mjs` 连不上 8188 时直接失败——**"没检查"不等于"通过"**。只查文件用 `--offline`，但要明白那时不校验节点。

### `ui2api.mjs` 的局限（重要）

自动转换在 2026-11-16 实测 **18/28 通过**。剩下 10 条不是脚本 bug，是**工作流本身过期**：

| 现象 | 原因 | 处理 |
|---|---|---|
| `SaveVideo` 缺 `format`（4 条） | 节点定义后来新增了必填字段，老工作流保存时没有 | 在界面里重新保存一次即可补上 |
| `TextEncodeQwenImage21` 缺 `images`（3 条） | 多图输入是结构化控件，不是普通 widget | 手工「导出(API)」 |
| `LTXVEmptyLatentAudio` 缺 `frame_rate` | 同上，节点已更新 | 重新保存或手工导出 |

**结论**：转换器优先用；它报错时，错误本身就是"这条工作流该更新了"的信号。真跑不通就用界面「导出(API)」兜底。
## 三层归属：什么放这里，什么不放（2026-11-16 定）

本仓只做**通用资产**。判断标准是"换一个项目还用不用得上"。

| 资产 | 放哪 | 理由 |
|---|---|---|
| **通用工作流**（多项目复用） | 本仓 `workflows/` | 一次开发，处处可调；改一处所有项目受益 |
| **自研插件 / 自定义节点** | 本仓 `nodes/` | 插件是能力，不是项目产物；版本一起走 |
| **项目微调后的工作流** | **该项目空间**（不在本仓） | 带项目专属参数（尺寸、风格、客户要求），混进来会污染通用层 |
| **项目正式产出** | **该项目空间** | 交付物属于项目，不属于工具仓 |
| **测试 / 日常随手产出** | 本仓 `output/`（被 ignore） | 方便就地查看，但不占版本库 |

### 微调出来的工作流怎么回流

项目里改顺了之后，如果发现"这个改法对别的项目也有用"，再把它**抽象成通用版本**放回本仓：

```
项目空间/workflows/xxx_v003_客户A改版.json     ← 带项目参数，留在项目
                ↓ 抽出通用部分
本仓/workflows/image/xxx/xxx_v003_通用改版.json  ← 去掉项目专属值再入库
```

不要直接把项目版本拷进本仓——那等于把项目参数变成默认值，下个项目会被误导。

### output 目录

- 保留目录本身（带 `.gitkeep` 和说明），**内容全部忽略**
- `SaveImage`/`SaveVideo` 的 `filename_prefix` 指到这里，出图立刻能在仓库里找到
- 可随时清空，不构成资产

## 接线状态（2026-11-16 已接）

```
E:\RAE_ToolRoot\comfyui\...\user\default\workflows
    → Junction →
E:\RAE_DevRoot\TECH-COMFY-001_comfyui-workflows\workflows
```

**真实文件只有一份，在仓库里。** 验证过往返：经 ComfyUI 路径写入 → 仓库立刻出现；从仓库删除 → ComfyUI 路径同时消失。

影响：ComfyUI 界面里的工作流现在是**按类别分文件夹**显示（`image/`、`video/`、`model3d/`、`identity/`），不再是原来的平铺列表。

原目录备份在 `user/default/workflows_backup_20261116_044215`（28 个文件），需要还原时把链接删掉、备份改回原名即可。