#!/usr/bin/env node
// 按 API 格式的 prompt 执行工作流：先校验，再排队，再等结果。
// 注意：ComfyUI 保存的工作流是 UI 格式；执行前需在 UI 里「导出(API)」得到 *api.json。
// 用法:
//   node scripts/run.mjs --prompt <api.json> --dry-run
//   node scripts/run.mjs --prompt <api.json> --set 6.text="一只猫" --wait
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const has = k => args.includes(k);
const val = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const all = k => args.map((a, i) => a === k ? args[i + 1] : null).filter(Boolean);
const base = process.env.COMFYUI_BASE || 'http://127.0.0.1:8188';

const promptPath = val('--prompt');
if (!promptPath) { console.error('缺 --prompt <api.json>'); process.exitCode = 2; }
else {
  let prompt;
  try { prompt = JSON.parse(fs.readFileSync(path.resolve(promptPath), 'utf8')); }
  catch (e) { console.error('读取失败: ' + e.message); process.exitCode = 2; }

  if (prompt && prompt.prompt) prompt = prompt.prompt;   // 兼容 {"prompt":{...}} 包装

  // --set <nodeId>.<input>=<value>，值按 JSON 解析，失败则当字符串
  for (const spec of all('--set')) {
    const m = spec.match(/^([^.]+)\.([^=]+)=(.*)$/s);
    if (!m) { console.error('--set 格式错误: ' + spec); process.exitCode = 2; break; }
    const [, nodeId, input, rawVal] = m;
    if (!prompt[nodeId]) { console.error('节点不存在: ' + nodeId); process.exitCode = 2; break; }
    let v; try { v = JSON.parse(rawVal); } catch { v = rawVal; }
    prompt[nodeId].inputs[input] = v;
  }

  if (process.exitCode === 2) { /* 参数错误，已在上面报出 */ }
  else {
    const info = await (await fetch(base + '/object_info')).json();
    const problems = [];
    for (const [id, node] of Object.entries(prompt)) {
      if (!node || !node.class_type) { problems.push(`节点 ${id} 缺 class_type`); continue; }
      const def = info[node.class_type];
      if (!def) { problems.push(`节点 ${id} 类型不存在: ${node.class_type}`); continue; }
      const required = Object.keys(def.input?.required || {});
      for (const r of required) if (!(r in (node.inputs || {}))) problems.push(`节点 ${id}(${node.class_type}) 缺必填输入: ${r}`);
      for (const k of Object.keys(node.inputs || {})) {
        if (!(k in (def.input?.required || {})) && !(k in (def.input?.optional || {}))) problems.push(`节点 ${id}(${node.class_type}) 未知输入: ${k}`);
      }
    }
    if (problems.length) { for (const p of problems) console.log('[FAIL] ' + p); console.log('校验失败，未执行。'); process.exitCode = 1; }
    else {
      console.log(`校验通过：${Object.keys(prompt).length} 个节点`);
      if (has('--dry-run')) { console.log('--dry-run，未排队。'); }
      else {
        const r = await fetch(base + '/prompt', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ prompt, client_id: 'tech-comfy-001' }) });
        const body = await r.json().catch(() => null);
        if (!r.ok) { console.log('[FAIL] 排队失败 ' + r.status + ' ' + JSON.stringify(body)); process.exitCode = 1; }
        else {
          const id = body.prompt_id;
          console.log('已排队 prompt_id=' + id);
          if (has('--wait')) {
            for (let i = 0; i < 600; i++) {
              await new Promise(res => setTimeout(res, 1000));
              const h = await (await fetch(base + '/history/' + encodeURIComponent(id))).json();
              const entry = h[id];
              if (entry) {
                const outs = [];
                for (const [nodeId, o] of Object.entries(entry.outputs || {})) for (const f of (o.images || [])) outs.push(`${f.subfolder ? f.subfolder + '/' : ''}${f.filename}`);
                console.log('完成，产出 ' + outs.length + ' 个文件:'); for (const o of outs) console.log('  ' + o);
                process.exitCode = 0; break;
              }
              if (i === 599) { console.log('[FAIL] 超时 600s'); process.exitCode = 1; }
            }
          }
        }
      }
    }
  }
}