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
import re
import struct
import tempfile
import time
import zipfile

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


def _source(value):
    """输入源三选一校验：生成任务 UUID / file_* token / http(s):// URL。
    返回 (normalized, kind)；不合法或为空返回 (None, None)。kind ∈ task_id|file_token|url。"""
    s = (value or "").strip()
    if not s:
        return None, None
    if re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", s):
        return s, "task_id"
    if re.match(r"^file_[A-Za-z0-9_-]+$", s):
        return s, "file_token"
    if re.match(r"^https?://\S+$", s):
        return s, "url"
    return None, None


def _glb_part_names(path):
    """GLB 最小解析：读取 JSON chunk，收集 tripo_part_* 节点名（meshes/nodes）。失败或不存在返回 []。"""
    try:
        with open(path, "rb") as f:
            magic, _, _ = struct.unpack("<4sII", f.read(12))
            if magic != b"glTF":
                return []
            while True:
                header = f.read(8)
                if len(header) < 8:
                    break
                clen, ctype = struct.unpack("<II", header)
                if ctype == 0x4E4F534A:  # 'JSON'
                    data = json.loads(f.read(clen).decode("utf-8", "replace"))
                    names = []
                    for m in data.get("meshes", []):
                        n = (m.get("name") or "")
                        if n.startswith("tripo_part_"):
                            names.append(n)
                    if not names:
                        for nd in data.get("nodes", []):
                            n = (nd.get("name") or "")
                            if n.startswith("tripo_part_"):
                                names.append(n)
                    return sorted(set(names))
                f.seek(clen, 1)
    except Exception:
        pass
    return []


def _tripo_outdir():
    out = os.path.join(folder_paths.get_output_directory(), "Tripo")
    os.makedirs(out, exist_ok=True)
    return out


def _now_ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _safe_filename_part(s):
    """清洗文件名字段：替换 Windows 非法字符（含 ASCII 冒号，防 NTFS 备用流/误建文件）。"""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s or "")


def _write_meta(task_id, status, model_path, preview_path, error, ext="", retries=0, recovered=False, extra=None):
    """取证持久化：output/Tripo/<task_id>.meta.json（无任务 ID 时用时间戳文件名）。
    ext=模型文件扩展名（如 .fbx）；retries=实际重试次数；recovered=是否经重试/续传恢复；
    extra=附加字段字典（如 archive/files/unzip_dir/format_override），format_override 优先于 ext 推导。"""
    try:
        name = (_safe_filename_part(task_id) or ("no-task-" + _now_ts().replace(":", "").replace(" ", "-"))) + ".meta.json"
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
        extra = extra or {}
        if ext:
            data["ext"] = ext
            data["format"] = extra.get("format_override") or ext.lstrip(".").upper()
        for k, v in extra.items():
            if k != "format_override":
                data[k] = v
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
    """从 model_url 的 URL 后缀推断扩展名（忽略查询串）；返回 (ext, known)。
    known=False 表示后缀不在已知列表（回退 .glb，下载后需嗅探文件头，可能是 zip）。"""
    path = (url or "").split("?")[0].strip().lower()
    for ext in _MODEL_EXTS:
        if path.endswith(ext):
            return ext, True
    return ".glb", False


def _download_model(cfg, url, task_id):
    ext, _ = _model_ext(url)
    local = os.path.join(_tripo_outdir(), task_id + ext)
    retries, recovered = _download_bytes_resumable(url, local, max(int(cfg.get("request_timeout") or 60), 120))
    return local, ext, retries, recovered


def _upload_image(cfg, tensor):
    """IMAGE tensor → 临时 PNG → multipart POST {base}/files → file_token；上传后清理临时文件。
    兼容 3D (H,W,C) 与 4D (B,H,W,C) 输入（Multiview batch 拆分后的切片为 3D）。"""
    if tensor.ndim == 4:
        tensor = tensor[0]
    arr = (tensor.clamp(0, 1).cpu().numpy() * 255.0 + 0.5).astype(np.uint8)
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
        meta_extra = {}
        try:
            if model_url:
                local_path, ext, dl_retries, dl_recovered = _download_model(cfg, model_url, task_id)
                total_retries += dl_retries
                recovered = recovered or dl_recovered
        except Exception as e:
            status = "模型下载失败（含 {0} 次下载重试）：{1}".format(total_retries, e)
            return finish("", blank, status, status, total_retries, recovered)
        # URL 后缀不在已知列表时嗅探文件头：PK → zip（OBJ 等转换常以 zip 交付 obj+mtl+贴图）
        _, ext_known = _model_ext(model_url)
        fmt_hint = ""
        di = d.get("input")
        if isinstance(di, dict):
            fmt_hint = str(di.get("format") or "").upper()
        if not ext_known and local_path and os.path.isfile(local_path):
            try:
                with open(local_path, "rb") as fh:
                    magic = fh.read(4)
            except OSError:
                magic = b""
            if magic == b"PK\x03\x04":
                zip_path = os.path.join(_tripo_outdir(), task_id + ".zip")
                if os.path.abspath(zip_path) != os.path.abspath(local_path):
                    if os.path.exists(zip_path):
                        os.unlink(zip_path)
                    os.replace(local_path, zip_path)
                local_path = zip_path
                ext = ".zip"
                label = fmt_hint or "ZIP"
                unzip_dir = os.path.join(_tripo_outdir(), _safe_filename_part(task_id) + "_" + label)
                os.makedirs(unzip_dir, exist_ok=True)
                files = []
                try:
                    with zipfile.ZipFile(zip_path) as zf:
                        zf.extractall(unzip_dir)
                        files = sorted(zf.namelist())
                except Exception as e:
                    status = "success（zip 已下载 {0}）；解包失败：{1}".format(local_path, e)
                    _write_meta(task_id, status, local_path, "", "", ext, total_retries, recovered,
                                {"archive": True, "unzip_dir": unzip_dir, "files": files, "format_override": fmt_hint or "ZIP"})
                    return {"ui": {"text": [status]}, "result": (local_path, blank, status)}
                meta_extra = {"archive": True, "unzip_dir": unzip_dir, "files": files, "format_override": fmt_hint or "ZIP"}
        parts_note = ""
        if ext == ".glb" and local_path and os.path.isfile(local_path):
            parts = _glb_part_names(local_path)
            if parts:
                meta_extra["parts"] = parts
                parts_note = "；分件节点 {0} 个（{1}）".format(len(parts), ",".join(parts))
        image = blank
        preview_path = ""
        try:
            if image_url:
                image, preview_path, dl_retries, dl_recovered = _download_image(cfg, image_url, task_id)
                total_retries += dl_retries
                recovered = recovered or dl_recovered
        except Exception as e:
            status = "success（模型已下载{0}）；预览图下载失败：{1}".format(ext, e)
            _write_meta(task_id, status, local_path, "", str(e), ext, total_retries, recovered, meta_extra)
            return {"ui": {"text": [status]}, "result": (local_path, blank, status)}
        unpack_note = ""
        if meta_extra.get("archive"):
            unpack_note = "（解包 {0} 个文件至 {1}）".format(len(meta_extra.get("files") or []), meta_extra.get("unzip_dir"))
        status = "success：模型 {0}{1}；预览图 {2}；credits_consumed={3}{4}".format(
            local_path or model_url, unpack_note, preview_path or ("已下载" if image_url else "未提供"), d.get("credits_consumed"), parts_note
        )
        _write_meta(task_id, status, local_path, preview_path, "", ext, total_retries, recovered, meta_extra)
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
            # 阶段开关语义：false = 本阶段跳过，不联网、原样透传 task_id、不报错
            return (task_id,
                    "已跳过（未启用）转换：task_id 原样透传，未发起任何网络请求。打开 enable_api 后本阶段才提交转换任务（约 5 credits）。")
        src, _kind = _source(task_id)
        if not src:
            err = "输入源无效或为空：支持生成任务 UUID / file_token / http(s) URL 三选一（分件任务 ID 需经 file_token 或 URL 桥接）。"
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
        info = "转换已提交：源任务={0}；convert_task_id={1}；format={2}；quad={3}；face_limit={4}（0=未传）；texture_size={5}{6}；预计约 5 credits".format(
            src, cid, fmt, quad, fl, ts, note
        )
        return (cid, info)


class TTTripoRetopo:
    """重拓扑（可带 UV）：POST /v3/mesh/decimate（异步，返回新 task_id）。
    enable_api=false 时本阶段跳过：不联网、原样透传 task_id、不报错。smart_uv 仅 v3.0 有效。
    成本口径：v3.0 约 35 credits、quad=true 约 40 credits（写进调用信息与模板说明卡）。"""

    CATEGORY = "TT"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("task_id", "调用信息")
    FUNCTION = "run"
    OUTPUT_NODE = False
    RETOPO_MODELS = ["v3.0", "v2.0", "v1.0"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": "", "tooltip": "粘贴已有任务的 ID，或从上一阶段（生成/重拓扑/SmartUV）的 task_id 连线"}),
                "enable_api": ("BOOLEAN", {"default": False}),
                "model": (cls.RETOPO_MODELS, {"default": "v3.0", "tooltip": "重拓扑模型版本；smart_uv 仅 v3.0 有效"}),
                "face_limit": ("INT", {"default": 10000, "min": 0, "max": 10000000, "tooltip": "0=不传（用平台默认）；重拓扑目标面数"}),
                "quad": ("BOOLEAN", {"default": False, "tooltip": "true=四边形重拓扑（约 40 credits，默认三角约 35 credits）"}),
                "smart_uv": ("BOOLEAN", {"default": False, "tooltip": "自动展开 UV（仅 v3.0 有效；v1.0/v2.0 与 true 组合会在客户端拦截）"}),
                "bake": ("BOOLEAN", {"default": True, "tooltip": "烘焙贴图；v1.0 不传此参数"}),
            }
        }

    def run(self, task_id, enable_api, model, face_limit, quad, smart_uv, bake):
        cfg = _load_config()
        src = (task_id or "").strip()
        if not enable_api:
            return (task_id,
                    "已跳过（未启用）重拓扑：task_id 原样透传，未发起任何网络请求。打开 enable_api 后本阶段才提交重拓扑任务（v3.0 约 35 credits，quad=true 约 40 credits）。")
        src, _kind = _source(task_id)
        if not src:
            err = "输入源无效或为空：支持生成任务 UUID / file_token / http(s) URL 三选一（分件任务 ID 需经 file_token 或 URL 桥接）。"
            return ("ERROR:" + err, err)
        if not cfg["api_key"]:
            return ("ERROR:" + _no_key_msg(), _no_key_msg())
        model = str(model or "v3.0")
        if model not in self.RETOPO_MODELS:
            err = "model 值无效：{0}（可选 {1}）。".format(model, "/".join(self.RETOPO_MODELS))
            return ("ERROR:" + err, err)
        quad = bool(quad)
        smart_uv = bool(smart_uv)
        if smart_uv and model in ("v1.0", "v2.0"):
            err = "smart_uv 仅 v3.0 有效：当前 model={0} 与 smart_uv=true 冲突，请改用 v3.0 或关闭 smart_uv（未发起请求）。".format(model)
            return ("ERROR:" + err, err)
        fl = int(face_limit or 0)
        payload = {"input": src, "model": model, "quad": quad}
        if fl > 0:
            payload["face_limit"] = fl
        if smart_uv:
            payload["smart_uv"] = True
        if model != "v1.0":
            payload["bake"] = bool(bake)
        try:
            data = _request_json(cfg, "POST", "/mesh/decimate", payload)
        except Exception as e:
            err = "重拓扑提交失败（网络/配置）：{0}".format(e)
            return ("ERROR:" + err, err)
        if not isinstance(data, dict) or data.get("code") != 0:
            if isinstance(data, dict):
                code = data.get("code")
                msg = data.get("message") or data.get("msg") or ""
            else:
                code, msg = None, ""
            err = "重拓扑提交失败：code={0} msg={1}".format(code, msg)
            return ("ERROR:" + err, err)
        cid = ((data.get("data") or {}).get("task_id") or "").strip()
        if not cid:
            return ("ERROR:重拓扑提交失败：响应缺少 task_id。", "重拓扑提交失败：响应缺少 task_id。")
        cost = "约 40 credits（quad）" if quad else "约 35 credits"
        info = "重拓扑已提交：源任务={0}；retopo_task_id={1}；model={2}；face_limit={3}（0=未传）；quad={4}；smart_uv={5}；bake={6}（v1.0 不传）；预计 {7}".format(
            src, cid, model, fl, quad, smart_uv, bool(bake), cost
        )
        return (cid, info)


class TTTripoSmartUV:
    """SmartUV：POST /v3/mesh/uv（异步，返回新 task_id）。
    enable_api=false 时本阶段跳过：不联网、原样透传 task_id、不报错。约 20 credits。
    平台限制：输入 ≤8 万等效三角面（超出需先重拓扑减面）。"""

    CATEGORY = "TT"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("task_id", "调用信息")
    FUNCTION = "run"
    OUTPUT_NODE = False
    EXPORT_ORIENTATIONS = ["默认(不传)", "+x", "-x", "+y", "-y"]
    COMPRESS_OPTIONS = ["无", "geometry"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": "", "tooltip": "粘贴已有任务的 ID，或从上一阶段节点连线；输入 ≤8 万等效三角面"}),
                "enable_api": ("BOOLEAN", {"default": False}),
                "bake": ("BOOLEAN", {"default": True}),
                "export_orientation": (cls.EXPORT_ORIENTATIONS, {"default": "默认(不传)", "tooltip": "默认不传；可选 +x/-x/+y/-y 导出朝向"}),
                "compress": (cls.COMPRESS_OPTIONS, {"default": "无", "tooltip": "geometry=几何压缩；默认不传"}),
            }
        }

    def run(self, task_id, enable_api, bake, export_orientation, compress):
        cfg = _load_config()
        src = (task_id or "").strip()
        if not enable_api:
            return (task_id,
                    "已跳过（未启用）SmartUV：task_id 原样透传，未发起任何网络请求。打开 enable_api 后本阶段才提交 SmartUV 任务（约 20 credits）。")
        src, _kind = _source(task_id)
        if not src:
            err = "输入源无效或为空：支持生成任务 UUID / file_token / http(s) URL 三选一（分件任务 ID 需经 file_token 或 URL 桥接）。"
            return ("ERROR:" + err, err)
        if not cfg["api_key"]:
            return ("ERROR:" + _no_key_msg(), _no_key_msg())
        exp = str(export_orientation or "")
        comp = str(compress or "")
        payload = {"input": src, "bake": bool(bake)}
        if exp and exp != "默认(不传)":
            payload["export_orientation"] = exp
        if comp == "geometry":
            payload["compress"] = comp
        try:
            data = _request_json(cfg, "POST", "/mesh/uv", payload)
        except Exception as e:
            err = "SmartUV 提交失败（网络/配置）：{0}".format(e)
            return ("ERROR:" + err, err)
        if not isinstance(data, dict) or data.get("code") != 0:
            if isinstance(data, dict):
                code = data.get("code")
                msg = data.get("message") or data.get("msg") or ""
            else:
                code, msg = None, ""
            err = "SmartUV 提交失败：code={0} msg={1}".format(code, msg)
            return ("ERROR:" + err, err)
        cid = ((data.get("data") or {}).get("task_id") or "").strip()
        if not cid:
            return ("ERROR:SmartUV 提交失败：响应缺少 task_id。", "SmartUV 提交失败：响应缺少 task_id。")
        info = "SmartUV 已提交：源任务={0}；smartuv_task_id={1}；bake={2}；export_orientation={3}（默认未传）；compress={4}；预计约 20 credits".format(
            src, cid, bool(bake), exp, comp
        )
        return (cid, info)


class TTTripoSegment:
    """平台分件（方案 A）：POST /v3/mesh/segment（异步，返回新 task_id）。约 40 credits/次。
    输出 GLB 节点名 = tripo_part_0/1/…（Fetch 会解析并写入 meta.parts）。
    enable_api=false 时本阶段跳过：不联网、原样透传 task_id、不报错。
    v2.0 为 Beta（语义分件）：granularity/split_by_connectivity/ref_image 仅 v2 有效，v1 时忽略并提示。"""

    CATEGORY = "TT"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("task_id", "调用信息")
    FUNCTION = "run"
    OUTPUT_NODE = False
    SEGMENT_MODELS = ["v1.0-20250506", "v2.0-20260430"]
    GRANULARITIES = ["balanced", "simple", "detailed"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": "", "tooltip": "输入源三选一：生成任务 UUID / file_token / http(s) URL（分件任务 ID 需经 file_token/URL 桥接才能继续下游优化）"}),
                "enable_api": ("BOOLEAN", {"default": False}),
                "model": (cls.SEGMENT_MODELS, {"default": "v1.0-20250506", "tooltip": "v1.0=几何分件（默认）；v2.0=Beta 语义分件"}),
                "granularity": (cls.GRANULARITIES, {"default": "balanced", "tooltip": "仅 v2.0 有效（simple/balanced/detailed）"}),
                "split_by_connectivity": ("BOOLEAN", {"default": True, "tooltip": "仅 v2.0 有效；按连通性拆分"}),
                "ref_image": ("STRING", {"default": "", "tooltip": "仅 v2.0 有效；file_token 或 URL，提供后忽略 granularity/split_by_connectivity"}),
            }
        }

    def run(self, task_id, enable_api, model, granularity, split_by_connectivity, ref_image):
        cfg = _load_config()
        if not enable_api:
            return (task_id,
                    "已跳过（未启用）分件：task_id 原样透传，未发起任何网络请求。打开 enable_api 后本阶段才提交分件任务（约 40 credits/次）。")
        src, _kind = _source(task_id)
        if not src:
            err = "输入源无效或为空：支持生成任务 UUID / file_token / http(s) URL 三选一。"
            return ("ERROR:" + err, err)
        if not cfg["api_key"]:
            return ("ERROR:" + _no_key_msg(), _no_key_msg())
        model = str(model or "v1.0-20250506")
        if model not in self.SEGMENT_MODELS:
            err = "model 值无效：{0}（可选 {1}）。".format(model, "/".join(self.SEGMENT_MODELS))
            return ("ERROR:" + err, err)
        granularity = str(granularity or "balanced")
        payload = {"input": src, "model": model}
        ignore_note = ""
        if model == "v2.0-20260430":
            ref = (ref_image or "").strip()
            if ref:
                payload["ref_image"] = ref
            else:
                payload["segmentation_granularity"] = granularity
                payload["split_by_connectivity"] = bool(split_by_connectivity)
        else:
            ignored = []
            if granularity != "balanced":
                ignored.append("granularity")
            if not split_by_connectivity:
                ignored.append("split_by_connectivity")
            if (ref_image or "").strip():
                ignored.append("ref_image")
            if ignored:
                ignore_note = "；v1 已忽略 v2 独有参数（{0}）".format(",".join(ignored))
        try:
            data = _request_json(cfg, "POST", "/mesh/segment", payload)
        except Exception as e:
            err = "分件提交失败（网络/配置）：{0}".format(e)
            return ("ERROR:" + err, err)
        if not isinstance(data, dict) or data.get("code") != 0:
            if isinstance(data, dict):
                code = data.get("code")
                msg = data.get("message") or data.get("msg") or ""
            else:
                code, msg = None, ""
            err = "分件提交失败：code={0} msg={1}".format(code, msg)
            return ("ERROR:" + err, err)
        cid = ((data.get("data") or {}).get("task_id") or "").strip()
        if not cid:
            return ("ERROR:分件提交失败：响应缺少 task_id。", "分件提交失败：响应缺少 task_id。")
        info = "分件已提交：源={0}；segment_task_id={1}；model={2}；granularity={3}；split_by_connectivity={4}；ref_image={5}；预计约 40 credits{6}".format(
            src, cid, model, granularity, bool(split_by_connectivity), (ref_image or "").strip() or "未提供", ignore_note
        )
        return (cid, info)


class TTTripoMeshComplete:
    """分件补洞：POST /v3/mesh/complete（异步）。input=分件/mesh 任务 ID（或 file_token/URL）。
    费用文档未标，以平台实际计费为准。enable_api=false 时透传跳过不报错。"""

    CATEGORY = "TT"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("task_id", "调用信息")
    FUNCTION = "run"
    OUTPUT_NODE = False
    COMPLETION_MODES = ["ai_completion", "quick_cap"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": "", "tooltip": "分件/mesh 任务 ID（或 file_token/URL）"}),
                "enable_api": ("BOOLEAN", {"default": False}),
                "part_names": ("STRING", {"default": "", "tooltip": "逗号分隔节点名（如 tripo_part_0,tripo_part_1）；空=全部"}),
                "completion_mode": (cls.COMPLETION_MODES, {"default": "ai_completion", "tooltip": "ai_completion=AI 补全（默认）；quick_cap=快速封盖"}),
            }
        }

    def run(self, task_id, enable_api, part_names, completion_mode):
        cfg = _load_config()
        if not enable_api:
            return (task_id,
                    "已跳过（未启用）补洞：task_id 原样透传，未发起任何网络请求。打开 enable_api 后本阶段才提交补洞任务（费用以平台计费为准）。")
        src, _kind = _source(task_id)
        if not src:
            err = "输入源无效或为空：支持分件任务 UUID / file_token / http(s) URL 三选一。"
            return ("ERROR:" + err, err)
        if not cfg["api_key"]:
            return ("ERROR:" + _no_key_msg(), _no_key_msg())
        mode = str(completion_mode or "ai_completion")
        if mode not in self.COMPLETION_MODES:
            err = "completion_mode 值无效：{0}（可选 {1}）。".format(completion_mode, "/".join(self.COMPLETION_MODES))
            return ("ERROR:" + err, err)
        parts = [p.strip() for p in (part_names or "").split(",") if p.strip()]
        payload = {"input": src, "model": "v1.0", "completion_mode": mode}
        if parts:
            payload["part_names"] = parts
        try:
            data = _request_json(cfg, "POST", "/mesh/complete", payload)
        except Exception as e:
            err = "补洞提交失败（网络/配置）：{0}".format(e)
            return ("ERROR:" + err, err)
        if not isinstance(data, dict) or data.get("code") != 0:
            if isinstance(data, dict):
                code = data.get("code")
                msg = data.get("message") or data.get("msg") or ""
            else:
                code, msg = None, ""
            err = "补洞提交失败：code={0} msg={1}".format(code, msg)
            return ("ERROR:" + err, err)
        cid = ((data.get("data") or {}).get("task_id") or "").strip()
        if not cid:
            return ("ERROR:补洞提交失败：响应缺少 task_id。", "补洞提交失败：响应缺少 task_id。")
        info = "补洞已提交：源={0}；complete_task_id={1}；part_names={2}（空=全部）；completion_mode={3}；费用以平台计费为准".format(
            src, cid, ",".join(parts) if parts else "全部", mode
        )
        return (cid, info)


NODE_CLASS_MAPPINGS = {
    "TTTripoSubmit": TTTripoSubmit,
    "TTTripoImageTo3D": TTTripoImageTo3D,
    "TTTripoMultiviewTo3D": TTTripoMultiviewTo3D,
    "TTTripoRetopo": TTTripoRetopo,
    "TTTripoSmartUV": TTTripoSmartUV,
    "TTTripoSegment": TTTripoSegment,
    "TTTripoMeshComplete": TTTripoMeshComplete,
    "TTTripoConvert": TTTripoConvert,
    "TTTripoFetch": TTTripoFetch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TTTripoSubmit": "TT-Tripo 提交（文生3D）",
    "TTTripoImageTo3D": "TT-Tripo 提交（图生3D）",
    "TTTripoMultiviewTo3D": "TT-Tripo 提交（多视图生3D）",
    "TTTripoRetopo": "TT-Tripo 重拓扑",
    "TTTripoSmartUV": "TT-Tripo SmartUV",
    "TTTripoSegment": "TT-Tripo 分件",
    "TTTripoMeshComplete": "TT-Tripo 分件补洞",
    "TTTripoConvert": "TT-Tripo 格式转换",
    "TTTripoFetch": "TT-Tripo 任务取回",
}
