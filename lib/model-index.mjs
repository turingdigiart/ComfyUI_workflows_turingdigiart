// 模型索引：把 ComfyUI 能看到的模型文件名汇总成集合。
// 两个来源：
//   1) 运行时 models/ 目录（递归）
//   2) extra_model_paths.yaml 里追加的路径（权重根）
// 只认文件名（大小写不敏感），因为工作流里写的是文件名，不带目录。
import fs from 'node:fs';
import path from 'node:path';

export const MODEL_EXT = /\.(safetensors|ckpt|pt|pth|gguf|bin|onnx|sft)$/i;

function walkFiles(dir, cb) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walkFiles(p, cb);
    else if (MODEL_EXT.test(e.name)) cb(e.name);
  }
}

// 简易解析：只支持本机构实际使用的子集 —— `名字:` 分组、`base_path:`、以及 `子目录: 相对路径`
// （值可以是单行，也可以是多行 `|` 块；两种都处理）
export function parseExtraModelPaths(file) {
  if (!file || !fs.existsSync(file)) return [];
  const lines = fs.readFileSync(file, 'utf8').split('\n');
  const roots = [];
  let base = null;
  let inBlock = null;
  for (const raw of lines) {
    const line = raw.replace(/\t/g, '  ');
    if (!line.trim() || line.trim().startsWith('#')) continue;
    const indent = line.match(/^\s*/)[0].length;
    const m = line.match(/^\s*([A-Za-z0-9_]+):\s*(.*)$/);
    if (!m) {
      // 多行块里的路径行
      if (inBlock && base) {
        const v = line.trim();
        if (v && !v.startsWith('-')) roots.push(path.join(base, v));
      }
      continue;
    }
    const [, key, value] = m;
    inBlock = null;
    if (indent === 0) { base = null; continue; }          // 组名
    if (key === 'base_path') { base = value.trim(); continue; }
    if (!base) continue;
    const v = value.trim();
    if (v === '|' || v === '') { inBlock = key; continue; }  // 后面跟多行
    roots.push(path.join(base, v));
  }
  return roots;
}

export function buildModelIndex({ modelsRoot, extraPathsFile }) {
  const names = new Set();
  if (modelsRoot && fs.existsSync(modelsRoot)) walkFiles(modelsRoot, n => names.add(n.toLowerCase()));
  const extraRoots = parseExtraModelPaths(extraPathsFile);
  for (const r of extraRoots) walkFiles(r, n => names.add(n.toLowerCase()));
  return { names, extraRoots };
}
