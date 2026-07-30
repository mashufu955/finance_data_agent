"""Synchronous PyMySQL database module for CRUD routers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
import pymysql.cursors

from app.config.app_config import app_config

_cfg = app_config.db_dw

DB_CONFIG = dict(
    host=_cfg.host,
    port=_cfg.port,
    user=_cfg.user,
    password=str(_cfg.password),
    database=_cfg.database,
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=True,
)


@contextmanager
def db_cursor() -> Iterator[tuple[pymysql.connections.Connection, pymysql.cursors.DictCursor]]:
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            yield conn, cursor
    finally:
        conn.close()


def fetch_one(sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    with db_cursor() as (_, cursor):
        cursor.execute(sql, params)
        return cursor.fetchone()


def fetch_all(sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    with db_cursor() as (_, cursor):
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def execute(sql: str, params: tuple[Any, ...] | None = None) -> int:
    with db_cursor() as (conn, cursor):
        affected = cursor.execute(sql, params)
        conn.commit()
        return affected


def insert(sql: str, params: tuple[Any, ...] | None = None) -> int:
    with db_cursor() as (conn, cursor):
        cursor.execute(sql, params)
        conn.commit()
        return cursor.lastrowid
