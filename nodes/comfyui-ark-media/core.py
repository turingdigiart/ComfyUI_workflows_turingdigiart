"""Ark HTTP and durable submission receipts. No third-party HTTP dependencies."""
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib import request, parse, error
import uuid

VERSION = "1.0.0"


class ArkError(RuntimeError):
    pass


def load_config():
    path = Path(os.environ.get("COMFY_ARK_CONFIG", Path(__file__).with_name("ark.local.json")))
    if not path.exists():
        path = Path(__file__).with_name("ark.example.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (OSError, ValueError):
        raise ArkError("方舟配置无法读取，请检查 ark.local.json。") from None


def config_fingerprint():
    c = load_config()
    key = os.environ.get(c.get("api_key_env", "ARK_API_KEY"), "") or c.get("api_key", "")
    return hashlib.sha256((json.dumps(c, sort_keys=True) + str(key)).encode()).hexdigest()


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", value):
        raise ArkError("任务编号格式无效。")
    return value


def validate_url(url, test=False, base=False):
    if not isinstance(url, str):
        raise ArkError("接口或媒体网址格式无效。")
    p = parse.urlsplit(url)
    if not p.hostname or p.username or p.password or p.fragment:
        raise ArkError("网址不能包含账户或片段。")
    if p.scheme != "https" and not (test and p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost")):
        raise ArkError("接口及媒体下载必须使用 HTTPS。")
    if base and p.query:
        raise ArkError("接口基址不能包含查询参数。")
    return url.rstrip("/") if base else url


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ArkError("API地址发生重定向，已停止；请填写官方最终地址。")


class MediaRedirect(request.HTTPRedirectHandler):
    def __init__(self, test):
        self.test = test
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, self.test)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def atomic_json(path, data):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


class Client:
    def __init__(self, config=None, state=None):
        self.config = config or load_config()
        c = self.config
        self.test = c.get("allow_local_test", False) is True
        self.base = validate_url(c.get("base_url", ""), self.test, base=True)
        self.key = os.environ.get(c.get("api_key_env", "ARK_API_KEY"), "") or c.get("api_key", "")
        if not self.key:
            raise ArkError("尚未配置方舟API Key。请在部署目录 ark.local.json 的 api_key 中填写，或设置 ARK_API_KEY；不要发到聊天或填进工作流。")
        if not isinstance(self.key, str) or any(ch in self.key for ch in "\r\n"):
            raise ArkError("API Key 格式无效。")
        proxy = c.get("proxy", "system")
        if proxy == "system":
            proxies = request.getproxies()
        elif proxy == "direct":
            proxies = {}
        elif isinstance(proxy, str) and proxy.startswith(("http://", "https://")):
            proxies = {"http": proxy, "https": proxy}
        else:
            raise ArkError("proxy 必须是 system、direct 或 HTTP 代理地址。")
        self.api = request.build_opener(request.ProxyHandler(proxies), NoRedirect())
        # The media opener never receives the API Authorization header.
        self.media = request.build_opener(request.ProxyHandler(proxies), MediaRedirect(self.test))
        self.timeout = max(5, min(int(c.get("request_timeout", 180)), 300))
        self.state = Path(state) if state else Path(__file__).with_name(".state")
        self.state.mkdir(parents=True, exist_ok=True)
        self.scope = hashlib.sha256((self.base + "\0" + self.key).encode()).hexdigest()

    def call(self, route, body=None):
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        if payload and len(payload) > 63 * 1024 * 1024:
            raise ArkError("请求包含的参考图过大，请缩小图片后重试。")
        req = request.Request(self.base + route, data=payload, headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json", "User-Agent": "ComfyUI-Ark-Media/" + VERSION})
        try:
            with self.api.open(req, timeout=self.timeout) as response:
                raw = response.read(90 * 1024 * 1024 + 1)
            if len(raw) > 90 * 1024 * 1024:
                raise ArkError("接口响应过大，已停止。")
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get("error"):
                raise ArkError("平台返回错误；请在方舟控制台检查模型权限、参数和额度。未自动重试。")
            return data
        except error.HTTPError as exc:
            code = exc.code
            exc.close()
            hint = {400: "参数不匹配或输入被平台拒绝", 401: "密钥无效", 403: "模型未开通或账户无权限", 404: "模型、任务或地址不存在", 429: "额度不足或触发限流"}.get(code, "平台请求失败")
            raise ArkError(f"方舟 HTTP {code}：{hint}。未自动重试。") from None
        except (error.URLError, OSError, TimeoutError):
            raise ArkError("方舟连接失败或超时。POST结果可能未知；请先核对控制台任务/账单，勿反复提交。") from None
        except (ValueError, UnicodeError):
            raise ArkError("方舟返回的不是有效JSON。") from None

    def submit_once(self, kind, body, refresh_id, scope):
        """Persist a receipt before POST; never blindly repeat an uncertain paid POST."""
        digest = hashlib.sha256(json.dumps([self.scope, kind, body, refresh_id, scope], sort_keys=True).encode()).hexdigest()
        path = self.state / (digest + ".json")
        try:
            with path.open("x", encoding="utf-8") as f:
                json.dump({"status": "submitting", "kind": kind}, f)
        except FileExistsError:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                raise ArkError("本地提交记录损坏；请先检查方舟控制台，勿直接重复创建任务。") from None
            if record.get("status") == "received":
                return record["result"]
            raise ArkError("此请求上次提交未确认成功，已阻止重复扣费风险。先在方舟控制台核对；视频可用任务ID恢复，确认需重新生成才增加 refresh_id。")
        route = "/images/generations" if kind == "image" else "/contents/generations/tasks"
        result = self.call(route, body)
        if kind == "video":
            result = {"id": safe_id(result.get("id"))}
        # Image response may contain expiring signed URLs. Private state is excluded from releases.
        atomic_json(path, {"status": "received", "kind": kind, "result": result})
        return result

    def download(self, url, target, limit, check=lambda: None):
        validate_url(url, self.test)
        target = Path(target)
        part = target.with_name(target.name + "." + uuid.uuid4().hex + ".part")
        try:
            with self.media.open(request.Request(url, headers={"User-Agent": "ComfyUI-Ark-Media/" + VERSION}), timeout=self.timeout) as r, part.open("wb") as f:
                total = 0
                while True:
                    check()
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise ArkError("媒体超过本地下载上限，已停止。")
                    f.write(chunk)
            if total == 0:
                raise ArkError("媒体下载为空。")
            os.replace(part, target)
        except (error.URLError, OSError, TimeoutError):
            raise ArkError("媒体下载失败。可用原任务编号重试获取，不必重新提交生成。") from None
        finally:
            part.unlink(missing_ok=True)

    def poll(self, task_id, wait_seconds, check=lambda: None):
        task_id = safe_id(task_id)
        deadline = time.monotonic() + wait_seconds
        while True:
            check()
            data = self.call("/contents/generations/tasks/" + task_id)
            status = data.get("status")
            if status == "succeeded":
                return data
            if status in ("failed", "cancelled", "canceled", "expired"):
                raise ArkError(f"视频任务 {task_id} 状态为 {status}；请到方舟控制台查看原因。")
            if status not in ("queued", "running", "processing"):
                raise ArkError("平台返回未知任务状态；未重新提交生成。")
            if time.monotonic() >= deadline:
                raise ArkError(f"本地等待结束，云端任务可能仍在运行。任务ID：{task_id}。再次运行获取节点即可继续查询；不要改变提交节点的 refresh_id。")
            pause = min(max(float(self.config.get("poll_interval", 5)), 1), 30)
            until = min(time.monotonic() + pause, deadline)
            while time.monotonic() < until:
                check()
                time.sleep(min(0.25, max(0, until - time.monotonic())))


def image_body(model, prompt, size, watermark, references):
    if not model.strip() or not prompt.strip():
        raise ArkError("模型和提示词不能为空。")
    if size not in ("1K", "2K", "4K") and not re.fullmatch(r"\d{3,5}x\d{3,5}", size):
        raise ArkError("size 请填 2K、4K 或宽x高，例如 2048x2048；以模型支持范围为准。")
    body = {"model": model, "prompt": prompt, "size": size, "watermark": bool(watermark), "response_format": "url", "stream": False}
    if references:
        if len(references) > 10:
            raise ArkError("此节点最多支持10张参考图片。")
        body["image"] = references[0] if len(references) == 1 else references
    return body


def video_body(model, prompt, mode, resolution, ratio, duration, audio, watermark, refs, last):
    if not model.strip() or not prompt.strip():
        raise ArkError("模型和提示词不能为空。")
    content = [{"type": "text", "text": prompt}]
    if mode == "text":
        if refs or last:
            raise ArkError("text模式不接受参考图，请断开图片或切换模式。")
    elif mode == "first_frame":
        if len(refs) != 1 or len(last) > 1:
            raise ArkError("首帧模式需要恰好一张首帧，尾帧可选一张。")
        ratio = "adaptive"
        content.append({"type": "image_url", "image_url": {"url": refs[0]}, "role": "first_frame"})
        if last:
            content.append({"type": "image_url", "image_url": {"url": last[0]}, "role": "last_frame"})
    elif mode == "reference_images":
        if not refs or len(refs) > 9 or last:
            raise ArkError("参考图模式支持1～9张图片，不使用尾帧接口。")
        content += [{"type": "image_url", "image_url": {"url": ref}, "role": "reference_image"} for ref in refs]
    else:
        raise ArkError("未知视频模式。")
    if not 4 <= duration <= 30 or ("2-0" in model and duration > 15):
        raise ArkError("当前模型/节点不支持该时长；2.0最多15秒，2.5最多30秒。")
    return {"model": model, "content": content, "resolution": resolution, "ratio": ratio, "duration": duration, "generate_audio": bool(audio), "watermark": bool(watermark)}
