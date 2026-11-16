import base64
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
import folder_paths
import comfy.model_management
from comfy_api.latest import InputImpl
from .core import Client, ArkError, config_fingerprint, image_body, video_body, safe_id


def enabled(value):
    if not value:
        raise ArkError("此示例的API调用尚未启用。请先在本地配置密钥、开通模型，再将 enable_api 打开。调用会使用方舟账户额度。")


def check():
    comfy.model_management.throw_exception_if_processing_interrupted()


def client():
    return Client(state=Path(folder_paths.get_user_directory()) / "ark-media-private")


def references(images, video=False):
    if images is None:
        return []
    if len(images) > 10:
        raise ArkError("参考图片过多，最多10张。")
    result = []
    for tensor in images:
        check()
        h, w = tensor.shape[:2]
        if video and (not 0.4 <= w/h <= 2.5 or not 300 <= min(w,h) or max(w,h) > 6000):
            raise ArkError("视频参考图要求宽高300～6000、宽高比0.4～2.5。请先缩放图片。")
        if not video and (min(w,h) < 15 or w*h > 36000000 or not 1/16 <= w/h <= 16):
            raise ArkError("图片尺寸或比例超出Seedream输入范围。")
        image = Image.fromarray((tensor.detach().cpu().clamp(0, 1).numpy()*255).astype(np.uint8)).convert("RGB")
        buf = io.BytesIO(); image.save(buf, format="PNG")
        raw = buf.getvalue()
        if len(raw) >= 30*1024*1024:
            raise ArkError("单张参考图过大，请缩小到30MB以下。")
        result.append("data:image/png;base64," + base64.b64encode(raw).decode())
    return result


def info(kind, model, **extra):
    return json.dumps({"provider": "Volcengine Ark", "kind": kind, "model": model, **extra}, ensure_ascii=False)


class ArkSeedream:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "enable_api": ("BOOLEAN", {"default": False}),
            "prompt": ("STRING", {"multiline": True, "default": "重新设计这个机器人：保留可爱的大头短身比例，改为钴蓝色装甲、橙色配件和发光眼睛，干净的浅灰背景，完整全身。"}),
            "model": ("STRING", {"default": "", "tooltip": "留空使用ark.local.json的seedream_model，也可填自己的模型ID或Endpoint ID"}),
            "size": ("STRING", {"default": "2K"}),
            "watermark": ("BOOLEAN", {"default": False}),
            "refresh_id": ("INT", {"default": 0, "min": 0, "max": 2147483647, "tooltip": "增大以发起新的付费生成。相同请求默认复用本地记录。"}),
        }, "optional": {"reference_images": ("IMAGE",)}, "hidden": {"unique_id": "UNIQUE_ID"}}
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("图片", "调用信息")
    FUNCTION = "run"
    CATEGORY = "Ark Media / 火山方舟"
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return config_fingerprint()
    def run(self, enable_api, prompt, model, size, watermark, refresh_id, reference_images=None, unique_id="default"):
        enabled(enable_api); c = client(); check()
        model = model.strip() or c.config.get("seedream_model", "")
        body = image_body(model, prompt, size, watermark, references(reference_images))
        result = c.submit_once("image", body, refresh_id, str(unique_id))
        items = result.get("data")
        if not isinstance(items, list) or len(items) != 1 or items[0].get("error"):
            raise ArkError("Seedream没有返回单张有效图片，请检查控制台。此节点使用单图模式。")
        item = items[0]
        cache_id = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
        path = c.state / (cache_id + ".image")
        if not path.exists():
            if item.get("b64_json"):
                try:
                    raw = base64.b64decode(item["b64_json"], validate=True)
                except (ValueError, TypeError):
                    raise ArkError("平台图片数据无效。") from None
                if len(raw) > 64*1024*1024:
                    raise ArkError("图片数据过大。")
                path.write_bytes(raw)
            elif item.get("url"):
                c.download(item["url"], path, 64*1024*1024, check)
            else:
                raise ArkError("平台没有返回图片地址或图片数据。")
        try:
            with Image.open(path) as im:
                if im.width*im.height > 36000000:
                    raise ArkError("返回图像像素过大。")
                tensor = torch.from_numpy(np.asarray(ImageOps.exif_transpose(im).convert("RGB")).copy().astype(np.float32)/255).unsqueeze(0)
        except (OSError, ValueError):
            raise ArkError("下载文件不能解码成图片。") from None
        return tensor, info("seedream", model)


class ArkSeedanceSubmit:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "enable_api": ("BOOLEAN", {"default": False}),
            "prompt": ("STRING", {"multiline": True, "default": "机器人慢慢抬起右手向镜头挥手，眼睛轻轻闪烁，镜头固定，保持造型一致，轻微机械运转音。"}),
            "model": ("STRING", {"default": ""}),
            "mode": (["text", "first_frame", "reference_images"],),
            "resolution": (["720p", "1080p", "480p"],),
            "ratio": (["adaptive", "16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],),
            "duration": ("INT", {"default": 5, "min": 4, "max": 30}),
            "generate_audio": ("BOOLEAN", {"default": True}),
            "watermark": ("BOOLEAN", {"default": False}),
            "refresh_id": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
        }, "optional": {"reference_images": ("IMAGE",), "last_frame": ("IMAGE",)}, "hidden": {"unique_id": "UNIQUE_ID"}}
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("任务ID", "调用信息")
    FUNCTION = "run"
    CATEGORY = "Ark Media / 火山方舟"
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return config_fingerprint()
    def run(self, enable_api, prompt, model, mode, resolution, ratio, duration, generate_audio, watermark, refresh_id, reference_images=None, last_frame=None, unique_id="default"):
        enabled(enable_api); c = client(); check()
        model = model.strip() or c.config.get("seedance_model", "")
        body = video_body(model, prompt, mode, resolution, ratio, duration, generate_audio, watermark, references(reference_images, True), references(last_frame, True))
        result = c.submit_once("video", body, refresh_id, str(unique_id))
        task = safe_id(result.get("id"))
        return task, info("seedance", model, task_id=task, ratio=body["ratio"])


class ArkSeedanceFetch:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "task_id": ("STRING", {"default": "", "tooltip": "连接提交节点，或手工填入已有任务ID；此节点只查询和下载，不创建新任务。"}),
            "wait_seconds": ("INT", {"default": 600, "min": 10, "max": 1800}),
        }}
    RETURN_TYPES = ("VIDEO", "STRING")
    RETURN_NAMES = ("视频", "任务信息")
    FUNCTION = "run"
    CATEGORY = "Ark Media / 火山方舟"
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return config_fingerprint()
    def run(self, task_id, wait_seconds):
        task = safe_id(task_id.strip()); c = client(); check()
        name = hashlib.sha256((c.scope+task).encode()).hexdigest()
        path = c.state / (name + ".mp4")
        if not path.exists():
            result = c.poll(task, wait_seconds, check)
            url = result.get("content", {}).get("video_url")
            if not url:
                raise ArkError("任务成功但未返回视频地址，请检查控制台。")
            c.download(url, path, 1024*1024*1024, check)
        video = InputImpl.VideoFromFile(str(path))
        try:
            video.get_dimensions()
        except Exception:
            path.unlink(missing_ok=True)
            raise ArkError("下载文件不能解码成视频；重试获取节点会重新下载，不会创建任务。") from None
        return video, json.dumps({"task_id": task, "status": "downloaded", "new_generation": False})
