#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Dify 配置示例文件
# 使用方法：复制此文件为 configs.py 并修改相应配置

# Dify API 配置
API_URL = 'http://localhost/v1'        # Dify API 地址（需包含 /v1）
API_KEY = 'dataset-xxxxxx'             # API 密钥，dataset- 开头，在「知识库 - API」页面创建
DATASET_ID = ''                        # 知识库ID（可选，留空则通过名称查找/创建）
DATASET_NAME = 'my_dataset'            # 知识库名称

# 文档处理配置
INDEXING_TECHNIQUE = 'high_quality'    # 索引模式：high_quality = 高质量 | economy = 经济（首次添加文档时必填）
PROCESS_RULE_MODE = 'automatic'        # 分段处理规则：automatic = 自动 | custom = 自定义 | hierarchical = 父子分段
DOC_FORM = 'text_model'                # 分段模式：text_model = 文本 | hierarchical_model = 父子 | qa_model = 问答对
DOC_LANGUAGE = ''                      # 文档语言；留空走 Dify 默认。可选：English / Chinese Simplified /
                                       # Chinese Traditional / Portuguese / Spanish / French / German / Japanese /
                                       # Korean / Russian / Italian / Thai / Ukrainian / Vietnamese / Romanian /
                                       # Polish / Hindi / Türkçe / Farsi / Slovensko / Indonesian / Dutch / Tunisian Arabic
SEGMENT_SEPARATOR = '\\n\\n'           # 分段分隔符（custom/hierarchical 父分段，用 \n 表示换行）
SEGMENT_MAX_TOKENS = 500               # 每段最大 token 数（custom/hierarchical 父分段）
SEGMENT_CHUNK_OVERLAP = 0              # 分段间重叠 token 数（custom/hierarchical 父分段）
PREPROCESS_REMOVE_EXTRA_SPACES = True  # 预处理：去除多余空格
PREPROCESS_REMOVE_URLS_EMAILS = False  # 预处理：去除 URL/邮箱
PREPROCESS_REMOVE_STOPWORDS = False    # 预处理：去除停用词
HIERARCHICAL_PARENT_MODE = 'full-doc'  # 父子模式父分段方式：full-doc = 全文档 | paragraph = 段落
HIERARCHICAL_CHILD_SEPARATOR = '\n'    # 父子模式子分段分隔符（用 \n 表示换行）
HIERARCHICAL_CHILD_MAX_TOKENS = 200    # 父子模式子分段最大 token 数
DOC_DIR = ''                           # 文档目录
DOC_SUFFIX = 'md,txt,pdf,docx'         # 支持的文件后缀
DOC_MIN_LINES = 1                      # 最小文件行数（仅作用于 txt,md,html 后缀）
DOC_MAX_SIZE_MB = 15                   # 单个文件最大尺寸（MB），超过则跳过（Dify 默认上限 15MB）

# 索引配置
ONLY_UPLOAD = False                    # 仅创建文档，不轮询等待索引完成
PROGRESS_CHECK_INTERVAL = 5            # 索引进度检查间隔（秒）
ENABLE_PROGRESS_LOG = True             # 打印索引进度日志
FIRST_INDEX_WAIT_TIME = 0              # 首次上传后索引等待时间（秒）
INDEXING_MAX_WAIT = 3600               # 单个文件索引等待上限（秒）；qa_model/摘要生成较慢时可调大
ENABLE_API_LOG = True                  # 是否记录 Dify API 完整请求日志（~/.dify_upload/api_logs/，敏感字段脱敏）

# 元数据配置
METADATA_SUFFIX = '.meta.json'         # 元数据文件后缀（替换文档后缀，如 a.md -> a.meta.json）

# 知识库配置
AUTO_CREATE_DATASET = False            # 知识库不存在时是否自动创建（按 DATASET_NAME）


def get_header():
    """获取API请求头"""
    return {'Authorization': f'Bearer {API_KEY}'}
