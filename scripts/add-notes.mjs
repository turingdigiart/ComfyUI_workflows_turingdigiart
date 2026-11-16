#!/usr/bin/env node
// 给没有说明的工作流补一条 MarkdownNote。默认只报告，--apply 才写入。
// 说明文字明确标注：参数由连线自动读取，用途据文件名推断，不冒充人工确认。
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const apply = args.includes('--apply');
const root = path.resolve(process.env.COMFY_WORKFLOWS || 'workflows');
const MODEL_EXT = /\.(safetensors|ckpt|pt|pth|gguf|bin|onnx|sft)$/i;
const NOTE = /^(MarkdownNote|Note)$/i;

function walk(d, acc = []) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p, acc); else if (e.name.endsWith('.json')) acc.push(p);
  }
  return acc;
}

let added = 0, skipped = 0;
for (const file of walk(root).sort()) {
  const rel = path.relative(root, file).replace(/\\/g, '/');
  const wf = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!Array.isArray(wf.nodes)) continue;
  // 已有说明就跳过；但"有 Note 节点却内容为空"要补内容，而不是再插一条
  const existing = wf.nodes.find(n => NOTE.test(n.type || ''));
  const existingText = existing ? String((existing.widgets_values || [])[0] || '').trim() : '';
  if (existing && existingText) { skipped++; continue; }

  const model = (() => { for (const n of wf.nodes) { const v = n.widgets_values || []; if ((n.type === 'CheckpointLoaderSimple' || n.type === 'UNETLoader') && typeof v[0] === 'string' && MODEL_EXT.test(v[0])) return v[0]; } return null; })();
  let res = null, steps = null, sampler = null, frames = null;
  for (const n of wf.nodes) {
    const v = n.widgets_values || [];
    if (/^EmptyLatentImage$/.test(n.type || '')) { res = res || `${v[0]}x${v[1]}`; }
    if (n.type === 'KSampler') { if (steps == null) steps = v[2]; sampler = sampler || v[4]; }
    if (/^Empty.*Video/.test(n.type || '')) frames = frames || v[0];
  }
  const parts = [];
  if (model) parts.push(`底模 ${model}`);
  if (res) parts.push(res);
  if (steps != null) parts.push(`${steps} 步`);
  if (sampler) parts.push(sampler);
  if (frames != null) parts.push(`${frames} 帧`);

  const dir = path.dirname(rel).split('/');
  const text = [
    `# ${path.basename(file, '.json')}`,
    '',
    `- 归类：${dir.join(' / ')}`,
    `- 参数：${parts.join(' · ') || '未从连线读到关键参数'}`,
    '- 说明：本条为 2026-11-16 迁入的既有工作流，画布原先没有说明。',
    '  上面的参数由节点连线自动读取；用途请看文件名，实际用法以连线为准。',
    '  需要补充准确用法时，直接改这条说明并重跑 catalog。'
  ].join('\n');

  if (existing) {
    // 空说明节点：直接填内容，不新增节点
    existing.widgets_values = [text];
    existing.title = existing.title || '使用说明（自动补）';
    added++;
    if (apply) fs.writeFileSync(file, JSON.stringify(wf, null, 2), 'utf8');
    console.log((apply ? '[填内容] ' : '[预案-填内容] ') + rel);
    continue;
  }

  const maxId = Math.max(0, ...wf.nodes.map(n => Number(n.id) || 0));
  const id = maxId + 1;
  wf.nodes.push({
    id,
    type: 'MarkdownNote',
    title: '使用说明（自动补）',
    pos: [0, -340],
    size: [700, 330],
    flags: {},
    order: id,
    mode: 0,
    properties: {},
    widgets_values: [text]
  });
  wf.last_node_id = Math.max(Number(wf.last_node_id) || 0, id);

  added++;
  if (apply) fs.writeFileSync(file, JSON.stringify(wf, null, 2), 'utf8');
  console.log((apply ? '[写入] ' : '[预案] ') + rel);
}
console.log(`--- 补说明 ${added} 条；已有说明跳过 ${skipped} 条；模式=${apply ? 'apply' : 'dry-run'}`);