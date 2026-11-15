#!/usr/bin/env node
// 把 ComfyUI 的 UI 格式工作流（nodes+links）转成 API 格式（节点字典），供 run.mjs 执行。
// 用法: node scripts/ui2api.mjs --workflow <x.json> [--out <y.api.json>]
//
// 为什么需要转换：UI 格式是"画布"，API 格式是"图"。两者结构完全不同，
// 而 /prompt 只接受后者。手写转换容易漏掉 control_after_generate 这类界面专有控件。
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const val = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const src = val('--workflow');

if (!src) { console.error('缺 --workflow <path>'); process.exitCode = 2; }
else {
  const abs = path.resolve(src);
  if (!fs.existsSync(abs)) { console.error('文件不存在: ' + abs); process.exitCode = 2; }
  else {
    const wf = JSON.parse(fs.readFileSync(abs, 'utf8'));
    if (!wf.nodes) { console.error('不是 UI 格式（缺 nodes）'); process.exitCode = 2; }
    else {
      const base = process.env.COMFYUI_BASE || 'http://127.0.0.1:8188';
      const info = await (await fetch(base + '/object_info')).json();

      // 只在前端存在、不是可执行节点的类型
      const UI_ONLY = new Set(['MarkdownNote', 'Note', 'Reroute', 'PrimitiveNode', 'Label (rgthree)', 'Fast Groups Bypasser (rgthree)']);
      const CONTROL = new Set(['fixed', 'randomize', 'increment', 'decrement']);

      // object_info 的输入定义有多种形态，不能一概而论：
      //   连线类型：  ["MODEL", {...}]                      首元素是字符串
      //   枚举：      [["euler","dpmpp_2m", ...], {...}]     首元素是数组
      //   基本类型：  ["INT", {...}] / ["STRING", {...}]
      //   组合类型：  ["FLOAT,INT", {...}]                  逗号分隔
      //   特殊控件：  ["COMFY_DYNAMICCOMBO_V3", {...}]      动态下拉（SaveVideo.format）
      //              ["COMFY_AUTOGROW_V3", {...}]          可增删多输入（Qwen images），非标量
      // 把连线类型当控件会让 widget 值整体错位；漏认枚举则必填项"消失"。
      const WIDGET_TYPES = new Set(['INT', 'FLOAT', 'STRING', 'BOOLEAN', 'COMBO',
        'COMFY_DYNAMICCOMBO_V3', 'COMFY_AUTOGROW_V3']);
      const MULTI_ONLY = new Set(['COMFY_AUTOGROW_V3']);

      const typeNames = spec => {
        const t = spec?.[0];
        if (Array.isArray(t)) return ['COMBO'];
        if (typeof t !== 'string') return [];
        return t.split(',').map(s => s.trim()).filter(Boolean);
      };
      const isWidget = spec => {
        if (!Array.isArray(spec)) return false;
        const names = typeNames(spec);
        return names.length > 0 && names.every(n => WIDGET_TYPES.has(n)) && !names.some(n => MULTI_ONLY.has(n));
      };

      // link_id -> [fromNode, fromSlot]
      const links = new Map();
      for (const l of (wf.links || [])) {
        if (Array.isArray(l)) links.set(l[0], [l[1], l[2]]);
        else if (l && l.id != null) links.set(l.id, [l.origin_id, l.origin_slot]);
      }

      const prompt = {};
      const problems = [];
      for (const node of wf.nodes) {
        if (!node.type || UI_ONLY.has(node.type)) continue;
        const def = info[node.type];
        if (!def) { problems.push(`节点 ${node.id} 类型不在 object_info: ${node.type}`); continue; }

        // 控件顺序：优先用 input_order，缺失时按 required/optional 顺序兜底
        const ordered = [];
        const ord = def.input_order || {};
        const pushFrom = group => {
          const names = (ord[group] && ord[group].length) ? ord[group] : Object.keys(def.input?.[group] || {});
          for (const name of names) {
            const spec = (def.input?.[group] || {})[name];
            if (spec && isWidget(spec)) ordered.push(name);
          }
        };
        pushFrom('required');
        pushFrom('optional');

        const inputs = {};
        const wv = node.widgets_values;
        if (Array.isArray(wv)) {
          let j = 0;
          for (let i = 0; i < ordered.length && j < wv.length; i++) {
            const name = ordered[i];
            // 界面专有控件 control_after_generate 紧跟在 seed 类输入后
            if (/seed/i.test(name) && j + 1 < wv.length && CONTROL.has(wv[j + 1])) { inputs[name] = wv[j]; j += 2; }
            else { inputs[name] = wv[j]; j += 1; }
          }
          if (j < wv.length) problems.push(`节点 ${node.id}(${node.type}) 有 ${wv.length - j} 个 widget 值没对上输入名`);
        } else if (wv && typeof wv === 'object') {
          for (const [k, v] of Object.entries(wv)) if (ordered.includes(k)) inputs[k] = v;
        }

        // 缺失的必填控件用节点定义里的默认值补齐
        // （节点升级后新增字段的老工作流靠这里救回，如 SaveVideo.format / LTXV frame_rate）
        const filled = [];
        for (const group of ['required', 'optional']) {
          for (const [name, spec] of Object.entries(def.input?.[group] || {})) {
            if (name in inputs) continue;
            if (!isWidget(spec)) continue;
            const opts = spec[1] || {};
            let v;
            if (opts.default !== undefined) v = opts.default;
            else if (Array.isArray(spec[0]) && spec[0].length) v = spec[0][0];
            else if (Array.isArray(opts.options) && opts.options.length) v = opts.options[0].key ?? opts.options[0];
            if (v !== undefined) { inputs[name] = v; filled.push(name); }
          }
        }
        if (filled.length) console.log('[INFO] 节点 ' + node.id + '(' + node.type + ') 用默认值补齐: ' + filled.join(', '));

        // 连线输入覆盖
        for (const inp of (node.inputs || [])) {
          if (inp.link == null) continue;
          const origin = links.get(inp.link);
          if (!origin) { problems.push(`节点 ${node.id} 的输入 ${inp.name} 指向不存在的连线 ${inp.link}`); continue; }
          inputs[inp.name] = [String(origin[0]), origin[1]];
        }
        prompt[String(node.id)] = { class_type: node.type, inputs };
      }

      const out = val('--out', path.join(path.dirname(abs), path.basename(abs, '.json') + '.api.json'));
      if (problems.length) { for (const p of problems) console.error('[WARN] ' + p); }
      fs.writeFileSync(out, JSON.stringify(prompt, null, 2), 'utf8');
      console.log(`转换完成: ${Object.keys(prompt).length} 个可执行节点 → ${out}`);
      if (problems.length) console.log(`警告 ${problems.length} 条，建议用 run.mjs --dry-run 复核`);
    }
  }
}
