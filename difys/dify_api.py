#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Dify 官方知识库 API 封装
# 接口参考：https://docs.dify.ai/api-reference/知识库
# 仅使用官方 API，不依赖任何数据库直连

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Optional

import requests

from difys import configs
from utils import apilog
from utils import timeutils


# 索引完成的最终状态值（其余如 waiting/parsing/cleaning/splitting/indexing 均视为进行中）
_INDEX_COMPLETED = 'completed'
_INDEX_ERROR = 'error'
_INDEX_PAUSED = 'paused'

# indexing_status 阶段中文映射（Dify 高质量索引是批量提交分段，completed_segments 常从 0 直接跳到 total，
# 故真正的"中间进度"是阶段流转 waiting→parsing→cleaning→splitting→indexing→completed）
_STAGE_LABELS = {
    'waiting': '排队中',
    'parsing': '解析中',
    'cleaning': '清洗中',
    'splitting': '切分中',
    'indexing': '索引中',
    'completed': '已完成',
    'error': '失败',
    'paused': '已暂停',
}


def _stage_label(status: str) -> str:
    return _STAGE_LABELS.get(status or '', status or '未知')


def _max_wait_seconds() -> int:
    """索引等待上限（秒），可由 INDEXING_MAX_WAIT 配置，默认 3600。

    尊重用户配置的任意 ≥1 的值（含用于测试的小值，如 3）；仅在非法或 ≤0 时回退默认。
    """
    try:
        value = int(getattr(configs, 'INDEXING_MAX_WAIT', 3600) or 3600)
    except (ValueError, TypeError):
        return 3600
    return value if value >= 1 else 3600


def _interruptible_sleep(seconds: int, should_stop: Optional[Callable[[], bool]] = None) -> None:
    """分段 sleep，每秒检查一次取消钩子；钩子返回 True 即抛出 KeyboardInterrupt 中断等待。"""
    remaining = max(1, int(seconds))
    for _ in range(remaining):
        if should_stop and should_stop():
            raise KeyboardInterrupt("用户请求停止")
        time.sleep(1)


class DifyAPI:
    """Dify 知识库（Dataset）官方 API 客户端"""

    def __init__(self):
        self.api_url = (configs.API_URL or '').rstrip('/')
        self.headers = configs.get_header()

    # ---------------- 基础请求 ----------------

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """发送 JSON 类型的 HTTP 请求。

        成功返回 Dify 原始 JSON；失败统一返回 {"code": -1, "message": ...}。
        multipart 上传请使用 create_document_by_file。
        """
        url = f"{self.api_url}{endpoint}"
        headers = dict(self.headers)
        headers.update(kwargs.pop('headers', {}) or {})
        # 请求体：优先 JSON body，其次 query 参数（用于日志记录，不参与实际发送）
        body = kwargs.get('json') if 'json' in kwargs else kwargs.get('params')
        start_time = time.time()

        try:
            response = requests.request(method.upper(), url, headers=headers, timeout=60, **kwargs)
        except requests.exceptions.RequestException as e:
            timeutils.print_log(f"请求异常: {method} {endpoint} -> {e}")
            apilog.log_api_request(method, url, headers, body, error=str(e),
                                   elapsed=time.time() - start_time)
            return {"code": -1, "message": f"请求异常: {e}"}

        apilog.log_api_request(method, url, headers, body,
                               status_code=response.status_code,
                               response=response.text, elapsed=time.time() - start_time)

        if response.status_code >= 400:
            return self._build_error(response, endpoint)

        if not response.content:
            # 部分删除接口可能返回空体
            return {"result": "success"}

        try:
            return response.json()
        except ValueError as e:
            timeutils.print_log(f"JSON 解析失败: {method} {endpoint} -> {e}")
            return {"code": -1, "message": f"JSON 解析失败: {response.text[:200]}"}

    @staticmethod
    def _build_error(response: requests.Response, endpoint: str) -> dict:
        """从 Dify 错误响应中提取可读信息"""
        status = response.status_code
        message = f"HTTP {status}"
        try:
            body = response.json()
        except ValueError:
            body = None

        if isinstance(body, dict):
            # Dify 错误体可能是 {"code": "...", "message": "..."} 或 {"error": {...}}
            err = body.get('error') if isinstance(body.get('error'), dict) else body
            code = err.get('code') or body.get('code') or ''
            msg = err.get('message') or body.get('message') or ''
            if code or msg:
                message += f" [{code}] {msg}"
        elif response.text:
            message += f" {response.text[:200]}"

        timeutils.print_log(f"请求失败: {endpoint} -> {message}")
        return {"code": -1, "message": message, "status": status}

    # ---------------- 连通性 ----------------

    def check_api_url(self) -> tuple[bool, str]:
        """检测配置的 API 地址与 API Key 是否可用"""
        url = f"{self.api_url}/datasets"
        params = {'page': 1, 'limit': 1}
        start_time = time.time()
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            apilog.log_api_request('GET', url, self.headers, params, error=str(e),
                                   elapsed=time.time() - start_time)
            return False, f"请求失败，请检查 API_URL 配置，请求异常：{e}"

        apilog.log_api_request('GET', url, self.headers, params,
                               status_code=response.status_code, response=response.text,
                               elapsed=time.time() - start_time)

        if response.status_code == 401 or response.status_code == 403:
            return False, f"鉴权失败（{response.status_code}），请检查 API_KEY 是否正确"
        if response.status_code >= 400:
            return False, f"请求失败，HTTP 状态码：{response.status_code}"
        return True, "API 地址与 API Key 配置正确"

    # ---------------- 知识库 ----------------

    def list_datasets(self, name: Optional[str] = None, page: int = 1, limit: int = 100) -> list:
        """获取知识库列表（Dify list 不支持按 name 过滤，需在结果中匹配）"""
        params: dict = {'page': page, 'limit': limit}
        response = self._request('GET', '/datasets', params=params)
        if response.get('code') == -1:
            return []
        data = response.get('data', [])
        if name:
            data = [d for d in data if d.get('name') == name]
        return data

    def get_dataset_by_name(self, name: str) -> Optional[dict]:
        """根据名称查找知识库（Dify list 不支持 name 过滤，需翻页匹配）"""
        if not name:
            return None
        page = 1
        while True:
            response = self._request('GET', '/datasets', params={'page': page, 'limit': 100})
            if response.get('code') == -1:
                return None
            data = response.get('data', [])
            if not data:
                return None
            for d in data:
                if d.get('name') == name:
                    return d
            if not response.get('has_more'):
                return None
            page += 1

    def get_dataset(self, dataset_id: str) -> Optional[dict]:
        """获取知识库详情"""
        response = self._request('GET', f'/datasets/{dataset_id}')
        if response.get('code') == -1:
            return None
        return response

    def create_dataset(self, name: str, indexing_technique: Optional[str] = None) -> Optional[dict]:
        """创建空知识库"""
        payload: dict = {'name': name}
        if indexing_technique:
            payload['indexing_technique'] = indexing_technique
        response = self._request('POST', '/datasets', json=payload)
        if response.get('code') == -1:
            timeutils.print_log(f"创建知识库失败: {response.get('message')}")
            return None
        timeutils.print_log(f"创建知识库成功: {name} (ID: {response.get('id')})")
        return response

    def get_or_create_dataset(self, dataset_name: str, dataset_id: str) -> Optional[dict]:
        """优先用 ID 取详情；否则按名称查找；AUTO_CREATE_DATASET 开启时按名创建"""
        if dataset_id:
            dataset = self.get_dataset(dataset_id)
            if dataset and dataset.get('id'):
                return dataset
            timeutils.print_log(f"DATASET_ID={dataset_id} 未找到对应知识库，尝试按名称查找")

        if dataset_name:
            dataset = self.get_dataset_by_name(dataset_name)
            if dataset:
                return dataset
            if getattr(configs, 'AUTO_CREATE_DATASET', False):
                return self.create_dataset(dataset_name, getattr(configs, 'INDEXING_TECHNIQUE', None))
            timeutils.print_log(f"知识库 {dataset_name} 不存在（可开启 AUTO_CREATE_DATASET 自动创建）")
        return None

    # ---------------- 文档 ----------------

    def list_documents(self, dataset_id: str, keyword: Optional[str] = None,
                       page: int = 1, limit: int = 100) -> list:
        """获取知识库文档列表"""
        params: dict = {'page': page, 'limit': limit}
        if keyword:
            params['keyword'] = keyword
        response = self._request('GET', f'/datasets/{dataset_id}/documents', params=params)
        if response.get('code') == -1:
            return []
        return response.get('data', [])

    def get_document_by_name(self, dataset_id: str, filename: str) -> Optional[dict]:
        """根据文件名在知识库中查找文档。

        分页遍历所有 keyword 命中结果（模糊查询），避免命中的相关文档数 >100 时漏判导致重复上传。
        """
        page = 1
        limit = 100
        while True:
            documents = self.list_documents(dataset_id, keyword=filename, page=page, limit=limit)
            if not documents:
                return None
            for doc in documents:
                if doc.get('name') == filename:
                    return doc
            if len(documents) < limit:
                return None
            page += 1

    def create_document_by_file(self, dataset_id: str, file_path: str, data: dict) -> dict:
        """通过上传文件创建文档（create-by-file），返回 {document, batch}

        Args:
            dataset_id: 知识库 ID
            file_path: 待上传文件路径
            data: 上传参数（indexing_technique / process_rule 等）
        """
        url = f"{self.api_url}/datasets/{dataset_id}/document/create-by-file"
        if not os.path.exists(file_path):
            return {"code": -1, "message": f"文件不存在: {file_path}"}

        start_time = time.time()
        try:
            with open(file_path, 'rb') as f:
                files = {
                    'file': (os.path.basename(file_path), f),
                    'data': (None, json.dumps(data), 'text/plain'),
                }
                response = requests.post(url, headers=self.headers, files=files, timeout=300)
        except requests.exceptions.RequestException as e:
            timeutils.print_log(f"上传文件异常: {file_path} -> {e}")
            apilog.log_api_request('POST', url, self.headers, data, error=str(e),
                                   elapsed=time.time() - start_time)
            return {"code": -1, "message": f"上传文件异常: {e}"}
        except IOError as e:
            apilog.log_api_request('POST', url, self.headers, data, error=f"读取文件异常: {e}",
                                   elapsed=time.time() - start_time)
            return {"code": -1, "message": f"读取文件异常: {e}"}

        apilog.log_api_request('POST', url, self.headers, data,
                               status_code=response.status_code, response=response.text,
                               elapsed=time.time() - start_time)

        if response.status_code >= 400:
            return self._build_error(response, '/document/create-by-file')
        try:
            return response.json()
        except ValueError as e:
            return {"code": -1, "message": f"上传响应 JSON 解析失败: {e}"}

    # ---------------- 索引状态 ----------------

    def get_indexing_status(self, dataset_id: str, batch: str) -> list:
        """获取某批次文档的索引状态/进度"""
        response = self._request('GET', f'/datasets/{dataset_id}/documents/{batch}/indexing-status')
        if response.get('code') == -1:
            return []
        return response.get('data', [])

    def get_document(self, dataset_id: str, document_id: str) -> Optional[dict]:
        """获取单个文档详情（含 indexing_status）。文档列表/详情响应不含 batch，
        因此恢复「已存在但未完成」的文档时用此接口轮询。"""
        response = self._request('GET', f'/datasets/{dataset_id}/documents/{document_id}')
        if response.get('code') == -1:
            return None
        return response

    def wait_for_indexing_complete(self, dataset_id: str, batch: str,
                                   filename: str, max_wait: Optional[int] = None,
                                   should_stop: Optional[Callable[[], bool]] = None) -> bool:
        """轮询索引状态直到 completed / error / 超时。

        说明：Dify 高质量索引的 completed_segments 是批量回写的，常从 0 直接跳到 total，
        所以"分段百分比"通常只有 0 和 100 两个值——这属于 Dify 的正常行为，并非工具问题。
        真正有意义的中间进度是 indexing_status 的阶段流转。为避免刷屏，仅在阶段或分段数变化时打印。
        """
        interval = max(1, int(getattr(configs, 'PROGRESS_CHECK_INTERVAL', 5) or 5))
        enable_log = bool(getattr(configs, 'ENABLE_PROGRESS_LOG', True))
        max_wait = int(max_wait) if max_wait else _max_wait_seconds()
        start_time = time.time()
        last_key = None  # (indexing_status, completed, total)
        no_status_count = 0  # 连续查不到状态次数，超过上限则判定失败而非空等 max_wait
        no_status_limit = 60

        while time.time() - start_time < max_wait:
            if should_stop and should_stop():
                raise KeyboardInterrupt("用户请求停止")

            status_list = self.get_indexing_status(dataset_id, batch)
            if not status_list:
                no_status_count += 1
                if no_status_count == 1 and last_key != 'no_status':
                    last_key = 'no_status'
                    timeutils.print_log(f"[{filename}] 暂未查询到索引状态，等待重试")
                if no_status_count >= no_status_limit:
                    timeutils.print_log(f"[{filename}] 连续 {no_status_limit} 次未查询到索引状态，停止等待")
                    return False
                _interruptible_sleep(min(interval, max(1, max_wait - int(time.time() - start_time))), should_stop)
                continue
            no_status_count = 0

            doc = status_list[0]
            indexing_status = doc.get('indexing_status') or ''
            completed = doc.get('completed_segments') or 0
            total = doc.get('total_segments') or 0

            # 只在阶段或分段数变化时打印，避免相同状态刷屏
            key = (indexing_status, completed, total)
            if enable_log and key != last_key:
                label = _stage_label(indexing_status)
                if total:
                    percent = round(completed / total * 100, 1)
                    timeutils.print_log(f"[{filename}] {label}（分段 {completed}/{total}，{percent}%）")
                else:
                    timeutils.print_log(f"[{filename}] {label}")
                last_key = key

            if indexing_status == _INDEX_COMPLETED:
                timeutils.print_log(f"[{filename}] 索引完成")
                return True
            if indexing_status == _INDEX_ERROR:
                timeutils.print_log(f"[{filename}] 索引失败：{doc.get('error')}，请手动检查该文件是否符合要求")
                return False
            if indexing_status == _INDEX_PAUSED:
                timeutils.print_log(f"[{filename}] 索引已暂停")
                return False

            _interruptible_sleep(min(interval, max(1, max_wait - int(time.time() - start_time))), should_stop)

        timeutils.print_log(f"[{filename}] 索引超时（{max_wait}s），建议根据实际情况调整【索引等待上限（秒）】")
        return False

    def wait_for_document_complete(self, dataset_id: str, document_id: str,
                                   filename: str, max_wait: Optional[int] = None,
                                   should_stop: Optional[Callable[[], bool]] = None) -> bool:
        """按 document_id 轮询文档详情直至索引完成（用于恢复已存在但未完成的文档）。

        与 wait_for_indexing_complete 的区别：文档详情接口无分段进度（completed_segments），
        仅返回 indexing_status，故此处只打印阶段、不打印百分比。同样仅在阶段变化时打印。
        """
        interval = max(1, int(getattr(configs, 'PROGRESS_CHECK_INTERVAL', 5) or 5))
        enable_log = bool(getattr(configs, 'ENABLE_PROGRESS_LOG', True))
        max_wait = int(max_wait) if max_wait else _max_wait_seconds()
        start_time = time.time()
        last_status = None

        while time.time() - start_time < max_wait:
            if should_stop and should_stop():
                raise KeyboardInterrupt("用户请求停止")

            doc = self.get_document(dataset_id, document_id)
            if not doc:
                _interruptible_sleep(min(interval, max(1, max_wait - int(time.time() - start_time))), should_stop)
                continue

            indexing_status = doc.get('indexing_status') or ''
            if enable_log and indexing_status != last_status:
                timeutils.print_log(f"[{filename}] {_stage_label(indexing_status)}")
                last_status = indexing_status

            if indexing_status == _INDEX_COMPLETED:
                timeutils.print_log(f"[{filename}] 索引完成")
                return True
            if indexing_status == _INDEX_ERROR:
                timeutils.print_log(f"[{filename}] 索引失败：{doc.get('error')}，请手动检查该文件是否符合要求")
                return False
            if indexing_status == _INDEX_PAUSED:
                timeutils.print_log(f"[{filename}] 索引已暂停")
                return False

            _interruptible_sleep(min(interval, max(1, max_wait - int(time.time() - start_time))), should_stop)

        timeutils.print_log(f"[{filename}] 索引超时（{max_wait}s），建议根据实际情况调整【索引等待上限（秒）】")
        return False

    # ---------------- 元数据 ----------------

    def list_metadata(self, dataset_id: str) -> list:
        """获取知识库的元数据字段列表，返回 [{id, name, type, ...}]"""
        response = self._request('GET', f'/datasets/{dataset_id}/metadata')
        if response.get('code') == -1:
            return []
        return response.get('doc_metadata', []) or response.get('data', []) or []

    def create_metadata_field(self, dataset_id: str, name: str, field_type: str = 'string') -> Optional[dict]:
        """创建元数据字段，返回 {id, type, name}"""
        response = self._request('POST', f'/datasets/{dataset_id}/metadata',
                                 json={'type': field_type, 'name': name})
        if response.get('code') == -1:
            timeutils.print_log(f"创建元数据字段失败 [{name}]: {response.get('message')}")
            return None
        return response

    def update_documents_metadata(self, dataset_id: str, document_id: str,
                                  metadata_list: list, partial_update: bool = True) -> bool:
        """为指定文档批量赋值元数据

        Args:
            metadata_list: [{"id": field_id, "name": field_name, "value": ...}, ...]
        """
        payload = {
            'operation_data': [
                {
                    'document_id': document_id,
                    'metadata_list': metadata_list,
                    'partial_update': partial_update,
                }
            ]
        }
        response = self._request('POST', f'/datasets/{dataset_id}/documents/metadata', json=payload)
        if response.get('code') == -1:
            timeutils.print_log(f"设置文档元数据失败: {response.get('message')}")
            return False
        return True


# 全局单例
dify_api = DifyAPI()
