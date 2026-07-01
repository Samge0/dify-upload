#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author：samge
# date：2024-08-23 16:46
# describe：Dify 知识库 API 薄封装，供 main.py 调用

from __future__ import annotations

import json
import os

from difys import configs
from difys.dify_api import dify_api as dify_client
from utils import timeutils


# ---------------- 工具函数 ----------------

def resolve_dataset_id(dataset_name: str = None, dataset_id: str = None) -> str:
    """解析知识库ID：优先入参，其次配置；不存在时按 AUTO_CREATE_DATASET 决定是否创建。

    调用方已传入有效 dataset_id 时直接返回，避免在循环里每个操作都重复发 GET /datasets/{id} 校验
    （main.py 解析一次后会在循环中复用同一个 id）。
    """
    if dataset_id:
        return dataset_id
    if not dataset_id:
        dataset_id = configs.DATASET_ID
    if not dataset_name:
        dataset_name = configs.DATASET_NAME
    dataset = dify_client.get_or_create_dataset(dataset_name, dataset_id)
    return dataset.get('id') if dataset else None


def persist_dataset_id(dataset_id) -> bool:
    """源码运行模式下，把解析到的知识库ID 回填到 configs.py（仅当原 DATASET_ID 为空）。

    UI 模式（launcher）下由界面负责持久化与刷新，此处通过环境变量 DIFY_UPLOAD_UI 跳过。
    """
    if os.environ.get('DIFY_UPLOAD_UI'):
        return False
    if not dataset_id or str(getattr(configs, 'DATASET_ID', '') or '').strip():
        return False
    path = getattr(configs, '__file__', None)
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        target = 'DATASET_ID'
        replaced = False
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(target) and stripped[len(target):len(target) + 1] in (' ', '=', '\t'):
                indent = line[:len(line) - len(stripped)]
                lines[i] = f"{indent}DATASET_ID = {repr(str(dataset_id))}\n"
                replaced = True
                break
        if not replaced:
            return False
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        # 注意：这里不更新运行时 configs.DATASET_ID，保持「首次按名找到 → 当次不比对模式」
        # 与 UI 模式（launcher 跳过回填）行为一致；写入文件供下一次运行加载后比对。
        return True
    except Exception as e:
        timeutils.print_log(f"回填知识库ID到配置失败: {e}")
        return False


def _normalize_separator(value: str) -> str:
    """将分隔符中的转义序列还原为真实字符。

    GUI 单行输入框无法直接输入换行，约定：用字面量 \\n 表示换行、\\t 制表符、\\r 回车。
    - GUI 输入 \\n\\n 或源码写成 '\\n\\n'（字面反斜杠n） -> 还原为真实换行
    - 若 value 已是真实换行（源码里直接写 '\\n\\n' 单反斜杠） -> 无字面 \\n 可替换，原样返回
    """
    if not value:
        return value
    return (value.replace('\\n', '\n')
                 .replace('\\t', '\t')
                 .replace('\\r', '\r'))


def _pre_processing_rules() -> list:
    """根据 3 个 PREPROCESS_* 开关构造 pre_processing_rules"""
    return [
        {'id': 'remove_extra_spaces', 'enabled': bool(getattr(configs, 'PREPROCESS_REMOVE_EXTRA_SPACES', True))},
        {'id': 'remove_urls_emails', 'enabled': bool(getattr(configs, 'PREPROCESS_REMOVE_URLS_EMAILS', False))},
        {'id': 'remove_stopwords', 'enabled': bool(getattr(configs, 'PREPROCESS_REMOVE_STOPWORDS', False))},
    ]


def _build_process_rule() -> dict:
    """根据 PROCESS_RULE_MODE 构造 process_rule。

    - automatic：内置规则，无需 rules
    - custom：自定义分段（segmentation）+ 预处理规则
    - hierarchical：父子分段，需 parent_mode + 父分段(segmentation) + 子分段(subchunk_segmentation) + 预处理规则
    """
    mode = getattr(configs, 'PROCESS_RULE_MODE', 'automatic')
    if mode == 'automatic':
        return {'mode': 'automatic'}

    segmentation = {
        'separator': _normalize_separator(getattr(configs, 'SEGMENT_SEPARATOR', '\n\n')),
        'max_tokens': int(getattr(configs, 'SEGMENT_MAX_TOKENS', 500)),
        'chunk_overlap': int(getattr(configs, 'SEGMENT_CHUNK_OVERLAP', 0)),
    }
    rules = {
        'pre_processing_rules': _pre_processing_rules(),
        'segmentation': segmentation,
    }

    if mode == 'hierarchical':
        rules['parent_mode'] = getattr(configs, 'HIERARCHICAL_PARENT_MODE', 'full-doc')
        rules['subchunk_segmentation'] = {
            'separator': _normalize_separator(getattr(configs, 'HIERARCHICAL_CHILD_SEPARATOR', '\n')),
            'max_tokens': int(getattr(configs, 'HIERARCHICAL_CHILD_MAX_TOKENS', 200)),
        }

    return {'mode': mode, 'rules': rules}


def _build_indexing_data() -> dict:
    """构造 create-by-file 的 data 参数（indexing_technique 首次添加文档必填）"""
    data = {
        'indexing_technique': configs.INDEXING_TECHNIQUE,
        'doc_form': getattr(configs, 'DOC_FORM', 'text_model'),
        'process_rule': _build_process_rule(),
    }
    doc_language = getattr(configs, 'DOC_LANGUAGE', '') or ''
    if doc_language.strip():
        data['doc_language'] = doc_language.strip()
    return data


def validate_process_rule_config() -> list:
    """校验处理模式相关配置，返回警告文案列表（不抛异常，仅提示）"""
    warnings = []
    mode = getattr(configs, 'PROCESS_RULE_MODE', 'automatic')
    doc_form = getattr(configs, 'DOC_FORM', 'text_model')

    # mode ↔ doc_form 匹配关系
    if mode == 'hierarchical' and doc_form != 'hierarchical_model':
        warnings.append(f"hierarchical 模式需要 DOC_FORM=hierarchical_model，当前为 {doc_form}，否则父子分段不会生效")
    if mode != 'hierarchical' and doc_form == 'hierarchical_model':
        warnings.append(f"DOC_FORM=hierarchical_model 需配合 PROCESS_RULE_MODE=hierarchical，当前为 {mode}")

    if mode in ('custom', 'hierarchical'):
        if int(getattr(configs, 'SEGMENT_MAX_TOKENS', 500)) <= 0:
            warnings.append(f"SEGMENT_MAX_TOKENS={getattr(configs, 'SEGMENT_MAX_TOKENS', 500)} 应为正整数")
        if mode == 'hierarchical':
            parent_mode = getattr(configs, 'HIERARCHICAL_PARENT_MODE', 'full-doc')
            if parent_mode not in ('full-doc', 'paragraph'):
                warnings.append(f"HIERARCHICAL_PARENT_MODE={parent_mode} 非法，应为 full-doc 或 paragraph")
            if int(getattr(configs, 'HIERARCHICAL_CHILD_MAX_TOKENS', 200)) <= 0:
                warnings.append(f"HIERARCHICAL_CHILD_MAX_TOKENS={getattr(configs, 'HIERARCHICAL_CHILD_MAX_TOKENS', 200)} 应为正整数")

    if doc_form == 'qa_model':
        warnings.append("DOC_FORM=qa_model 问答对提取需要在 Dify 后台配置问答模型，若Dify中没有配置相关模型，则索引阶段可能会失败")

    return warnings


def check_mode_compatibility(existing_dataset_id: str = None) -> list:
    """硬性阻断检查：返回阻断错误列表（空=通过）。

    - 规则A（始终）：父子模式(hierarchical)仅在高质量(high_quality)索引下可用。
    - 规则B（提供现有知识库ID时）：分段/索引模式在知识库创建后默认不可修改，
      故配置需与该知识库的 indexing_technique / doc_form 一致，否则提前阻断。
    """
    errors = []
    mode = getattr(configs, 'PROCESS_RULE_MODE', 'automatic')
    doc_form = getattr(configs, 'DOC_FORM', 'text_model')
    indexing_technique = getattr(configs, 'INDEXING_TECHNIQUE', None)

    # 规则A：父子模式仅高质量可用
    if mode == 'hierarchical' and indexing_technique != 'high_quality':
        errors.append(f"父子模式(hierarchical)仅在高质量(high_quality)索引下可用，当前 INDEXING_TECHNIQUE={indexing_technique}")

    # 规则B：与现有知识库的模式一致性
    if existing_dataset_id:
        dataset = dify_client.get_dataset(existing_dataset_id)
        if not dataset:
            errors.append(f"无法获取知识库 {existing_dataset_id} 的详情，无法校验模式兼容性")
        else:
            kb_indexing = dataset.get('indexing_technique')
            kb_doc_form = dataset.get('doc_form') or dataset.get('chunk_structure')
            if kb_indexing and indexing_technique and indexing_technique != kb_indexing:
                errors.append(f"索引模式不一致：当前配置={indexing_technique}，目标知识库={kb_indexing}（索引模式创建后默认不可修改）")
            if kb_doc_form and doc_form and doc_form != kb_doc_form:
                errors.append(f"分段模式不一致：当前配置={doc_form}，目标知识库={kb_doc_form}（分段模式创建后默认不可修改）")
            # doc_form ↔ process_rule_mode 交叉一致性（以知识库实际结构为准）
            if kb_doc_form == 'hierarchical_model' and mode != 'hierarchical':
                errors.append(f"知识库为父子分段模式(doc_form={kb_doc_form})，需将 PROCESS_RULE_MODE 设为 hierarchical")
            if kb_doc_form and kb_doc_form != 'hierarchical_model' and mode == 'hierarchical':
                errors.append(f"知识库非父子结构(doc_form={kb_doc_form})，PROCESS_RULE_MODE 不可为 hierarchical")

    return errors


def _infer_metadata_type(value) -> str:
    """根据值推断元数据字段类型：数值 -> number，其它 -> string"""
    if isinstance(value, bool):
        return 'string'
    if isinstance(value, (int, float)):
        return 'number'
    return 'string'


def _coerce_metadata_value(value, field_type: str):
    """按 Dify 字段类型规整元数据值；无法规整时返回 None（调用方据以跳过该字段）。

    避免把 number 字段塞入字符串值（或反之）导致服务端 422。
    """
    if field_type == 'number':
        if isinstance(value, bool):  # bool 不应当作 number
            return None
        if isinstance(value, (int, float)):
            return value
        try:
            num = float(value)
            return int(num) if num.is_integer() else num
        except (ValueError, TypeError):
            return None
    # string / time / 其它统一字符串化；bool 显式转为可读字符串
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


# ---------------- 对外接口 ----------------

def check_api_url() -> tuple:
    """检测API连接

    Returns:
        tuple[bool, str]: (是否可以访问, 提示文本)
    """
    return dify_client.check_api_url()


def get_document_from_api(filename: str, dataset_id: str = None, dataset_name: str = None):
    """从 Dify API 查询文档（state.json 丢失时作为去重兜底）"""
    resolved_id = resolve_dataset_id(dataset_name, dataset_id)
    if not resolved_id:
        return None
    return dify_client.get_document_by_name(resolved_id, filename)


@timeutils.monitor
def upload_file_to_dataset(file_path: str, dataset_name: str = None, dataset_id: str = None) -> dict:
    """上传文件创建文档（create-by-file）

    Returns:
        dict: 成功返回 {document:{id,...}, batch}；失败返回 {"code": -1, "message": ...}
    """
    resolved_id = resolve_dataset_id(dataset_name, dataset_id)
    if not resolved_id:
        return {'code': -1, 'message': '无法获取知识库ID'}
    return dify_client.create_document_by_file(resolved_id, file_path, _build_indexing_data())


def wait_indexing_complete(filename: str, batch: str,
                           dataset_name: str = None, dataset_id: str = None,
                           should_stop=None) -> bool:
    """轮询索引状态直至完成（Dify 中 create-by-file 已自动开索引，无独立 parse 步骤）。

    用于「刚上传」的文档：使用 batch 调用 indexing-status 接口，可获取分段进度百分比。
    should_stop：可选的取消钩子（返回 True 即抛出 KeyboardInterrupt 中断等待）。
    """
    resolved_id = resolve_dataset_id(dataset_name, dataset_id)
    if not resolved_id or not batch:
        timeutils.print_log(f"[{filename}] 无法获取知识库ID或batch，跳过索引等待")
        return False
    return dify_client.wait_for_indexing_complete(resolved_id, batch, filename, should_stop=should_stop)


def wait_indexing_complete_by_doc(filename: str, document_id: str,
                                  dataset_name: str = None, dataset_id: str = None,
                                  should_stop=None) -> bool:
    """按 document_id 轮询文档详情直至完成。用于恢复「已存在但未完成」的文档（无 batch 时）。"""
    resolved_id = resolve_dataset_id(dataset_name, dataset_id)
    if not resolved_id or not document_id:
        timeutils.print_log(f"[{filename}] 无法获取知识库ID或document_id，跳过索引等待")
        return False
    return dify_client.wait_for_document_complete(resolved_id, document_id, filename, should_stop=should_stop)


def is_succeed(response: dict) -> bool:
    """判断请求是否成功：Dify 成功响应无 code 字段，失败统一返回 code=-1"""
    if not isinstance(response, dict):
        return False
    return response.get('code', 0) == 0


@timeutils.monitor
def set_document_metadata(doc_id: str, filepath: str,
                          dataset_id: str = None, dataset_name: str = None) -> bool:
    """读取同名 .meta.json 元数据并为文档赋值（Dify 两步流程：建字段 + 赋值）

    元数据文件命名：与文档同名替换后缀，如 a.md -> a.meta.json
    元数据内容为扁平 JSON，如 {"author": "samge", "version": 1}
    """
    suffix = getattr(configs, 'METADATA_SUFFIX', '')
    if not suffix or not doc_id:
        return False

    metadata_filepath = os.path.splitext(filepath)[0] + suffix
    if not os.path.exists(metadata_filepath):
        return False

    try:
        with open(metadata_filepath, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        if not isinstance(metadata, dict) or not metadata:
            timeutils.print_log(f"元数据内容为空或格式不正确: {metadata_filepath}")
            return False
    except Exception as e:
        timeutils.print_log(f"读取元数据文件失败 {metadata_filepath}: {e}")
        return False

    resolved_id = resolve_dataset_id(dataset_name, dataset_id)
    if not resolved_id:
        return False

    # 确保字段存在，收集 field_id
    existing = {m.get('name'): m for m in dify_client.list_metadata(resolved_id) if m.get('name')}
    metadata_list = []
    for key, value in metadata.items():
        field = existing.get(key)
        if not field:
            field = dify_client.create_metadata_field(resolved_id, key, _infer_metadata_type(value))
            if not field:
                continue
            existing[key] = field
        # 按字段实际类型规整值，避免类型不匹配被服务端拒绝
        field_type = field.get('type') or 'string'
        coerced = _coerce_metadata_value(value, field_type)
        if coerced is None:
            timeutils.print_log(f"元数据字段 [{key}] 的值 {value!r} 无法转为 {field_type}，跳过")
            continue
        metadata_list.append({'id': field.get('id'), 'name': key, 'value': coerced})

    if not metadata_list:
        return False

    ok = dify_client.update_documents_metadata(resolved_id, doc_id, metadata_list)
    if ok:
        timeutils.print_log(f"设置文档元数据成功: {doc_id}")
    return ok
