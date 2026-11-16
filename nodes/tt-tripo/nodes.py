"""tt-tripo：机构自研 Tripo API 调用节点（文生 3D）。

两个节点：
- TTTripoSubmit：POST /generation/text-to-model 提交生成任务（enable_api 默认关，防误扣费）。
- TTTripoFetch：GET /tasks/{task_id} 轮询取回，下载 GLB 与渲染预览图，不自动重试提交（防重复计费）。

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


def _download_image(cfg, url):
    r = requests.get(url, timeout=int(cfg.get("request_timeout") or 120))
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def _download_model(cfg, url, task_id):
    out_dir = os.path.join(folder_paths.get_output_directory(), "Tripo")
    os.makedirs(out_dir, exist_ok=True)
    local = os.path.join(out_dir, task_id + ".glb")
    r = requests.get(url, timeout=max(int(cfg.get("request_timeout") or 60), 120))
    r.raise_for_status()
    with open(local, "wb") as f:
        f.write(r.content)
    return local


class TTTripoSubmit:
    """提交文生 3D 任务；enable_api=false 时不发任何网络请求。"""

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
            return ("", "enable_api 未开启：未发起任何网络请求。确认参数与预算后打开 enable_api。")
        if not cfg["api_key"]:
            return ("", _no_key_msg())
        if not prompt or not prompt.strip():
            return ("", "prompt 为空：文生 3D 需要 prompt（≤1024 字符）。")
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
            return ("", "提交失败（网络/配置）：{0}".format(e))
        if not isinstance(data, dict) or data.get("code") != 0:
            if isinstance(data, dict):
                code = data.get("code")
                msg = data.get("message") or data.get("msg") or ""
            else:
                code, msg = None, ""
            return ("", "提交失败：code={0} msg={1}".format(code, msg))
        task_id = ((data.get("data") or {}).get("task_id") or "").strip()
        if not task_id:
            return ("", "提交失败：响应缺少 task_id。")
        info = "已提交：task_id={0}；model={1}；texture={2}；pbr={3}；face_limit={4}；seed={5}（0=不传 model_seed）".format(
            task_id, model, bool(texture), bool(pbr), int(face_limit), int(seed)
        )
        return (task_id, info)


class TTTripoFetch:
    """轮询任务并取回结果；超时/终态返回可读状态字符串，不自动重试提交。"""

    CATEGORY = "TT"
    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("模型路径", "预览图", "状态")
    FUNCTION = "run"
    OUTPUT_NODE = False

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
        if not task_id:
            return ("", blank, "task_id 为空：请先连线 TTTripoSubmit 的 task_id 输出，或手工粘贴任务 ID。")
        if not cfg["api_key"]:
            return ("", blank, _no_key_msg())
        interval = max(1, int(cfg.get("poll_interval") or poll_interval or 5))
        deadline = time.time() + int(wait_seconds)
        status = "unknown"
        while time.time() < deadline:
            try:
                data = _request_json(cfg, "GET", "/tasks/" + task_id)
            except Exception as e:
                return ("", blank, "查询失败（网络/配置）：{0}".format(e))
            if not isinstance(data, dict) or data.get("code") != 0:
                code = (data or {}).get("code") if isinstance(data, dict) else None
                return ("", blank, "查询失败：code={0}".format(code))
            d = data.get("data") or {}
            status = d.get("status") or "unknown"
            if status == "success":
                break
            if status in ("failed", "cancelled", "banned", "expired"):
                return (
                    "",
                    blank,
                    "任务终态 {0}：error_code={1} error_message={2}".format(
                        status, d.get("error_code"), d.get("error_message", "")
                    ),
                )
            # queued / running / unknown：继续轮询，不重复提交
            time.sleep(interval)
        else:
            return ("", blank, "等待超时（{0}s）：任务仍为 {1}。可用同一 task_id 再次取回，无需重新提交。".format(int(wait_seconds), status))
        out = d.get("output") or {}
        model_url = out.get("model_url") or ""
        image_url = out.get("rendered_image_url") or ""
        local_path = ""
        try:
            if model_url:
                local_path = _download_model(cfg, model_url, task_id)
        except Exception as e:
            return ("", blank, "GLB 下载失败：{0}".format(e))
        image = blank
        try:
            if image_url:
                image = _download_image(cfg, image_url)
        except Exception as e:
            return (local_path, blank, "success（模型已下载）；预览图下载失败：{0}".format(e))
        return (
            local_path,
            image,
            "success：模型 {0}；预览图 {1}；credits_consumed={2}".format(
                local_path or model_url, "已下载" if image_url else "未提供", d.get("credits_consumed")
            ),
        )


NODE_CLASS_MAPPINGS = {
    "TTTripoSubmit": TTTripoSubmit,
    "TTTripoFetch": TTTripoFetch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TTTripoSubmit": "TT-Tripo 提交（文生3D）",
    "TTTripoFetch": "TT-Tripo 任务取回",
}
