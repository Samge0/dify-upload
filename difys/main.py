#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author：samge
# date：2024-08-23 16:49
# describe：遍历目录，自动上传文档到 Dify 知识库并等待索引完成（纯官方 API，无数据库依赖）

import glob
import os
import time

from difys import api, configs
from utils import timeutils
from utils.statestore import StateStore

# 运行时解析到的知识库ID（供 UI launcher 在运行后读取并回填到配置/界面）
RESOLVED_DATASET_ID = None
# 解析到知识库ID时的回调钩子（UI launcher 注入；源码运行为 None）。一解析到即触发，避免运行中断后丢失
on_dataset_resolved = None


def check_stop() -> bool:
    """协作式取消钩子：UI 运行时由 launcher 注入（返回 True 表示请求停止）；源码运行为空操作。

    main 循环与索引等待会在合适位置调用它，使「停止」按钮能及时响应，而不是依赖异步异常注入。
    """
    return False


def get_docs_files() -> list:
    """获取指定目录及其子目录中的所有文件。

    统一小写比较后缀（Linux 下 glob 大小写敏感，避免漏掉 .PDF 等大写后缀），
    过滤掉目录，结果去重并排序以便日志可复现。
    """
    if not os.path.exists(configs.DOC_DIR):
        raise ValueError(f"文档目录configs.DOC_DIR（{configs.DOC_DIR}）不存在")

    suffixes = {e.strip().lower().lstrip('.') for e in configs.DOC_SUFFIX.split(',') if e.strip()}
    all_files = set()
    for f in glob.glob(f'{configs.DOC_DIR}/**/*', recursive=True):
        if not os.path.isfile(f):
            continue  # 跳过目录
        ext = os.path.splitext(f)[1].lower().lstrip('.')
        if ext in suffixes:
            all_files.add(f)
    return sorted(all_files)


def need_calculate_lines(filepath) -> bool:
    """判断是否需要计算文件行数（仅 txt/md/html）"""
    if not filepath:
        return False
    suffix_lst = "txt,md,html".split(",")
    return filepath.split(".")[-1].lower() in suffix_lst


def get_file_lines(file_path) -> int:
    """获取文件行数。返回 -1 表示无法判定（如非 UTF-8 编码），调用方应跳过行数检查而非跳过文件。"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return len(f.readlines())
    except UnicodeDecodeError:
        # 非 UTF-8（如 GBK）文件：降级用系统默认编码再试一次，仅用于行数判定，不影响上传
        try:
            with open(file_path, 'r') as f:
                return len(f.readlines())
        except Exception as e:
            timeutils.print_log(f"无法解码文件 {file_path} 用于行数统计：{e}")
            return -1
    except Exception as e:
        timeutils.print_log(f"打开文件 {file_path} 时出错，错误信息：{e}")
        return -1


def main():
    """主函数：处理文档上传并等待索引完成"""

    # 运行前测试 API 连接
    status, msg = api.check_api_url()
    if not status:
        raise Exception(msg)

    # 校验处理模式相关配置（仅提示，不中断）
    for warning in api.validate_process_rule_config():
        timeutils.print_log(f"⚠️ {warning}")

    # 解析知识库ID（优先配置 ID，其次按名称查找/创建）
    dataset_id = api.resolve_dataset_id(configs.DATASET_NAME, configs.DATASET_ID)
    if not dataset_id:
        raise ValueError("无法获取知识库ID，请检查 DATASET_ID / DATASET_NAME 配置")

    # 暴露解析结果供 UI 回填；源码模式下回填到 configs.py（UI 模式由 launcher 负责）
    global RESOLVED_DATASET_ID
    RESOLVED_DATASET_ID = dataset_id
    timeutils.print_log(f"已解析知识库ID：{dataset_id}")
    # 一解析到即通知 UI 回显（在文件处理之前触发，运行被中断也不会丢失已解析的ID）
    if callable(on_dataset_resolved):
        on_dataset_resolved(dataset_id)
    if api.persist_dataset_id(dataset_id):
        timeutils.print_log(f"已自动回填知识库ID 到 configs.py：{dataset_id}")

    # 硬性阻断：父子模式需高质量索引；提供了知识库ID时，配置模式需与该库一致（分段/索引模式创建后默认不可修改）
    existing_id = dataset_id if configs.DATASET_ID else None
    block_errors = api.check_mode_compatibility(existing_id)
    if block_errors:
        for err in block_errors:
            timeutils.print_log(f"❌ {err}")
        raise ValueError("处理模式校验未通过，已阻断。请修改当前配置或在 Dify 后台重新创建知识库/修改知识库配置：\n" + "\n".join(block_errors))

    # 获取待处理文件
    doc_files = get_docs_files() or []
    file_total = len(doc_files)
    if file_total == 0:
        raise ValueError(f"在 {configs.DOC_DIR} 目录下没有找到符合要求文档文件")

    # 初始化状态机
    cache_key = dataset_id or configs.DATASET_NAME
    state = StateStore(cache_key)
    is_first_upload = True

    for i in range(file_total):
        # 协作式取消：每个文件处理前检查一次，使「停止」能及时生效
        if check_stop():
            timeutils.print_log("收到停止信号，终止处理")
            break

        file_path = doc_files[i]

        # 跳过元数据文件
        if configs.METADATA_SUFFIX and file_path.endswith(configs.METADATA_SUFFIX):
            continue

        file_path = file_path.replace(os.sep, '/')
        filename = os.path.basename(file_path)

        timeutils.print_log(f"【{i + 1}/{file_total}】[{filename}] 正在处理")

        # 状态机检查：DONE 直接跳过
        if not state.should_process(file_path):
            timeutils.print_log(f"[{filename}] 状态为 {state.get(file_path)}，跳过")
            continue

        # 判断文件行数是否小于目标值
        if need_calculate_lines(file_path):
            lines = get_file_lines(file_path)
            if lines == -1:
                timeutils.print_log(f"[{filename}] 无法以 UTF-8 解码用于行数统计，跳过行数检查直接上传")
            elif lines < configs.DOC_MIN_LINES:
                timeutils.print_log(f"[{filename}] 行数低于{configs.DOC_MIN_LINES}，跳过")
                continue

        # 判断文件大小是否超过上限（Dify 默认单文件上限 15MB）
        max_size_mb = getattr(configs, 'DOC_MAX_SIZE_MB', 0) or 0
        if max_size_mb > 0:
            try:
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            except OSError as e:
                timeutils.print_log(f"[{filename}] 获取文件大小失败：{e}，跳过")
                continue
            if file_size_mb > max_size_mb:
                timeutils.print_log(f"[{filename}] 文件大小 {file_size_mb:.2f}MB 超过上限 {max_size_mb}MB，跳过")
                continue

        # 去重兜底：通过 API 查询文档是否已存在（state.json 丢失时生效）
        existing_doc = api.get_document_from_api(filename, dataset_id=dataset_id)
        if existing_doc:
            doc_id = existing_doc.get('id')
            indexing_status = existing_doc.get('indexing_status')

            # 设置元数据（如有同名 .meta.json）
            api.set_document_metadata(doc_id, file_path, dataset_id=dataset_id)

            if configs.ONLY_UPLOAD:
                timeutils.print_log(f"[{filename}] 已存在，仅上传模式，跳过")
                state.set(file_path, StateStore.UPLOADED)
            elif indexing_status == 'completed':
                timeutils.print_log(f"[{filename}] 已存在且索引完成，跳过")
                state.set(file_path, StateStore.DONE)
            elif indexing_status == 'error':
                timeutils.print_log(f"[{filename}] 已存在但索引失败：{existing_doc.get('error')}，请手动检查该文件是否符合要求")
                state.set(file_path, StateStore.FAILED)
            else:
                timeutils.print_log(f"[{filename}] 已存在但未完成索引（{indexing_status}），等待索引完成")
                state.set(file_path, StateStore.PARSING)
                ok = api.wait_indexing_complete_by_doc(filename, doc_id, dataset_id=dataset_id, should_stop=check_stop)
                timeutils.print_log(f"[{filename}] 索引状态：{ok}")
                state.set(file_path, StateStore.DONE if ok else StateStore.FAILED)
            continue

        # 文档不存在，上传文件创建文档（create-by-file 会自动开始索引）
        response = api.upload_file_to_dataset(file_path, configs.DATASET_NAME, configs.DATASET_ID)
        timeutils.print_log(f"[{filename}] upload_file_to_dataset response: {response}")

        if not api.is_succeed(response):
            timeutils.print_log(f"[{filename}] 上传失败：{response.get('message')}")
            state.set(file_path, StateStore.FAILED)
            continue

        # 解析返回的 document.id 与 batch
        document = response.get('document') or {}
        doc_id = document.get('id')
        batch = response.get('batch')

        # 设置元数据（如有同名 .meta.json）
        api.set_document_metadata(doc_id, file_path, dataset_id=dataset_id)

        # 仅上传模式：不等待索引完成
        if configs.ONLY_UPLOAD:
            timeutils.print_log(f"[{filename}] 仅上传模式，已创建文档")
            state.set(file_path, StateStore.UPLOADED)
            continue

        if not batch:
            timeutils.print_log(f"[{filename}] 上传响应未包含 batch，无法跟踪索引进度")
            state.set(file_path, StateStore.FAILED)
            continue

        # 首次上传且配置了首次等待时间
        if is_first_upload and configs.FIRST_INDEX_WAIT_TIME > 0:
            timeutils.print_log(f"[{filename}] 首次上传成功，等待 {configs.FIRST_INDEX_WAIT_TIME} 秒后再查询索引进度...")
            time.sleep(configs.FIRST_INDEX_WAIT_TIME)
        is_first_upload = False

        # 等待索引完成
        timeutils.print_log(f"[{filename}] 等待索引完成")
        state.set(file_path, StateStore.PARSING)
        ok = api.wait_indexing_complete(filename, batch, dataset_id=dataset_id, should_stop=check_stop)
        timeutils.print_log(f"[{filename}] 索引状态：{ok}")
        state.set(file_path, StateStore.DONE if ok else StateStore.FAILED)

    timeutils.print_log('all done')


if __name__ == '__main__':
    main()
