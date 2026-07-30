"""
Build meta knowledge base.

Usage:
  Full init (new container):  python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml --init
  Rebuild meta only:          python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml
  Full profile data:          python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml --init --profile full
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Step 0: Load app config
# ---------------------------------------------------------------------------

def load_app_config() -> dict:
    config_path = PROJECT_ROOT / "conf" / "app_config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Step 1: Ensure databases exist
# ---------------------------------------------------------------------------

def ensure_databases(app_config: dict) -> None:
    import pymysql

    cfg = app_config["db_dw"]
    print("[Step 1/4] Ensuring databases exist ...")
    conn = pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "CREATE DATABASE IF NOT EXISTS `dw` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(
                "CREATE DATABASE IF NOT EXISTS `meta` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        print("  -> Databases [dw] and [meta] ready.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Step 2: Import finance.sql DDL into dw
# ---------------------------------------------------------------------------

def import_schema(app_config: dict) -> None:
    import pymysql
    from pymysql.constants import CLIENT

    sql_file = PROJECT_ROOT / "docker_finance" / "sql" / "finance.sql"
    if not sql_file.exists():
        print(f"  !! finance.sql not found: {sql_file}, skipping schema import.")
        return

    cfg = app_config["db_dw"]
    print("[Step 2/4] Importing finance.sql into [dw] ...")
    conn = pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database="dw",
        charset="utf8mb4",
        client_flag=CLIENT.MULTI_STATEMENTS,
    )
    try:
        sql_text = sql_file.read_text(encoding="utf-8")
        with conn.cursor() as cursor:
            cursor.execute(sql_text)
            # Consume all result sets from multi-statement execution
            while cursor.nextset():
                pass
        conn.commit()
        print("  -> Schema imported successfully.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Step 3: Generate test data
# ---------------------------------------------------------------------------

def generate_test_data(app_config: dict, profile: str = "smoke") -> None:
    cfg = app_config["db_dw"]
    print(f"[Step 3/4] Generating test data (profile={profile}) ...")

    # The generate module reads DB config from env vars (via dotenv)
    os.environ.setdefault("DB_HOST", str(cfg["host"]))
    os.environ.setdefault("DB_PORT", str(cfg["port"]))
    os.environ.setdefault("DB_USER", str(cfg["user"]))
    os.environ.setdefault("DB_PASSWORD", str(cfg["password"]))
    os.environ.setdefault("DB_NAME", "dw")

    # Ensure project root is on sys.path so `generate` package is importable
    root_str = str(PROJECT_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from generate.config import GENERATION_DEFAULTS, generation_profile
    from generate.db import close_db, init_db
    from generate.layers.layer1 import Layer1Generator
    from generate.layers.layer2 import Layer2Generator
    from generate.layers.layer3 import Layer3Generator
    from generate.layers.layer4 import Layer4Generator
    from generate.layers.layer5 import Layer5Generator
    from generate.layers.layer6 import Layer6Generator
    from generate.layers.layer7 import Layer7Generator
    from generate.layers.layer8 import Layer8Generator
    from generate.layers.layer9 import Layer9Generator
    from generate.progress import console_print, progress_context

    generators = (
        Layer1Generator, Layer2Generator, Layer3Generator,
        Layer4Generator, Layer5Generator, Layer6Generator,
        Layer7Generator, Layer8Generator, Layer9Generator,
    )

    init_db()
    try:
        with generation_profile(profile):
            with progress_context():
                console_print(f"Generation profile: {profile} -> {GENERATION_DEFAULTS}")
                for gen_cls in generators:
                    gen_cls().run()
    finally:
        close_db()
    print("  -> Test data generated.")


# ---------------------------------------------------------------------------
# Step 4: Build meta knowledge (original logic)
# ---------------------------------------------------------------------------

async def build(meta_config: Path):
    from app.clients.embedding_client import embedding_client_manager
    from app.clients.es_client import es_client_manager
    from app.clients.mysql_client import dw_client_manager, meta_client_manager
    from app.clients.qdrant_client import qdrant_client_manager
    from app.repositories.es.value_es_repository import ValueESRepository
    from app.repositories.mysql.dw_mysql_repository import DWMySQLRepository
    from app.repositories.mysql.meta_mysql_repository import MetaMySQLRepository
    from app.repositories.qdrant.column_repository_qdrant import ColumnQdrantRepository
    from app.repositories.qdrant.metric_repository_qdrant import MetricQdrantRepository
    from app.service.meta_knowledge_service import MetaKnowledgeService

    print("[Step 4/4] Building meta knowledge ...")
    dw_client_manager.init()
    meta_client_manager.init()
    embedding_client_manager.init()
    qdrant_client_manager.init()
    es_client_manager.init()
    async with dw_client_manager.session_factory() as dw_session, meta_client_manager.session_factory() as meta_session:
        dw_mysql_repository = DWMySQLRepository(dw_session)
        meta_mysql_repository = MetaMySQLRepository(meta_session)
        column_qdrant_repository = ColumnQdrantRepository(qdrant_client_manager.client)
        metric_qdrant_repository = MetricQdrantRepository(qdrant_client_manager.client)
        embedding_client = embedding_client_manager.client
        value_es_repository = ValueESRepository(es_client_manager.client)

        meta_knowledge_service = MetaKnowledgeService(
            dw_mysql_repository=dw_mysql_repository,
            meta_mysql_repository=meta_mysql_repository,
            embedding_client=embedding_client,
            column_qdrant_repository=column_qdrant_repository,
            metric_qdrant_repository=metric_qdrant_repository,
            value_es_repository=value_es_repository
        )
        await meta_knowledge_service.build_meta_knowledge(meta_config)

    await dw_client_manager.close()
    await meta_client_manager.close()
    await qdrant_client_manager.close()
    await es_client_manager.close()
    print("  -> Meta knowledge built.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Build meta knowledge base")
    parser.add_argument("-c", "--config", required=True, help="Path to meta_config.yaml")
    parser.add_argument("--init", action="store_true",
                        help="Run full init: create DBs -> import schema -> generate data -> build meta")
    parser.add_argument("--profile", choices=("smoke", "full"), default="smoke",
                        help="Data generation profile (default: smoke)")
    args = parser.parse_args()

    app_config = load_app_config()

    if args.init:
        ensure_databases(app_config)
        import_schema(app_config)
        generate_test_data(app_config, profile=args.profile)

    asyncio.run(build(Path(args.config)))
    print("\nAll done.")
