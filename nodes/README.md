# nodes/｜自研 ComfyUI 插件

本机构自己开发的 ComfyUI 自定义节点统一放这里，**一个插件一个子目录**。

## 目录约定

```
nodes/<插件名>/
├─ __init__.py          # ComfyUI 加载入口，导出 NODE_CLASS_MAPPINGS
├─ nodes.py             # 节点实现
├─ requirements.txt     # 该插件的 Python 依赖（可为空）
├─ README.md            # 用途、输入输出、示例工作流 id
└─ tests/               # 可选：最小可跑用例
```

## 与 ComfyUI 的关系

ComfyUI 只从 `${TOOLS_ROOT}/comfyui/.../custom_nodes/` 加载插件。
本目录是**源码母版**，通过 junction 或 `scripts/setup.ps1` 建链进入运行时——
和 `workflows/` 一样：**本仓是源，运行时不复制正文**。

## 命名

- 目录名用短横线小写：`tt-prompt-kit`、`tt-export-helper`
- 节点类名前缀 `TT`：`TTPromptMerge`、`TTExportMark`
- 这样在 ComfyUI 搜索框一搜 `TT` 就能看到我们自己的节点

## 入库门槛

1. 能在当前 ComfyUI 版本里加载（`/object_info` 能查到节点名）
2. `requirements.txt` 写明依赖，装完能跑
3. README 写清输入输出和至少一个示例工作流
4. 有对应工作流放在 `workflows/` 且已登记台账