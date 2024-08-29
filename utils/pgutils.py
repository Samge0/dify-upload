#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2022/6/4 下午6:28
# @Author  : Samge
from abc import abstractmethod
import psycopg2
import logging

class BasePg(object):

    def __init__(self, host=None, user=None, password=None, database=None, port=None):
        self.logger = logging.getLogger(__name__)
        host = host or self.get_default_host()
        user = user or self.get_default_user()
        password = password or self.get_default_password()
        database = database or self.get_default_database()
        port = int(port or self.get_default_port() or 0)
        self.i('{} {} {} {}'.format(host, user, database, port))
        try:
            self.conn = psycopg2.connect(
                host=host,
                user=user,
                password=password,
                database=database,
                port=port
            )
            self.cursor = self.conn.cursor()

            self.cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
            
        except Exception as e:
            self.e(f"Failed to connect: {e}")
            self.conn = None
            self.cursor = None

    def reconnect(self):
        """重新连接数据库"""
        try:
            if self.conn:
                self.conn.close()
            self.conn = psycopg2.connect(
                host=self.conn.get_dsn_parameters()['host'],
                user=self.conn.get_dsn_parameters()['user'],
                password=self.conn.get_dsn_parameters()['password'],
                database=self.conn.get_dsn_parameters()['dbname'],
                port=self.conn.get_dsn_parameters()['port']
            )
            self.cursor = self.conn.cursor()
            self.i('Reconnected to the database')
        except Exception as e:
            self.e(f"Reconnect failed: {e}")
            self.conn = None
            self.cursor = None

    def query_list(self, sql: str) -> list:
        """
        有返回值的sql执行
        :param sql:
        :return: 字典列表
        """
        try:
            if self.conn.closed:
                self.reconnect()
            cur = self.cursor
            cur.execute(sql)
            columns = [col[0] for col in cur.description]
            return [dict(zip(columns, self.parse_encoding(row))) for row in cur.fetchall()]
        except Exception as e:
            self.e(f"Query failed: {e}")
            return []

    def execute(self, sql: str) -> bool:
        """
        无返回的sql执行
        :param sql:
        :return: True=执行成功, False=执行失败
        """
        try:
            if self.conn.closed:
                self.reconnect()
            cur = self.cursor
            cur.execute(sql)
            self.conn.commit()
            return True
        except Exception as e:
            self.e(f"Execution failed: {e}")
            return False

    def parse_encoding(self, row) -> list:
        """处理Windows中查询出来的中文乱码问题"""
        row = list(row)
        try:
            for i in range(len(row)):
                item = row[i]
                if isinstance(item, str):
                    try:
                        row[i] = item.encode('latin1').decode('gbk')  # 尝试 gbk 解码
                    except UnicodeEncodeError:
                        row[i] = item.encode('utf-8').decode('utf-8')  # 备用 utf-8 解码
        except Exception as e:
            self.e(f"Encoding parse failed: {e}")
        return row


    def close_connect(self) -> None:
        """关闭游标和连接"""
        try:
            if self.cursor:
                self.cursor.close()
            if self.conn:
                self.conn.close()
            self.child_close()
            self.i('释放数据库连接')
        except Exception as e:
            self.e(f"Closing connection failed: {e}")

    @abstractmethod
    def child_close(self) -> None:
        """提供给子类处理的关闭操作"""
        pass

    def i(self, msg):
        self.logger.info(msg)

    def e(self, msg):
        self.logger.error(msg)

    @abstractmethod
    def get_default_host(self):
        """
        获取实际的 默认数据库连接地址

        （子类必须实现该方法）
        """
        raise self.get_error_tip()

    @abstractmethod
    def get_default_user(self):
        """
        获取实际的 默认数据库连接用户名

        （子类必须实现该方法）
        """
        raise self.get_error_tip()

    @abstractmethod
    def get_default_password(self):
        """
        获取实际的 默认数据库连接用户密码

        （子类必须实现该方法）
        """
        raise self.get_error_tip()

    @abstractmethod
    def get_default_database(self):
        """
        获取实际的 默认数据库连接操作的数据库

        （子类必须实现该方法）
        """
        raise self.get_error_tip()

    @abstractmethod
    def get_default_port(self):
        """
        获取实际的 默认数据库连接端口

        （子类必须实现该方法）
        """
        raise self.get_error_tip()
