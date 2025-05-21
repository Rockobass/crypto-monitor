# db_manager.py
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
        return None
    except sqlite3.Error as e:
        print(f"数据库操作失败: {query[:100]}... - {e}")
        if "UNIQUE constraint failed" in str(e):
            print("错误：尝试插入重复的唯一键值。")
        return None if "INSERT" in query.upper() and commit else False
    finally:
        conn.close()


def _row_to_model(row: Optional[sqlite3.Row], model_class: Type[ModelType]) -> Optional[ModelType]:
    if not row:
        return None
    data = dict(row)
    if model_class == AlertRule and 'params' in data and isinstance(data['params'], str):
        try:
            data['params'] = json.loads(data['params'])
        except json.JSONDecodeError:
            print(f"警告: 解析AlertRule params失败 (ID: {data.get('id')}): {data['params']}")
            data['params'] = {}

    # 将布尔值正确转换
    # 使用 Pydantic v2 的 model_fields 替代 __fields__
    for key, field_info in model_class.model_fields.items():
        if key in data:
            value = data[key]
            # 检查字段的期望类型是否为 bool
            # Pydantic v2中，类型的比较可能需要更细致，但通常 bool 类型会直接用 bool 表示
            # field_info.annotation 可以获取类型
            if field_info.annotation == bool and isinstance(value, int):
                data[key] = bool(value)

    if model_class == AlertRule and 'cooldown_seconds' not in data and 'cooldown_seconds' in AlertRule.model_fields:
        data['cooldown_seconds'] = AlertRule.model_fields['cooldown_seconds'].default

    try:
        return model_class(**data)
    except Exception as e:  # 更通用的异常捕获，以防模型实例化时出错
        print(f"错误: _row_to_model 实例化 {model_class.__name__} 失败. 数据: {data}. 错误: {e}")
        return None


def initialize_database():
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
        cooldown_seconds INTEGER DEFAULT 60,
        FOREIGN KEY (pair_id) REFERENCES trading_pairs (id) ON DELETE CASCADE
    )
    """)
    print(f"数据库表已在 '{DB_FILE}' 中检查/创建。")
    try:
        _execute_query("SELECT cooldown_seconds FROM alert_rules LIMIT 1", fetch_one=True)
    except sqlite3.OperationalError as e:
        if "no such column: cooldown_seconds" in str(e):
            print("警告：检测到 alert_rules 表缺少 cooldown_seconds 列。正在尝试添加...")
            try:
                _execute_query("ALTER TABLE alert_rules ADD COLUMN cooldown_seconds INTEGER DEFAULT 60", commit=True)
                print("列 cooldown_seconds 已成功添加到 alert_rules 表。")
            except sqlite3.Error as alter_e:
                print(f"添加列 cooldown_seconds 失败: {alter_e}")
                print("请考虑手动更新数据库结构或删除旧的 .db 文件以重新创建。")


# --- TradingPair 操作 ---
def add_trading_pair(pair: TradingPair) -> Optional[int]:
    return _execute_query(
        "INSERT INTO trading_pairs (instId, is_enabled) VALUES (?, ?)",
        (pair.instId, int(pair.is_enabled)),
        commit=True
    )


def get_trading_pair_by_id(pair_id: int) -> Optional[TradingPair]:
    row = _execute_query("SELECT * FROM trading_pairs WHERE id = ?", (pair_id,), fetch_one=True)
    return _row_to_model(row, TradingPair)


def get_all_trading_pairs() -> List[TradingPair]:
    rows = _execute_query("SELECT * FROM trading_pairs", fetch_all=True)
    # 修正列表推导式：直接使用 tp
    return [tp for row in rows if (tp := _row_to_model(row, TradingPair)) is not None]


def update_trading_pair(pair_id: int, updates: Dict[str, Any]) -> bool:
    processed_updates = {
        key: int(value) if isinstance(value, bool) else value
        for key, value in updates.items()
    }
    fields = ", ".join([f"{key} = ?" for key in processed_updates])
    values = list(processed_updates.values()) + [pair_id]
    return _execute_query(f"UPDATE trading_pairs SET {fields} WHERE id = ?", tuple(values), commit=True)


def delete_trading_pair(pair_id: int) -> bool:
    return _execute_query("DELETE FROM trading_pairs WHERE id = ?", (pair_id,), commit=True)


# --- AlertRule 操作 ---
def add_alert_rule(rule: AlertRule) -> Optional[int]:
    return _execute_query(
        "INSERT INTO alert_rules (pair_id, name, rule_type, params, is_enabled, human_readable_condition, cooldown_seconds) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rule.pair_id, rule.name, rule.rule_type, json.dumps(rule.params), int(rule.is_enabled),
         rule.human_readable_condition, rule.cooldown_seconds),
        commit=True
    )


def get_alert_rule_by_id(rule_id: int) -> Optional[AlertRule]:
    row = _execute_query("SELECT * FROM alert_rules WHERE id = ?", (rule_id,), fetch_one=True)
    return _row_to_model(row, AlertRule)


def get_alert_rules_for_pair(pair_id: int) -> List[AlertRule]:
    rows = _execute_query("SELECT * FROM alert_rules WHERE pair_id = ?", (pair_id,), fetch_all=True)
    # 修正列表推导式：直接使用 ar
    return [ar for row in rows if (ar := _row_to_model(row, AlertRule)) is not None]


def get_all_alert_rules() -> List[AlertRule]:
    rows = _execute_query("SELECT * FROM alert_rules", fetch_all=True)
    # 修正列表推导式：直接使用 ar
    return [ar for row in rows if (ar := _row_to_model(row, AlertRule)) is not None]


def update_alert_rule(rule_id: int, updates: Dict[str, Any]) -> bool:
    if 'params' in updates and isinstance(updates['params'], dict):
        updates['params'] = json.dumps(updates['params'])

    processed_updates = {
        key: int(value) if isinstance(value, bool) else value
        for key, value in updates.items()
    }

    fields = ", ".join([f"{key} = ?" for key in processed_updates])
    values = list(processed_updates.values()) + [rule_id]
    return _execute_query(f"UPDATE alert_rules SET {fields} WHERE id = ?", tuple(values), commit=True)


def delete_alert_rule(rule_id: int) -> bool:
    return _execute_query("DELETE FROM alert_rules WHERE id = ?", (rule_id,), commit=True)