# 运维手册（工作流增删改）

面向"我有一条新需求，怎么把它变成仓库里可复用的工作流"。

## 一、新增一条工作流

```
① 在 ComfyUI 界面里搭好 → 跑通一次 → 确认效果
② 菜单「导出（API）」存成 <名称>.api.json（临时用，校验过就能删）
③ 决定归类和文件名，放进 workflows/<类别>/<名称>.json
④ node scripts/catalog.mjs        重生成台账（含 SHA-256）
⑤ node scripts/verify.mjs         三重校验 + 台账新鲜度
⑥ git add -A && git commit
⑦ git push
```

**第 ② 步的 API 文件只是给 `run.mjs` 用的**，不是仓库资产。仓库里存的是 UI 格式（`nodes`+`links`），因为那才是能在界面里打开的格式。

## 二、改现有工作流

**永远不要在原文件上直接改。** 走派生：

```powershell
node scripts/bump.mjs --workflow workflows/image/sdxl/01_SDXL_文生图.json --label 高清
# 生成 01_SDXL_文生图_v001_高清.json，旧版原样保留
```

这样 `git diff` 能直接看出"v001 到底改了什么"，回滚也有靶子。

## 三、命名与分类

```
workflows/<类别>/<模型或用途>_<具体用途>.json
```

| 类别 | 放什么 | 现有 |
|---|---|---|
| `image` | 文生图、图生图、改图、放大 | 13 条（按模型分子目录：sdxl/qwen/flux/zimage/ark/api） |
| `video` | 文生视频、图生视频、有声视频 | 7 条（wan/ltx/ark） |
| `model3d` | 图生 3D | 1 条（混元） |
| `identity` | 人物一致性、形象复用 | 7 条（TT-IP 写实版） |

文件名带版本时用 `_vNNN_`（三位数），排在说明前面：`foo_v002_高分辨率.json`。

## 四、常见失败与处理

| 报错 | 含义 | 处理 |
|---|---|---|
| `[FAIL] 缺节点 X` | ComfyUI 升级或自定义节点包被删 | 装回节点包；装不回就改工作流换节点 |
| `[WARN] 缺模型 X` | 权重不在本机 | 按 `WEIGHTS_REGISTRY` 补；补不到就把该工作流标 `Blocked` |
| `[FAIL] 内容与台账不一致` | 改了工作流没重跑 `catalog.mjs` | 重跑 `catalog.mjs` |
| `[FAIL] 磁盘上有、台账里没有` | 手工塞了文件没登记 | 同上 |
| `[FAIL] 台账里有、磁盘上没有` | 文件被删或改名 | 重跑 `catalog.mjs`（会移除该条） |
| `verify` 连不上 8188 | 服务没起 | 启动 ComfyUI；只查文件用 `--offline`（**此时不校验节点**） |

## 五、和运行时、权重的关系

- **ComfyUI 本体**：`TOOL-ORG-COMFYUI-001`，装在 `${TOOLS_ROOT}/comfyui/...`。本仓库不复制它。
- **模型权重**：`WEIGHTS_REGISTRY` / `P-ORG-005` 管理，按权重根登记。本仓库只引用文件名，不存权重。
- **接上运行时**：`scripts/setup.ps1` 把 ComfyUI 的 `user/default/workflows/` 指向本仓库 `workflows/`。接上后界面里手工保存的工作流**直接成为 Git 改动**——这正是"手工开发也留档"的实现方式。

## 六、提交前必过

```powershell
node scripts/catalog.mjs   # 台账必须是最新的
node scripts/verify.mjs    # 退出码必须为 0（WARN 可接受，FAIL 不可）
```

两条都过才提交。`verify` 会同时检查台账新鲜度，所以先跑 `catalog` 再跑 `verify` 是固定顺序。