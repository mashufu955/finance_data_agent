"""Import seed CSV files into the dw database - v3."""
import csv
import pymysql
from pathlib import Path

DB_CONFIG = dict(
    host="127.0.0.1", port=3306, user="atguigu", password="Atguigu.123",
    database="dw", charset="utf8mb4", autocommit=False,
)

SEEDS_DIR = Path(r"D:\workspace\finance-data-agent\seeds")

COLUMN_DEFAULTS = {
    "province": "unknown",
    "city": "unknown",
    "address": "unknown",
    "service_phone": "000",
    "min_guarantee_ratio": "0.000000",
    "decision_override": "none",
    "permission_codes": '["all"]',
    "mobile": None,
    "email": None,
    "registered_capital_amount": "0.00",
    "business_address": None,
    "company_scale": None,
    "employee_count": "0",
    "annual_revenue_amount": "0.00",
    "taxpayer_type": None,
    "registration_no": None,
    "legal_representative": None,
}


def read_csv(csv_path: Path) -> tuple[list[str], list[dict]]:
    """Read CSV - files are UTF-8 encoded."""
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if rows:
            return list(rows[0].keys()), rows
        return [], []


# Extra columns to add for specific tables (not in CSV but required by DDL)
TABLE_EXTRA_COLUMNS = {
    "dim_employee": {"permission_codes": '["all"]'},
}


def import_csv(csv_path: Path, table: str, conn):
    columns, rows = read_csv(csv_path)
    if not rows:
        print(f"  SKIP {table}: empty")
        return 0

    # Add extra columns needed by the table but not in CSV
    extra = TABLE_EXTRA_COLUMNS.get(table, {})
    for col, default_val in extra.items():
        if col not in columns:
            columns.append(col)
            for row in rows:
                row[col] = default_val

    for row in rows:
        for col in columns:
            if row.get(col, "") == "" or row.get(col) is None:
                default = COLUMN_DEFAULTS.get(col)
                if default is not None:
                    row[col] = default

    col_names = ", ".join(f"`{c}`" for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO `{table}` ({col_names}) VALUES ({placeholders})"

    count = 0
    with conn.cursor() as cursor:
        for row in rows:
            values = []
            for c in columns:
                v = row.get(c, "")
                if v == "":
                    values.append(None)
                else:
                    values.append(v)
            try:
                cursor.execute(sql, values)
                count += 1
            except Exception as e:
                print(f"  ROW ERROR {table}: {e}")
    conn.commit()
    print(f"  OK {table}: {count}/{len(rows)} rows")
    return count


if __name__ == "__main__":
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        conn.commit()

        seed_files = sorted(SEEDS_DIR.rglob("*.csv"))
        for csv_path in seed_files:
            table = csv_path.stem
            print(f"Importing {csv_path.name} -> {table}")
            try:
                import_csv(csv_path, table, conn)
            except Exception as e:
                print(f"  ERROR {table}: {e}")
                conn.rollback()

        with conn.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
    finally:
        conn.close()
