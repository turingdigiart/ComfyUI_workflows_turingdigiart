"""tt-tripo：机构自研 Tripo API 调用节点（文生 3D）。

两个节点：
- TTTripoSubmit：POST /generation/text-to-model 提交生成任务（enable_api 默认关，防误扣费）。
- TTTripoFetch：GET /tasks/{task_id} 轮询取回，下载 GLB 与渲染预览图，不自动重试提交（防重复计费）。
  - OUTPUT_NODE=True：图以它收尾，输出（task_id/路径/状态）进入 /history 可取证；
  - 每次执行把 {task_id, status, model_path, preview_path, error, ts} 写入 output/Tripo/<task_id>.meta.json。

配置：插件目录 tripo.local.json（schema 见 tripo.local.json.example）；环境变量 TRIPO_API_KEY 优先。
Key 管理遵循 DEC-ORG-094「本机配置 + 中控只验证约束」：不入画布、不入同步盘。
付费调用属 P1：真实生成前确认预算，enable_api 默认关闭。
"""

import io
import json
import os
import time

import requests

# ComfyUI python_embeded 自带（见 requirements.txt 说明）
import folder_paths
import numpy as np
import torch
from PIL import Image

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_NAME = "tripo.local.json"

DEFAULT_CONFIG = {
    "base_url": "https://openapi.tripo3d.ai/v3",
    "api_key_env": "TRIPO_API_KEY",
    "api_key": "",
    "request_timeout": 60,
    "poll_interval": 5,
}

MODEL_OPTIONS = ["v3.1-20260211", "v3.0-20250812", "v2.5-20250123"]


def _load_config():
    cfg = dict(DEFAULT_CONFIG)
    path = os.path.join(PLUGIN_DIR, CONFIG_NAME)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k in DEFAULT_CONFIG:
                    if k in data:
                        cfg[k] = data[k]
        except Exception:
            # 配置损坏时回退默认值；网络调用会在缺 Key 时给出可读提示
            pass
    env_name = cfg.get("api_key_env") or DEFAULT_CONFIG["api_key_env"]
    env_key = os.environ.get(env_name, "")
    if env_key:
        cfg["api_key"] = env_key
    env_base = os.environ.get("TRIPO_BASE_URL", "")
    if env_base:
        cfg["base_url"] = env_base.rstrip("/")
    return cfg


def _no_key_msg():
    return (
        "未找到 API Key：请在本机插件目录 tt-tripo/tripo.local.json 填 api_key，"
        "或设置环境变量 TRIPO_API_KEY（DEC-ORG-094 本机配置模式，不经过聊天与同步盘）。"
    )


def _tripo_outdir():
    out = os.path.join(folder_paths.get_output_directory(), "Tripo")
    os.makedirs(out, exist_ok=True)
    return out


def _now_ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _write_meta(task_id, status, model_path, preview_path, error):
    """取证持久化：output/Tripo/<task_id>.meta.json（无任务 ID 时用时间戳文件名）。"""
    try:
        name = (task_id or ("no-task-" + _now_ts().replace(":", "").replace(" ", "-"))) + ".meta.json"
        data = {
            "task_id": task_id,
            "status": status,
            "model_path": model_path,
            "preview_path": preview_path,
            "error": error,
            "ts": _now_ts(),
        }
        with open(os.path.join(_tripo_outdir(), name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 取证写入失败不影响主流程


def _request_json(cfg, method, path, payload=None):
    url = cfg["base_url"].rstrip("/") + path
    headers = {"Authorization": "Bearer " + cfg["api_key"], "Content-Type": "application/json"}
    timeout = int(cfg.get("request_timeout") or 60)
    if method == "POST":
        r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    else:
        r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _blank_image():
    return torch.zeros((1, 1, 1, 3), dtype=torch.float32)


def _download_image(cfg, url, task_id):
    r = requests.get(url, timeout=int(cfg.get("request_timeout") or 120))
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    png = os.path.join(_tripo_outdir(), task_id + "_preview.png")
    img.save(png)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...], png


def _download_model(cfg, url, task_id):
    local = os.path.join(_tripo_outdir(), task_id + ".glb")
    r = requests.get(url, timeout=max(int(cfg.get("request_timeout") or 60), 120))
    r.raise_for_status()
    with open(local, "wb") as f:
        f.write(r.content)
    return local


class TTTripoSubmit:
    """提交文生 3D 任务；enable_api=false 时不发任何网络请求。
    失败时把「ERROR:<原因>」写入 task_id 输出（供 Fetch 透传取证），调用信息保留完整原因。"""

    CATEGORY = "TT"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("task_id", "调用信息")
    FUNCTION = "run"
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enable_api": ("BOOLEAN", {"default": False}),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "model": (MODEL_OPTIONS, {"default": "v3.1-20260211"}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "face_limit": ("INT", {"default": 100000, "min": -1, "max": 1000000}),
                "texture": ("BOOLEAN", {"default": True}),
                "pbr": ("BOOLEAN", {"default": True}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF}),
            }
        }

    def run(self, enable_api, prompt, model, negative_prompt, face_limit, texture, pbr, seed):
        cfg = _load_config()
        if not enable_api:
            return ("ERROR:enable_api 未开启：未发起任何网络请求。确认参数与预算后打开 enable_api。",
                    "enable_api 未开启：未发起任何网络请求。确认参数与预算后打开 enable_api。")
        if not cfg["api_key"]:
            return ("ERROR:" + _no_key_msg(), _no_key_msg())
        if not prompt or not prompt.strip():
            return ("ERROR:prompt 为空：文生 3D 需要 prompt（≤1024 字符）。",
                    "prompt 为空：文生 3D 需要 prompt（≤1024 字符）。")
        payload = {
            "prompt": prompt.strip(),
            "model": model,
            "texture": bool(texture),
            "pbr": bool(pbr),
            "face_limit": int(face_limit),
        }
        if negative_prompt and negative_prompt.strip():
            payload["negative_prompt"] = negative_prompt.strip()
        if int(seed) != 0:
            payload["model_seed"] = int(seed)
        try:
            data = _request_json(cfg, "POST", "/generation/text-to-model", payload)
        except Exception as e:
            return ("ERROR:提交失败（网络/配置）：{0}".format(e), "提交失败（网络/配置）：{0}".format(e))
        if not isinstance(data, dict) or data.get("code") != 0:
            if isinstance(data, dict):
                code = data.get("code")
                msg = data.get("message") or data.get("msg") or ""
            else:
                code, msg = None, ""
            err = "提交失败：code={0} msg={1}".format(code, msg)
            return ("ERROR:" + err, err)
        task_id = ((data.get("data") or {}).get("task_id") or "").strip()
        if not task_id:
            return ("ERROR:提交失败：响应缺少 task_id。", "提交失败：响应缺少 task_id。")
        info = "已提交：task_id={0}；model={1}；texture={2}；pbr={3}；face_limit={4}；seed={5}（0=不传 model_seed）".format(
            task_id, model, bool(texture), bool(pbr), int(face_limit), int(seed)
        )
        return (task_id, info)


class TTTripoFetch:
    """轮询任务并取回结果；OUTPUT_NODE=True（输出进入 /history 可取证），
    每次执行写 output/Tripo/<task_id>.meta.json 取证；不自动重试提交。"""

    CATEGORY = "TT"
    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("模型路径", "预览图", "状态")
    FUNCTION = "run"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": "", "forceInput": True}),
                "wait_seconds": ("INT", {"default": 600, "min": 1, "max": 86400}),
                "poll_interval": ("INT", {"default": 5, "min": 1, "max": 300}),
                "refresh_id": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF}),
            }
        }

    def run(self, task_id, wait_seconds, poll_interval, refresh_id):
        cfg = _load_config()
        blank = _blank_image()
        task_id = (task_id or "").strip()

        def finish(path, image, status, error):
            _write_meta(task_id or "", status, path or "", "", error)
            return {"ui": {"text": [status]}, "result": (path, image, status)}

        if task_id.startswith("ERROR:"):
            status = task_id
            return finish("", blank, status, status)
        if not task_id:
            status = "task_id 为空：请先连线 TTTripoSubmit 的 task_id 输出，或手工粘贴任务 ID。"
            return finish("", blank, status, status)
        if not cfg["api_key"]:
            status = _no_key_msg()
            return finish("", blank, status, status)
        interval = max(1, int(cfg.get("poll_interval") or poll_interval or 5))
        deadline = time.time() + int(wait_seconds)
        status = "unknown"
        while time.time() < deadline:
            try:
                data = _request_json(cfg, "GET", "/tasks/" + task_id)
            except Exception as e:
                status = "查询失败（网络/配置）：{0}".format(e)
                return finish("", blank, status, status)
            if not isinstance(data, dict) or data.get("code") != 0:
                code = (data or {}).get("code") if isinstance(data, dict) else None
                status = "查询失败：code={0}".format(code)
                return finish("", blank, status, status)
            d = data.get("data") or {}
            status = d.get("status") or "unknown"
            if status == "success":
                break
            if status in ("failed", "cancelled", "banned", "expired"):
                status = "任务终态 {0}：error_code={1} error_message={2}".format(
                    status, d.get("error_code"), d.get("error_message", "")
                )
                return finish("", blank, status, status)
            # queued / running / unknown：继续轮询，不重复提交
            time.sleep(interval)
        else:
            status = "等待超时（{0}s）：任务仍为 {1}。可用同一 task_id 再次取回，无需重新提交。".format(int(wait_seconds), status)
            return finish("", blank, status, status)
        out = d.get("output") or {}
        model_url = out.get("model_url") or ""
        image_url = out.get("rendered_image_url") or ""
        local_path = ""
        try:
            if model_url:
                local_path = _download_model(cfg, model_url, task_id)
        except Exception as e:
            status = "GLB 下载失败：{0}".format(e)
            return finish("", blank, status, status)
        image = blank
        preview_path = ""
        try:
            if image_url:
                image, preview_path = _download_image(cfg, image_url, task_id)
        except Exception as e:
            status = "success（模型已下载）；预览图下载失败：{0}".format(e)
            _write_meta(task_id, status, local_path, "", str(e))
            return {"ui": {"text": [status]}, "result": (local_path, blank, status)}
        status = "success：模型 {0}；预览图 {1}；credits_consumed={2}".format(
            local_path or model_url, preview_path or ("已下载" if image_url else "未提供"), d.get("credits_consumed")
        )
        _write_meta(task_id, status, local_path, preview_path, "")
        return {"ui": {"text": [status]}, "result": (local_path, image, status)}


NODE_CLASS_MAPPINGS = {
    "TTTripoSubmit": TTTripoSubmit,
    "TTTripoFetch": TTTripoFetch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TTTripoSubmit": "TT-Tripo 提交（文生3D）",
    "TTTripoFetch": "TT-Tripo 任务取回",
}
