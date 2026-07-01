#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dify API 请求日志：独立保存到 ~/.dify_upload/api_logs/api_YYYY-MM-DD.log。

每次请求记录一条结构化文本块：请求时间、方法、URL、请求头（敏感字段脱敏）、
请求体、HTTP 状态码、响应结果（截断）、耗时。

- 通过 `ENABLE_API_LOG`（默认 True）控制开关。
- 敏感字段（auth/token/key/secret/password 等）的值脱敏：保留前 6 + 后 6 字符，中间以 6 个 `*` 拼接；
  值长度 ≤12 时整体替换为 `******`（避免前后拼接反向暴露全部）。
  `Authorization: Bearer xxx` 保留前缀，仅对 token 部分做上述脱敏。
- 仅写入独立文件，不输出到主日志流，避免刷屏。
"""

import json
import logging
import os
import re
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import pytz

_LOGGER_NAME = 'DifyApi'
_TIME_ZONE = os.environ.get('TZ', 'Asia/Shanghai')
# 命中这些子串的「键」视为敏感字段（大小写不敏感）
_SENSITIVE_KEY = re.compile(r'(auth|token|secret|password|passwd|credential)', re.I)
_MAX_TEXT_LEN = 4000  # 请求体 / 响应体单字段最大字符数

_logger = None


def _enabled() -> bool:
    """读取 ENABLE_API_LOG 开关；读取失败时默认开启。延迟 import 避免循环依赖。"""
    try:
        from difys import configs
        return bool(getattr(configs, 'ENABLE_API_LOG', True))
    except Exception:
        return True


def _partial_mask(s: str) -> str:
    """局部脱敏：保留前 3 + 后 3 字符，中间固定 6 个 *；长度 ≤6 时整体掩码。"""
    if len(s) <= 6:
        return '******'
    return f"{s[:3]}******{s[-3:]}"


def _mask_value(value) -> str:
    """脱敏单个值：Bearer 保留前缀（只对 token 局部脱敏），其余整体局部脱敏。"""
    s = str(value)
    if s.lower().startswith('bearer '):
        return 'Bearer ' + _partial_mask(s[7:])
    return _partial_mask(s)


def _mask(obj):
    """递归脱敏 dict/list 中敏感 key 的值。"""
    if isinstance(obj, dict):
        return {k: (_mask_value(v) if _SENSITIVE_KEY.search(str(k)) else _mask(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask(v) for v in obj]
    return obj


def _mask_headers(headers: dict) -> dict:
    masked = {}
    for k, v in (headers or {}).items():
        masked[k] = _mask_value(v) if _SENSITIVE_KEY.search(str(k)) else v
    return masked


def _truncate(text, limit: int = _MAX_TEXT_LEN):
    if text is None:
        return None
    s = text if isinstance(text, str) else str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + f'...(truncated {len(s) - limit} chars)'


def _to_text(obj):
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(obj)


def _pretty_response(text):
    """把响应文本里的 \\uXXXX 转义还原为真实字符（如中文）。

    Dify 的 JSON 响应在传输层常做 ASCII 转义（ensure_ascii=True），导致 response.text
    里出现字面的 \\u9e3f...；通过 JSON 往返（loads + dumps ensure_ascii=False）即可还原。
    仅对以 { 或 [ 开头的 JSON 文本生效；其余（如 HTML 错误页）原样返回。
    """
    if not isinstance(text, str) or not text:
        return text
    s = text.strip()
    if not s or s[0] not in '{[':
        return text
    try:
        return json.dumps(json.loads(s), ensure_ascii=False)
    except (ValueError, TypeError):
        return text


class _TZFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        tz = pytz.timezone(_TIME_ZONE)
        dt = datetime.fromtimestamp(record.created).astimezone(tz)
        return dt.strftime(datefmt or '%Y-%m-%d %H:%M:%S')


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    log_dir = os.path.join(str(Path.home()), '.dify_upload', 'api_logs')
    os.makedirs(log_dir, exist_ok=True)
    tz = pytz.timezone(_TIME_ZONE)
    log_file = os.path.join(log_dir, f"api_{datetime.now(tz).strftime('%Y-%m-%d')}.log")
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 不冒泡到 root，避免重复输出
    if not logger.handlers:
        handler = TimedRotatingFileHandler(log_file, when='midnight', interval=1,
                                           backupCount=30, encoding='utf-8')
        handler.setFormatter(_TZFormatter('%(asctime)s %(message)s'))
        logger.addHandler(handler)
    _logger = logger
    return logger


def log_api_request(method: str, url: str, headers: dict = None, body=None,
                    status_code: int = None, response=None,
                    elapsed: float = None, error: str = None) -> None:
    """记录一次 API 请求。任何字段都可为 None；日志异常不影响主流程。"""
    if not _enabled():
        return
    try:
        logger = _get_logger()
        head = f"[{method.upper()}] {url}"
        if elapsed is not None:
            head += f"  ({elapsed:.3f}s)"
        parts = [head]
        if headers:
            parts.append(f"Headers: {_to_text(_mask_headers(headers))}")
        if body is not None:
            parts.append(f"Body: {_truncate(_to_text(_mask(body)))}")
        if error is not None:
            parts.append(f"Error: {error}")
        else:
            parts.append(f"Status: {status_code}")
            parts.append(f"Response: {_truncate(_pretty_response(response))}")
        logger.info("\n".join(parts) + "\n")
    except Exception:
        # 日志写入失败不应影响业务请求
        pass
