#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author：samge
# date：2024-08-23 16:46
# describe：

import json
import time
import requests
from difys import configs, difydb
from utils import fileutils, timeutils


error_codes = {
    "no_file_uploaded": {
        "status": 400,
        "message": "Please upload your file."
    },
    "too_many_files": {
        "status": 400,
        "message": "Only one file is allowed."
    },
    "file_too_large": {
        "status": 413,
        "message": "File size exceeded."
    },
    "unsupported_file_type": {
        "status": 415,
        "message": "File type not allowed."
    },
    "high_quality_dataset_only": {
        "status": 400,
        "message": "Current operation only supports 'high-quality' datasets."
    },
    "dataset_not_initialized": {
        "status": 400,
        "message": "The dataset is still being initialized or indexing. Please wait a moment."
    },
    "archived_document_immutable": {
        "status": 403,
        "message": "The archived document is not editable."
    },
    "dataset_name_duplicate": {
        "status": 409,
        "message": "The dataset name already exists. Please modify your dataset name."
    },
    "invalid_action": {
        "status": 400,
        "message": "Invalid action."
    },
    "document_already_finished": {
        "status": 400,
        "message": "The document has been processed. Please refresh the page or go to the document details."
    },
    "document_indexing": {
        "status": 400,
        "message": "The document is being processed and cannot be edited."
    },
    "invalid_metadata": {
        "status": 400,
        "message": "The metadata content is incorrect. Please check and verify."
    },
    "unknown": {
        "status": 500,
        "message": "Internal Server Error."
    }
}


@timeutils.monitor
def upload_file(file_path, kb_id):
    """上传文件到指定知识库

    Args:
        file_path (str): 上传的文件路径
        kb_name (str): 知识库名称

    Returns:
        dict: 上传结果
    """
    url = f"{configs.API_URL}/datasets/{kb_id}/document/create_by_file" 
    files = {'file': open(file_path, 'rb')}
    data = configs.DOC_COMMON_DATA
    try:
        with open(file_path, 'rb') as file:
            files = {
                'file': file,
                'data': (None, json.dumps(data), 'text/plain')
            }
            response = requests.post(url, headers=configs.get_header(), files=files)
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "retcode": response.status_code,
                "retmsg": "Failed to upload file"
            }
    
    except FileNotFoundError:
        return {
            "retcode": 404,
            "retmsg": f"File not found: {file_path}"
        }
    except IOError as e:
        return {
            "retcode": 500,
            "retmsg": f"IOError: {str(e)}"
        }
    except requests.exceptions.RequestException as e:
        return {
            "retcode": 500,
            "retmsg": f"Request failed: {str(e)}"
        }

@timeutils.monitor
def upload_file_with_check(file_path, kb_id):
    # 上传文档+解析文档，并仅当文档解析完毕后才返回
    
    # 上传文档
    r = upload_file(file_path=file_path, kb_id=kb_id)
    
    if not is_succeed(r):
        timeutils.print_log(F'失败 parse_chunks_with_check = {doc_item.get("id")}')
        return False
    
    doc_id = r.get('document').get('id')
    while True:
        doc_item = difydb.get_doc_item(doc_id)
        if not doc_item:
            return False
        
        indexing_status = doc_item.get('indexing_status')
        if indexing_status == "failed":
            msg = f"[{file_path}]解析失败，跳过，indexing_status={indexing_status}"
            timeutils.print_log(msg)
            fileutils.save(f"{fileutils.get_cache_dir()}/dify_fail.txt", f"{timeutils.get_now_str()} {msg}\n")
            return False
        
        timeutils.print_log(f"[{file_path}]解析进度状态为：{indexing_status or '未知'}")
        if is_index_completed(doc_item):
            return True
        time.sleep(1)
    
    
# 是否请求成功
def is_succeed(response):
    retcode = response.get("retcode") or 0
    if retcode > 0:
        if retcode == 200:
            return True
        timeutils.print_log(f"请求错误：{code} {response.get('retmsg')}")
        return False
    
    code = response.get("code")
    is_ok = code not in error_codes.keys()
    if not is_ok:
        timeutils.print_log(f"请求错误：{code} {error_codes.get(code).get('message')}")
    return is_ok
    
    
# 是否构建索引已完成
def is_index_completed(doc_item):
    return doc_item.get('indexing_status') == 'completed'
