#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author：samge
# date：2024-08-26 10:11
# describe：

from difys import configs
from utils.pgutils import BasePg
from utils import timeutils
from psycopg2 import sql


def get_db():
    return BasePg(
        host=configs.PG_HOST,
        user=configs.PG_USER,
        password=configs.PG_PASSWORD,
        database=configs.PG_DATABASE,
        port=configs.PG_PORT
    )

def query_list(where_key, where_value, field="id,name,indexing_status"):
    db = get_db()
    query_str = sql.SQL("SELECT {field} FROM documents WHERE {where_key} = {where_value}").format(
        field=sql.SQL(',').join(map(sql.Identifier, field.split(','))),  # 将 field 转换为多个 Identifier
        where_key=sql.Identifier(where_key),  # 将 where_key 转换为 Identifier
        where_value=sql.Literal(where_value)  # 将 where_value 转换为 Literal
    )
    lst = db.query_list(query_str)
    db.close_connect()
    return lst


@timeutils.monitor
def get_doc_list(dataset_id):
    doc_ids = query_list("dataset_id", dataset_id)
    return doc_ids

@timeutils.monitor
def get_doc_item(doc_id):
    results = query_list("id", doc_id)
    return results[0] if results else None

@timeutils.monitor
def get_doc_item_by_name(name):
    results = query_list("name", name)
    return results[0] if results else None

def exist(doc_id):
    return get_doc_item(doc_id) is not None

def exist_name(name):
    return get_doc_item_by_name(name) is not None


if __name__ == '__main__':
    doc_list = get_doc_list(configs.DIFY_DOC_KB_ID) or []
    for item in doc_list:
        timeutils.print_log(item.get('id'), item.get('name'), item.get('indexing_status'))
        
    doc_id = 'README.md'
    timeutils.print_log('是否存在：', exist_name(doc_id))
        