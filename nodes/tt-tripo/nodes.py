"""tt-tripo：机构自研 Tripo API 调用节点（文生 / 图生 / 多视图生 3D）。

四个节点：
- TTTripoSubmit：POST /generation/text-to-model 提交生成任务（enable_api 默认关，防误扣费）。
- TTTripoImageTo3D：IMAGE → 上传 /files → POST /generation/image-to-model（input=file_token）。
- TTTripoMultiviewTo3D：2–4 张视图（连接顺序=front/left/back/right）→ 逐张上传 → POST /generation/multiview-to-model（inputs 用 view-key 格式）。
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
import tempfile
import time

import requests

# ComfyUI python_embeded 自带（见 requirements.txt 说明）
import comfy.model_management
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


def _write_meta(task_id, status, model_path, preview_path, error, ext="", retries=0, recovered=False):
    """取证持久化：output/Tripo/<task_id>.meta.json（无任务 ID 时用时间戳文件名）。
    ext=模型文件扩展名（如 .fbx）；retries=实际重试次数；recovered=是否经重试/续传恢复。"""
    try:
        name = (task_id or ("no-task-" + _now_ts().replace(":", "").replace(" ", "-"))) + ".meta.json"
        data = {
            "task_id": task_id,
            "status": status,
            "model_path": model_path,
            "preview_path": preview_path,
            "error": error,
            "retries": int(retries or 0),
            "recovered": bool(recovered),
            "ts": _now_ts(),
        }
        if ext:
            data["ext"] = ext
            data["format"] = ext.lstrip(".").upper()
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


NET_RETRIES = 3
BACKOFF_SECONDS = [2, 4, 8]


def _check_interrupted():
    comfy.model_management.throw_exception_if_processing_interrupted()


def _sleep_interruptible(seconds):
    end = time.time() + seconds
    while time.time() < end:
        _check_interrupted()
        time.sleep(min(1.0, end - time.time()))


def _is_network_error(e):
    """仅网络类异常可重试（连接错误/超时/代理故障/流中断）；HTTP 状态错误与业务错误不重试。"""
    return isinstance(e, (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
    ))


def _request_json_retry(cfg, method, path, payload=None, max_retries=NET_RETRIES):
    """查询任务状态（GET）带网络类有界重试：最多 max_retries 次、指数退避 2/4/8 秒、期间可中断。
    业务错误（code!=0）不抛异常、不重试，由调用方处理。返回 (data, attempts)。"""
    attempts = 0
    while True:
        attempts += 1
        try:
            return _request_json(cfg, method, path, payload), attempts
        except requests.exceptions.RequestException as e:
            if not _is_network_error(e) or attempts > max_retries:
                raise
            _sleep_interruptible(BACKOFF_SECONDS[min(attempts - 1, len(BACKOFF_SECONDS) - 1)])


def _download_bytes_resumable(url, dest_path, timeout, max_retries=NET_RETRIES):
    """有界下载 + HTTP Range 断点续传：网络中断后从 .part 已下载字节续传；校验最终大小与
    Content-Length 一致（不一致视为失败并重试）。返回 (retries, recovered)。"""
    tmp = dest_path + ".part"
    retries = 0
    recovered = False
    for attempt in range(1, max_retries + 1):
        existing = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        headers = {"Range": "bytes={0}-".format(existing)} if existing > 0 else {}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                if existing > 0 and r.status_code == 206:
                    total = existing + int(r.headers.get("Content-Length") or 0)
                    mode = "ab"
                    recovered = True
                else:
                    total = int(r.headers.get("Content-Length") or 0)
                    mode = "wb"
                    existing = 0
                with open(tmp, mode) as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            size = os.path.getsize(tmp)
            if total and size != total:
                raise RuntimeError("下载不完整：已收 {0}/{1} 字节".format(size, total))
            if not total and size <= 0:
                raise RuntimeError("下载为空文件且无 Content-Length。")
            os.replace(tmp, dest_path)
            return retries, recovered
        except requests.exceptions.RequestException as e:
            retries += 1
            if attempt >= max_retries or not _is_network_error(e):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            _sleep_interruptible(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
        except RuntimeError:
            # 大小校验不一致：已有部分字节视为断点，继续重试
            retries += 1
            if attempt >= max_retries:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            _sleep_interruptible(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
    raise RuntimeError("下载失败（已重试 {0} 次）".format(max_retries))


def _blank_image():
    return torch.zeros((1, 1, 1, 3), dtype=torch.float32)


def _download_image(cfg, url, task_id):
    png = os.path.join(_tripo_outdir(), task_id + "_preview.png")
    tmp = png + ".dl"
    retries, recovered = _download_bytes_resumable(url, tmp, int(cfg.get("request_timeout") or 120))
    img = Image.open(tmp).convert("RGB")
    img.save(png)
    try:
        os.unlink(tmp)
    except OSError:
        pass
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...], png, retries, recovered


_MODEL_EXTS = [".fbx", ".obj", ".glb", ".gltf", ".stl", ".3mf", ".usdz"]


def _model_ext(url):
    """从 model_url 的 URL 后缀推断扩展名（忽略查询串）；无法推断回退 .glb。"""
    path = (url or "").split("?")[0].strip().lower()
    for ext in _MODEL_EXTS:
        if path.endswith(ext):
            return ext
    return ".glb"


def _download_model(cfg, url, task_id):
    ext = _model_ext(url)
    local = os.path.join(_tripo_outdir(), task_id + ext)
    retries, recovered = _download_bytes_resumable(url, local, max(int(cfg.get("request_timeout") or 60), 120))
    return local, ext, retries, recovered


def _upload_image(cfg, tensor):
    """IMAGE tensor → 临时 PNG → multipart POST {base}/files → file_token；上传后清理临时文件。"""
    arr = (tensor[0].clamp(0, 1).cpu().numpy() * 255.0 + 0.5).astype(np.uint8)
    img = Image.fromarray(arr, "RGB")
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    try:
        tmp.close()
        img.save(tmp.name, format="PNG")
        with open(tmp.name, "rb") as f:
            r = requests.post(
                cfg["base_url"].rstrip("/") + "/files",
                files={"file": ("upload.png", f, "image/png")},
                headers={"Authorization": "Bearer " + cfg["api_key"]},
                timeout=int(cfg.get("request_timeout") or 120),
            )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict) or data.get("code") != 0:
            code = data.get("code") if isinstance(data, dict) else None
            msg = (data.get("message") or data.get("msg") or "") if isinstance(data, dict) else ""
            raise RuntimeError("上传失败：code={0} msg={1}".format(code, msg))
        token = ((data.get("data") or {}).get("file_token") or "").strip()
        if not token:
            raise RuntimeError("上传失败：响应缺少 file_token。")
        return token
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


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
    每次执行写 output/Tripo/<task_id>.meta.json 取证（含 retries/recovered）；
    查询与下载对网络类异常做有界重试（2/4/8s 退避）+ HTTP Range 断点续传，**绝不重试提交**。"""

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

        def finish(path, image, status, error, retries=0, recovered=False):
            _write_meta(task_id or "", status, path or "", "", error, "", retries, recovered)
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
        total_retries = 0
        recovered = False
        while time.time() < deadline:
            try:
                data, attempts = _request_json_retry(cfg, "GET", "/tasks/" + task_id)
                if attempts > 1:
                    total_retries += attempts - 1
                    recovered = True
            except Exception as e:
                status = "查询失败（网络/配置，已重试 {0} 次）：{1}".format(total_retries, e)
                return finish("", blank, status, status, total_retries, recovered)
            if not isinstance(data, dict) or data.get("code") != 0:
                code = (data or {}).get("code") if isinstance(data, dict) else None
                status = "查询失败：code={0}".format(code)
                return finish("", blank, status, status, total_retries, recovered)
            d = data.get("data") or {}
            status = d.get("status") or "unknown"
            if status == "success":
                break
            if status in ("failed", "cancelled", "banned", "expired"):
                status = "任务终态 {0}：error_code={1} error_message={2}".format(
                    status, d.get("error_code"), d.get("error_message", "")
                )
                return finish("", blank, status, status, total_retries, recovered)
            # queued / running / unknown：继续轮询，不重复提交
            _sleep_interruptible(interval)
        else:
            status = "等待超时（{0}s）：任务仍为 {1}。可用同一 task_id 再次取回，无需重新提交。".format(int(wait_seconds), status)
            return finish("", blank, status, status, total_retries, recovered)
        out = d.get("output") or {}
        model_url = out.get("model_url") or ""
        image_url = out.get("rendered_image_url") or ""
        local_path = ""
        ext = ""
        try:
            if model_url:
                local_path, ext, dl_retries, dl_recovered = _download_model(cfg, model_url, task_id)
                total_retries += dl_retries
                recovered = recovered or dl_recovered
        except Exception as e:
            status = "模型下载失败（含 {0} 次下载重试）：{1}".format(total_retries, e)
            return finish("", blank, status, status, total_retries, recovered)
        image = blank
        preview_path = ""
        try:
            if image_url:
                image, preview_path, dl_retries, dl_recovered = _download_image(cfg, image_url, task_id)
                total_retries += dl_retries
                recovered = recovered or dl_recovered
        except Exception as e:
            status = "success（模型已下载{0}）；预览图下载失败：{1}".format(ext, e)
            _write_meta(task_id, status, local_path, "", str(e), ext, total_retries, recovered)
            return {"ui": {"text": [status]}, "result": (local_path, blank, status)}
        status = "success：模型 {0}；预览图 {1}；credits_consumed={2}".format(
            local_path or model_url, preview_path or ("已下载" if image_url else "未提供"), d.get("credits_consumed")
        )
        _write_meta(task_id, status, local_path, preview_path, "", ext, total_retries, recovered)
        return {"ui": {"text": [status]}, "result": (local_path, image, status)}


class TTTripoImageTo3D:
    """图生 3D：IMAGE → 上传 /files → POST /generation/image-to-model（input=file_token）。
    enable_api=false 不发任何请求；失败把 ERROR:<原因> 写入 task_id 输出。"""

    CATEGORY = "TT"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("task_id", "调用信息")
    FUNCTION = "run"
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {}),
                "enable_api": ("BOOLEAN", {"default": False}),
                "model": (MODEL_OPTIONS, {"default": "v3.1-20260211"}),
                "face_limit": ("INT", {"default": 100000, "min": -1, "max": 1000000}),
                "texture": ("BOOLEAN", {"default": True}),
                "pbr": ("BOOLEAN", {"default": True}),
                "texture_alignment": (["original_image", "geometry"], {"default": "original_image"}),
                "orientation": (["default", "align_image"], {"default": "default"}),
                "enable_image_autofix": ("BOOLEAN", {"default": False}),
            }
        }

    def run(self, image, enable_api, model, face_limit, texture, pbr, texture_alignment, orientation, enable_image_autofix):
        cfg = _load_config()
        if not enable_api:
            return ("ERROR:enable_api 未开启：未发起任何网络请求。确认参数与预算后打开 enable_api。",
                    "enable_api 未开启：未发起任何网络请求。确认参数与预算后打开 enable_api。")
        if not cfg["api_key"]:
            return ("ERROR:" + _no_key_msg(), _no_key_msg())
        try:
            token = _upload_image(cfg, image)
        except Exception as e:
            err = "图片上传失败：{0}".format(e)
            return ("ERROR:" + err, err)
        payload = {
            "input": token,
            "model": model,
            "texture": bool(texture),
            "pbr": bool(pbr),
            "face_limit": int(face_limit),
            "texture_alignment": texture_alignment,
            "orientation": orientation,
            "enable_image_autofix": bool(enable_image_autofix),
        }
        try:
            data = _request_json(cfg, "POST", "/generation/image-to-model", payload)
        except Exception as e:
            err = "提交失败（网络/配置）：{0}".format(e)
            return ("ERROR:" + err, err)
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
        info = "已提交：task_id={0}；model={1}；texture={2}；pbr={3}；face_limit={4}；texture_alignment={5}；orientation={6}；autofix={7}".format(
            task_id, model, bool(texture), bool(pbr), int(face_limit), texture_alignment, orientation, bool(enable_image_autofix)
        )
        return (task_id, info)


class TTTripoMultiviewTo3D:
    """多视图生 3D：images 单 IMAGE 输入承载图像批次（2–4 张，batch 顺序 = front/left/back/right，第一张视为 front）
    → 逐张上传 /files → POST /generation/multiview-to-model（inputs 为 view-key 格式）。
    多图用 ComfyUI 自带 ImageBatch 串联成单链输入（4 张 = 3 个 ImageBatch）。"""

    CATEGORY = "TT"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("task_id", "调用信息")
    FUNCTION = "run"
    OUTPUT_NODE = False
    VIEW_KEYS = ["front", "left", "back", "right"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {}),
                "enable_api": ("BOOLEAN", {"default": False}),
                "model": (MODEL_OPTIONS, {"default": "v3.1-20260211"}),
                "face_limit": ("INT", {"default": 100000, "min": -1, "max": 1000000}),
                "texture": ("BOOLEAN", {"default": True}),
                "pbr": ("BOOLEAN", {"default": True}),
                "orientation": (["default", "align_image"], {"default": "default"}),
            }
        }

    def run(self, images, enable_api, model, face_limit, texture, pbr, orientation):
        cfg = _load_config()
        # 单 IMAGE 输入承载批次：batch 张量 (B,H,W,C) 按 batch 维拆分；3D 单张包装成列表。
        if not isinstance(images, (list, tuple)):
            images = [images] if images.ndim == 3 else [images[i] for i in range(images.shape[0])]
        count = len(images)
        if not enable_api:
            return ("ERROR:enable_api 未开启：未发起任何网络请求。确认参数与预算后打开 enable_api。",
                    "enable_api 未开启：未发起任何网络请求。确认参数与预算后打开 enable_api。")
        if count < 2 or count > 4:
            err = "视图数量 {0} 张：需要 2–4 张（batch 顺序=front/left/back/right，第一张视为 front，front 必填；多图请用 ImageBatch 串联成单链输入）。".format(count)
            return ("ERROR:" + err, err)
        if not cfg["api_key"]:
            return ("ERROR:" + _no_key_msg(), _no_key_msg())
        views = []
        try:
            for i, img in enumerate(images):
                token = _upload_image(cfg, img)
                views.append({self.VIEW_KEYS[i]: token})
        except Exception as e:
            err = "图片上传失败：{0}".format(e)
            return ("ERROR:" + err, err)
        payload = {
            "inputs": views,
            "model": model,
            "texture": bool(texture),
            "pbr": bool(pbr),
            "face_limit": int(face_limit),
            "orientation": orientation,
        }
        try:
            data = _request_json(cfg, "POST", "/generation/multiview-to-model", payload)
        except Exception as e:
            err = "提交失败（网络/配置）：{0}".format(e)
            return ("ERROR:" + err, err)
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
        info = "已提交：task_id={0}；views={1}；model={2}；texture={3}；pbr={4}；face_limit={5}；orientation={6}".format(
            task_id, ",".join(self.VIEW_KEYS[:count]), model, bool(texture), bool(pbr), int(face_limit), orientation
        )
        return (task_id, info)


class TTTripoConvert:
    """格式转换：POST /models/convert 把已有生成任务转为 FBX/OBJ/GLTF/USDZ/STL/3MF（异步，返回新 task_id）。
    quad=true 会强制输出 FBX；OBJ 无动画、STL/3MF 仅几何。转换任务用 TTTripoFetch 轮询取回。"""

    CATEGORY = "TT"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("task_id", "调用信息")
    FUNCTION = "run"
    OUTPUT_NODE = False
    FORMAT_OPTIONS = ["FBX", "OBJ", "GLTF", "USDZ", "STL", "3MF"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": "", "tooltip": "粘贴已成功生成任务的 ID；也可在 UI 把本 widget 转输入槽，连线 Submit/ImageTo3D/MultiviewTo3D 的 task_id 输出"}),
                "enable_api": ("BOOLEAN", {"default": False}),
                "format": (cls.FORMAT_OPTIONS, {"default": "FBX"}),
                "quad": ("BOOLEAN", {"default": False}),
                "face_limit": ("INT", {"default": 0, "min": 0, "max": 10000000, "tooltip": "0=不传；quad=true 且未设置时平台默认 1 万面"}),
                "texture_size": ("INT", {"default": 4096, "min": 0, "max": 8192}),
            }
        }

    def run(self, task_id, enable_api, format, quad, face_limit, texture_size):
        cfg = _load_config()
        src = (task_id or "").strip()
        if not enable_api:
            return ("ERROR:enable_api 未开启：未发起任何网络请求。确认参数与预算后打开 enable_api。",
                    "enable_api 未开启：未发起任何网络请求。确认参数与预算后打开 enable_api。")
        if not src:
            err = "task_id 为空：粘贴已有生成任务的 ID，或从 Submit/ImageTo3D/MultiviewTo3D 的 task_id 连线。"
            return ("ERROR:" + err, err)
        if not cfg["api_key"]:
            return ("ERROR:" + _no_key_msg(), _no_key_msg())
        fmt = str(format or "FBX").upper()
        if fmt not in self.FORMAT_OPTIONS:
            err = "format 值无效：{0}（可选 {1}）。".format(format, "/".join(self.FORMAT_OPTIONS))
            return ("ERROR:" + err, err)
        quad = bool(quad)
        fl = int(face_limit or 0)
        ts = int(texture_size or 4096)
        payload = {"input": src, "format": fmt, "quad": quad, "texture_size": ts}
        if fl > 0:
            payload["face_limit"] = fl
        try:
            data = _request_json(cfg, "POST", "/models/convert", payload)
        except Exception as e:
            err = "转换提交失败（网络/配置）：{0}".format(e)
            return ("ERROR:" + err, err)
        if not isinstance(data, dict) or data.get("code") != 0:
            if isinstance(data, dict):
                code = data.get("code")
                msg = data.get("message") or data.get("msg") or ""
            else:
                code, msg = None, ""
            err = "转换提交失败：code={0} msg={1}".format(code, msg)
            return ("ERROR:" + err, err)
        cid = ((data.get("data") or {}).get("task_id") or "").strip()
        if not cid:
            return ("ERROR:转换提交失败：响应缺少 task_id。", "转换提交失败：响应缺少 task_id。")
        note = "；quad=true 将强制输出 FBX" if quad else ""
        info = "转换已提交：源任务={0}；convert_task_id={1}；format={2}；quad={3}；face_limit={4}（0=未传）；texture_size={5}{6}".format(
            src, cid, fmt, quad, fl, ts, note
        )
        return (cid, info)


NODE_CLASS_MAPPINGS = {
    "TTTripoSubmit": TTTripoSubmit,
    "TTTripoImageTo3D": TTTripoImageTo3D,
    "TTTripoMultiviewTo3D": TTTripoMultiviewTo3D,
    "TTTripoConvert": TTTripoConvert,
    "TTTripoFetch": TTTripoFetch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TTTripoSubmit": "TT-Tripo 提交（文生3D）",
    "TTTripoImageTo3D": "TT-Tripo 提交（图生3D）",
    "TTTripoMultiviewTo3D": "TT-Tripo 提交（多视图生3D）",
    "TTTripoConvert": "TT-Tripo 格式转换",
    "TTTripoFetch": "TT-Tripo 任务取回",
}
