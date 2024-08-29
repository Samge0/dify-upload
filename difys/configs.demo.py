#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author：samge
# date：2024-08-23 16:49
# describe：

API_URL = 'http://localhost:80/v1'              # dify的api地址，请替换为实际的服务器地址
AUTHORIZATION = 'your authorization'            # dify的api鉴权token
DIFY_DOC_KB_ID = 'your kb_id'                   # dify的知识库id
DOC_COMMON_DATA = {
    # "original_document_id": "",               # 文档id，传值表示更新，不传值表示创建
    "indexing_technique": "high_quality",       # 解析模式： 1. economy = 经济 2. high_quality = 高质量
    "process_rule": {
        "rules": {
            "pre_processing_rules": [
                {"id": "remove_extra_spaces", "enabled": True},
                {"id": "remove_urls_emails", "enabled": False}
            ],
            "segmentation": {
                "separator": "###",
                "max_tokens": 500
            }
        },
        "mode": "automatic" # 1. automatic = 自动 2. manual = 手动
    }
}

DOC_DIR = ''    # 文档目录
DOC_SUFFIX = 'md,txt,pdf,docx'    # 指定文档后缀

PG_HOST = 'localhost'
PG_PORT = 5432
PG_USER = 'postgres'
PG_PASSWORD = 'xxx'
PG_DATABASE = 'dify'

# 文档最少行数，低于该值的文档则被忽略，该参数仅作用于 txt,md,html 后缀文件
DOC_MIN_LINES = 1


def get_header():
    return {'authorization': AUTHORIZATION}