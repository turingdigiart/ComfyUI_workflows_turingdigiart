#!/usr/bin/env node
// 扫描工作流目录，生成三份产物：
//   catalog/registry.json   机器读（含参数、说明、缺模型）
//   catalog/WORKFLOWS.md    人读总表（每条一行，带说明）
//   catalog/INDEX.md        按类别分组的检索索引（找"我要做什么"用）
//
// 用法: node scripts/catalog.mjs [--source <工作流目录>] [--out <catalog 目录>] [--models <模型根>]
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const args = process.argv.slice(2);
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const source = path.resolve(argOf('--source', process.env.COMFY_WORKFLOWS || 'E:/RAE_ToolRoot/comfyui/ComfyUI_windows_portable/ComfyUI/user/default/workflows'));
const outDir = path.resolve(argOf('--out', path.join(process.cwd(), 'catalog')));
const modelsRoot = path.resolve(argOf('--models', 'E:/RAE_ToolRoot/comfyui/ComfyUI_windows_portable/ComfyUI/models'));
const MODEL_EXT = /\.(safetensors|ckpt|pt|pth|gguf|bin|onnx|sft)$/i;
const NOTE_TYPE = /^(MarkdownNote|Note)$/i;

function walk(dir, acc = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, acc);
    else if (e.name.endsWith('.json')) acc.push(p);
  }
  return acc;
}

// 模型索引（只按文件名，避免每次扫全盘）
const onDisk = new Set();
if (fs.existsSync(modelsRoot)) {
  (function scan(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) scan(p); else if (MODEL_EXT.test(e.name)) onDisk.add(e.name.toLowerCase());
    }
  })(modelsRoot);
}

const clean = s => String(s || '').replace(/\r/g, '').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
const firstLine = s => (clean(s).split('\n').find(l => l.trim()) || '').replace(/^#+\s*/, '').slice(0, 120);

const files = walk(source).sort();
const entries = [];
for (const file of files) {
  const rel = path.relative(source, file).replace(/\\/g, '/');
  const raw = fs.readFileSync(file);
  let json = null, parseError = null;
  try { json = JSON.parse(raw.toString('utf8')); } catch (e) { parseError = e.message; }

  const nodes = json?.nodes || [];
  const modelRefs = new Set();
  let description = '', noteTitle = '';
  const p = { model: null, resolution: null, steps: null, sampler: null, frames: null, fps: null };

  for (const n of nodes) {
    const v = n.widgets_values || [];
    for (const x of v) if (typeof x === 'string' && MODEL_EXT.test(x)) modelRefs.add(x);
    if (NOTE_TYPE.test(n.type || '')) {
      const t = clean(v[0]);
      if (t && !description) description = t;
      if (!noteTitle && n.title) noteTitle = n.title;
      continue;
    }
    if ((n.type === 'CheckpointLoaderSimple' || n.type === 'UNETLoader') && !p.model && typeof v[0] === 'string') p.model = v[0];
    if (/^(EmptyLatentImage|EmptySD3LatentImage)$/.test(n.type || '') && !p.resolution) p.resolution = `${v[0]}x${v[1]}`;
    if (/^Empty.*(Latent)?Video/.test(n.type || '') && !p.frames) p.frames = v[0];
    if (n.type === 'KSampler') { if (p.steps == null) p.steps = v[2]; if (!p.sampler) p.sampler = v[4]; }
  }

  const list = [...modelRefs];
  const missing = list.filter(m => !onDisk.has(m.toLowerCase()));
  const name = path.basename(file, '.json');
  const vm = name.match(/_v(\d{3})_?/);
  const dirParts = rel.split('/');
  const category = dirParts.length > 1 ? dirParts[0] : '未分类';
  const subcategory = dirParts.length > 2 ? dirParts[1] : '';

  entries.push({
    workflow_id: rel.replace(/\.json$/, '').replace(/[\\/]/g, '-').toLowerCase(),
    path: rel,
    category,
    subcategory,
    name,
    title: firstLine(description) || noteTitle || name,
    description: description.slice(0, 600),
    has_description: Boolean(description),
    version: vm ? 'v' + vm[1] : null,
    sha256: crypto.createHash('sha256').update(raw).digest('hex'),
    bytes: raw.length,
    node_count: nodes.length,
    node_types: [...new Set(nodes.map(n => n.type).filter(Boolean))],
    models: list.sort(),
    missing_models: missing,
    params: p,
    parse_error: parseError,
    status: parseError ? 'Broken' : 'Candidate'
  });
}

const registry = {
  schema: 2,
  generated_at: new Date().toISOString(),
  source,
  count: entries.length,
  missing_model_count: entries.filter(e => e.missing_models.length).length,
  undocumented_count: entries.filter(e => !e.has_description).length,
  workflows: entries
};

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'registry.json'), JSON.stringify(registry, null, 2), 'utf8');

const fmtParams = e => {
  const parts = [];
  if (e.params.model) parts.push(e.params.model.replace(/\.(safetensors|ckpt)$/, ''));
  if (e.params.resolution) parts.push(e.params.resolution);
  if (e.params.steps != null) parts.push(e.params.steps + ' 步');
  if (e.params.frames != null) parts.push(e.params.frames + ' 帧');
  if (e.params.sampler) parts.push(e.params.sampler);
  return parts.join(' · ') || '—';
};

const byCat = new Map();
for (const e of entries) {
  if (!byCat.has(e.category)) byCat.set(e.category, []);
  byCat.get(e.category).push(e);
}

// ---- WORKFLOWS.md：总表 ----
const t1 = [
  '# 工作流台账',
  '',
  '> 由 `scripts/catalog.mjs` 生成，**不要手改**。改工作流后重跑脚本。',
  `> 生成时间：${registry.generated_at}`,
  `> 来源目录：\`${source}\``,
  `> 共 ${entries.length} 条｜缺模型 ${registry.missing_model_count} 条｜缺说明 ${registry.undocumented_count} 条`,
  '',
  '## 分类分布',
  '',
  '| 类别 | 数量 |',
  '|---|---:|',
  ...[...byCat].map(([c, l]) => `| ${c} | ${l.length} |`),
  ''
];
for (const [cat, list] of byCat) {
  t1.push(`## ${cat}`, '', '| 工作流 | 说明 | 参数 | 模型 | 校验 |', '|---|---|---|---|:--:|');
  for (const e of list.sort((a, b) => a.path.localeCompare(b.path))) {
    const flag = e.parse_error ? '❌解析' : (e.missing_models.length ? '⚠️缺模型' : '✅');
    t1.push(`| \`${e.path}\` | ${e.title.replace(/\|/g, '/')} | ${fmtParams(e)} | ${e.models.length} | ${flag} |`);
  }
  t1.push('');
}
fs.writeFileSync(path.join(outDir, 'WORKFLOWS.md'), t1.join('\n'), 'utf8');

// ---- INDEX.md：按"我要做什么"检索 ----
const t2 = [
  '# 工作流索引（按用途找）',
  '',
  '> 由 `scripts/catalog.mjs` 生成。想"做什么"就来这里找，找到路径后用 `run.mjs` 调用。',
  '',
  '## 按类别',
  ''
];
for (const [cat, list] of byCat) {
  t2.push(`### ${cat}（${list.length}）`, '');
  for (const e of list.sort((a, b) => a.path.localeCompare(b.path))) {
    t2.push(`**${e.name}**${e.missing_models.length ? '  ⚠️ 缺模型' : ''}`);
    t2.push(`- 路径：\`${e.path}\``);
    t2.push(`- 参数：${fmtParams(e)}`);
    if (e.models.length) t2.push(`- 模型：${e.models.join('、')}`);
    if (e.has_description) t2.push(`- 说明：${e.title}`);
    else t2.push('- 说明：（画布里没有说明节点，靠文件名判断）');
    t2.push('');
  }
}

const noDoc = entries.filter(e => !e.has_description);
if (noDoc.length) {
  t2.push('## 待补说明', '', '这些工作流的画布里没有 MarkdownNote，建议补一条用途说明：', '');
  for (const e of noDoc) t2.push(`- \`${e.path}\``);
  t2.push('');
}
const missModel = entries.filter(e => e.missing_models.length);
if (missModel.length) {
  t2.push('## 缺模型', '', '| 工作流 | 缺的模型 |', '|---|---|');
  for (const e of missModel) t2.push(`| \`${e.path}\` | ${e.missing_models.join('、')} |`);
  t2.push('');
}
fs.writeFileSync(path.join(outDir, 'INDEX.md'), t2.join('\n'), 'utf8');

console.log(`扫描 ${entries.length} 条 → ${outDir}`);
console.log(`  缺模型 ${registry.missing_model_count} 条；缺说明 ${registry.undocumented_count} 条；模型目录 ${onDisk.size} 个文件`);
for (const e of entries) if (e.parse_error) console.log('  解析失败: ' + e.path + ' — ' + e.parse_error);
