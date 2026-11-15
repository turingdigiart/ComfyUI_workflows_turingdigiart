#!/usr/bin/env node
// 扫描工作流目录，生成 registry.json（机器读）+ WORKFLOWS.md（人读）。
// 用法: node scripts/catalog.mjs [--source <工作流目录>] [--out <catalog 目录>]
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const args = process.argv.slice(2);
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const source = path.resolve(argOf('--source', process.env.COMFY_WORKFLOWS || 'E:/RAE_ToolRoot/comfyui/ComfyUI_windows_portable/ComfyUI/user/default/workflows'));
const outDir = path.resolve(argOf('--out', path.join(process.cwd(), 'catalog')));
const MODEL_EXT = /\.(safetensors|ckpt|pt|pth|gguf|bin|onnx|sft)$/i;

function walk(dir, acc = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, acc);
    else if (e.name.endsWith('.json')) acc.push(p);
  }
  return acc;
}

const files = walk(source).sort();
const entries = [];
for (const file of files) {
  const rel = path.relative(source, file).replace(/\\/g, '/');
  const raw = fs.readFileSync(file);
  let json = null, parseError = null;
  try { json = JSON.parse(raw.toString('utf8')); } catch (e) { parseError = e.message; }
  const nodes = json?.nodes || [];
  const modelRefs = new Set();
  for (const n of nodes) for (const v of (n.widgets_values || [])) {
    if (typeof v === 'string' && MODEL_EXT.test(v)) modelRefs.add(v);
  }
  const name = path.basename(file, '.json');
  const vm = name.match(/_v(\d{3})_?/);
  const dirParts = rel.split('/');
  const category = dirParts.length > 1 ? dirParts[0] : '未分类';
  entries.push({
    workflow_id: rel.replace(/\.json$/, '').replace(/[\\/]/g, '-').toLowerCase(),
    path: rel,
    category,
    name,
    version: vm ? 'v' + vm[1] : null,
    sha256: crypto.createHash('sha256').update(raw).digest('hex'),
    bytes: raw.length,
    node_count: nodes.length,
    node_types: [...new Set(nodes.map(n => n.type).filter(Boolean))],
    models: [...modelRefs].sort(),
    parse_error: parseError,
    status: parseError ? 'Broken' : 'Candidate'
  });
}

const registry = {
  schema: 1,
  generated_at: new Date().toISOString(),
  source,
  comfyui_version: process.env.COMFYUI_VERSION || null,
  count: entries.length,
  workflows: entries
};

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'registry.json'), JSON.stringify(registry, null, 2), 'utf8');

const byCat = new Map();
for (const e of entries) { if (!byCat.has(e.category)) byCat.set(e.category, []); byCat.get(e.category).push(e); }
const lines = [
  '# 工作流台账',
  '',
  '> 由 `scripts/catalog.mjs` 生成，**不要手改**。改工作流后重跑脚本。',
  `> 生成时间：${registry.generated_at}`,
  `> 来源目录：\`${source}\``,
  `> 工作流总数：${entries.length}`,
  '',
  '## 分类分布',
  '',
  '| 类别 | 数量 |',
  '|---|---:|',
  ...[...byCat].map(([c, list]) => `| ${c} | ${list.length} |`),
  ''
];
for (const [cat, list] of byCat) {
  lines.push(`## ${cat}`, '', '| 工作流 | 节点数 | 模型数 | SHA-256（前 12） | 状态 |', '|---|---:|---:|---|---|');
  for (const e of list.sort((a, b) => a.path.localeCompare(b.path))) {
    lines.push(`| \`${e.path}\` | ${e.node_count} | ${e.models.length} | \`${e.sha256.slice(0, 12)}\` | ${e.status} |`);
  }
  lines.push('');
}
fs.writeFileSync(path.join(outDir, 'WORKFLOWS.md'), lines.join('\n'), 'utf8');

console.log(`扫描 ${entries.length} 个工作流 → ${outDir}`);
for (const e of entries) if (e.parse_error) console.log('  解析失败: ' + e.path + ' — ' + e.parse_error);