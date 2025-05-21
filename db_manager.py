import sqlite3
import json
from typing import List, Optional, Dict, Any, TypeVar, Type
from app_models import TradingPair, AlertRule
from config import DATABASE_URL

DB_FILE = DATABASE_URL.split("sqlite:///./")[-1]
ModelType = TypeVar('ModelType')


def _get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _execute_query(query: str, params: tuple = (), fetch_one: bool = False, fetch_all: bool = False,
                   commit: bool = False):
    """通用查询执行函数"""
    conn = _get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if commit:
            conn.commit()
            return cursor.lastrowid if "INSERT" in query.upper() else cursor.rowcount > 0
        if fetch_one:
            return cursor.fetchone()
        if fetch_all:
            return cursor.fetchall()
        return None  # 默认或用于非查询语句
    except sqlite3.Error as e:
        print(f"数据库操作失败: {query[:100]}... - {e}")
        if "UNIQUE constraint failed" in str(e):  # 更具体的错误提示
            print("错误：尝试插入重复的唯一键值。")
        return None if "INSERT" in query.upper() and commit else False  # 插入失败返回None，更新/删除失败返回False
    finally:
        conn.close()


def _row_to_model(row: Optional[sqlite3.Row], model_class: Type[ModelType]) -> Optional[ModelType]:
    """将数据库行转换为Pydantic模型实例"""
    if not row:
        return None
    data = dict(row)
    if model_class == AlertRule and 'params' in data and isinstance(data['params'], str):
        data['params'] = json.loads(data['params'])
    # 将布尔值正确转换
    for key, value in data.items():
        if isinstance(value, int) and key in ['is_enabled']:  # 假设is_enabled是主要的布尔字段
            data[key] = bool(value)
    return model_class(**data)


def initialize_database():
    """创建数据库表 (如果尚不存在)"""
    # 表定义中为 human_readable_condition 添加 TEXT 类型，允许 NULL
    _execute_query("""
    CREATE TABLE IF NOT EXISTS trading_pairs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instId TEXT NOT NULL UNIQUE,
        is_enabled BOOLEAN NOT NULL DEFAULT 1
    )
    """)
    _execute_query("""
    CREATE TABLE IF NOT EXISTS alert_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pair_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        rule_type TEXT NOT NULL,
        params TEXT NOT NULL,
        is_enabled BOOLEAN NOT NULL DEFAULT 1,
        human_readable_condition TEXT,
        FOREIGN KEY (pair_id) REFERENCES trading_pairs (id) ON DELETE CASCADE
    )
    """)
    print(f"数据库表已在 '{DB_FILE}' 中检查/创建。")


# --- TradingPair 操作 ---
def add_trading_pair(pair: TradingPair) -> Optional[int]:
    return _execute_query(
        "INSERT INTO trading_pairs (instId, is_enabled) VALUES (?, ?)",
        (pair.instId, pair.is_enabled),
        commit=True
    )


def get_trading_pair_by_id(pair_id: int) -> Optional[TradingPair]:
    row = _execute_query("SELECT * FROM trading_pairs WHERE id = ?", (pair_id,), fetch_one=True)
    return _row_to_model(row, TradingPair)


def get_all_trading_pairs() -> List[TradingPair]:
    rows = _execute_query("SELECT * FROM trading_pairs", fetch_all=True)
    return [_row_to_model(row, TradingPair) for row in rows if row]


def update_trading_pair(pair_id: int, updates: Dict[str, Any]) -> bool:
    fields = ", ".join([f"{key} = ?" for key in updates])
    values = list(updates.values()) + [pair_id]
    return _execute_query(f"UPDATE trading_pairs SET {fields} WHERE id = ?", tuple(values), commit=True)


def delete_trading_pair(pair_id: int) -> bool:
    return _execute_query("DELETE FROM trading_pairs WHERE id = ?", (pair_id,), commit=True)


# --- AlertRule 操作 ---
def add_alert_rule(rule: AlertRule) -> Optional[int]:
    return _execute_query(
        "INSERT INTO alert_rules (pair_id, name, rule_type, params, is_enabled, human_readable_condition) VALUES (?, ?, ?, ?, ?, ?)",
        (rule.pair_id, rule.name, rule.rule_type, json.dumps(rule.params), rule.is_enabled,
         rule.human_readable_condition),
        commit=True
    )


def get_alert_rule_by_id(rule_id: int) -> Optional[AlertRule]:
    row = _execute_query("SELECT * FROM alert_rules WHERE id = ?", (rule_id,), fetch_one=True)
    return _row_to_model(row, AlertRule)


def get_alert_rules_for_pair(pair_id: int) -> List[AlertRule]:
    rows = _execute_query("SELECT * FROM alert_rules WHERE pair_id = ?", (pair_id,), fetch_all=True)
    return [_row_to_model(row, AlertRule) for row in rows if row]


def get_all_alert_rules() -> List[AlertRule]:
    rows = _execute_query("SELECT * FROM alert_rules", fetch_all=True)
    return [_row_to_model(row, AlertRule) for row in rows if row]


def update_alert_rule(rule_id: int, updates: Dict[str, Any]) -> bool:
    if 'params' in updates and isinstance(updates['params'], dict):
        updates['params'] = json.dumps(updates['params'])
    fields = ", ".join([f"{key} = ?" for key in updates])
    values = list(updates.values()) + [rule_id]
    return _execute_query(f"UPDATE alert_rules SET {fields} WHERE id = ?", tuple(values), commit=True)


def delete_alert_rule(rule_id: int) -> bool:
    return _execute_query("DELETE FROM alert_rules WHERE id = ?", (rule_id,), commit=True)

