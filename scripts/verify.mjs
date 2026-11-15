#!/usr/bin/env node
// 校验工作流是否"现在真能跑"：JSON 可解析 + 节点类型存在 + 引用的模型在盘上。
// 用法: node scripts/verify.mjs [--offline] [--catalog <catalog/registry.json>]
// 退出码: 0 全通过（可含警告）; 1 有失败
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const args = process.argv.slice(2);
const has = k => args.includes(k);
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const offline = has('--offline');
const registryPath = path.resolve(argOf('--catalog', 'catalog/registry.json'));
const modelsRoot = path.resolve(process.env.COMFY_MODELS || 'E:/RAE_ToolRoot/comfyui/ComfyUI_windows_portable/ComfyUI/models');
const base = process.env.COMFYUI_BASE || 'http://127.0.0.1:8188';
const workflowsRoot = path.resolve(argOf('--workflows', 'workflows'));
const MODEL_EXT = /\.(safetensors|ckpt|pt|pth|gguf|bin|onnx|sft)$/i;
const FRONTEND_ONLY = new Set(['MarkdownNote', 'Note', 'Reroute', 'PrimitiveNode', 'PreviewAny']);

function finish(code) {
  // 不用 process.exit()：undici 的 socket 还在时，Windows 上会触发 libuv 断言
  // （Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)，退出码 0xC0000409），
  // 让"通过"被误读成崩溃。设 exitCode 让事件循环自然退出。
  process.exitCode = code;
}

if (!fs.existsSync(registryPath)) {
  console.error('找不到台账: ' + registryPath + '，先跑 scripts/catalog.mjs');
  finish(1);
} else {
  const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));

  let avail = null;
  if (!offline) {
    try {
      const r = await fetch(base + '/object_info');
      avail = new Set(Object.keys(await r.json()));
    } catch (e) {
      console.error('无法连接 ComfyUI（' + base + '）：' + e.message);
      console.error('要么启动服务，要么显式加 --offline（--offline 不校验节点，只校验文件与模型）。');
      finish(1);
    }
  }

  if (avail || offline) {
    const onDisk = new Set();
    if (fs.existsSync(modelsRoot)) {
      (function walk(d) {
        for (const e of fs.readdirSync(d, { withFileTypes: true })) {
          const p = path.join(d, e.name);
          if (e.isDirectory()) walk(p); else if (MODEL_EXT.test(e.name)) onDisk.add(e.name.toLowerCase());
        }
      })(modelsRoot);
    }

    const fails = [], warns = [];
    for (const w of registry.workflows) {
      if (w.parse_error) { fails.push(w.path + ': JSON 解析失败 — ' + w.parse_error); continue; }
      if (avail) {
        const miss = (w.node_types || []).filter(t => !avail.has(t) && !FRONTEND_ONLY.has(t));
        if (miss.length) fails.push(w.path + ': 缺节点 ' + miss.join(', '));
      }
      const missModels = (w.models || []).filter(m => !onDisk.has(m.toLowerCase()));
      if (missModels.length) warns.push(w.path + ': 缺模型 ' + missModels.join(', '));
    }

    // 台账新鲜度：工作流改了却没重跑 catalog.mjs，台账就开始说谎。
    if (fs.existsSync(workflowsRoot)) {
      const seen = new Set();
      for (const w of registry.workflows) {
        const abs = path.join(workflowsRoot, w.path);
        seen.add(path.resolve(abs));
        if (!fs.existsSync(abs)) { fails.push(w.path + ': 台账里有、磁盘上没有（文件被删或改名）'); continue; }
        const sha = crypto.createHash('sha256').update(fs.readFileSync(abs)).digest('hex');
        if (sha !== w.sha256) fails.push(w.path + ': 内容与台账不一致（重跑 scripts/catalog.mjs）');
      }
      const walk = d => { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const q = path.join(d, e.name); if (e.isDirectory()) walk(q); else if (e.name.endsWith('.json')) if (!seen.has(path.resolve(q))) fails.push(path.relative(workflowsRoot, q).replace(/\\/g, '/') + ': 磁盘上有、台账里没有（重跑 scripts/catalog.mjs）'); } };
      walk(workflowsRoot);
    }
    console.log('台账 ' + registry.workflows.length + ' 个工作流 | 模型目录 ' + onDisk.size + ' 个文件 | 节点库 ' + (avail ? avail.size + ' 个类型' : '未检查(offline)'));
    for (const f of fails) console.log('  [FAIL] ' + f);
    for (const w of warns) console.log('  [WARN] ' + w);
    console.log('结果: ' + (fails.length ? '失败' : '通过') + '（失败 ' + fails.length + ' / 警告 ' + warns.length + '）');
    finish(fails.length ? 1 : 0);
  }
}