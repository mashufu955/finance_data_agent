"""Tests for ChatService and MetaKnowledgeService with mocked dependencies."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# ChatService
# ---------------------------------------------------------------------------

class TestChatService:
    @pytest.fixture
    def chat_service(self):
        from app.service.chat_service import ChatService
        graph = MagicMock()
        graph.astream = AsyncMock()
        return ChatService(
            graph=graph,
            embedding_client=AsyncMock(),
            meta_mysql_repository=AsyncMock(),
            dw_mysql_repository=AsyncMock(),
            column_qdrant_repository=AsyncMock(),
            value_es_repository=AsyncMock(),
            metric_qdrant_repository=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_stream_chat_yields_chunks(self, chat_service):
        chunks = [{"stage": "classify"}, {"stage": "generate"}]

        async def mock_astream(**kwargs):
            for c in chunks:
                yield c

        chat_service.graph.astream = mock_astream
        results = []
        async for chunk in chat_service.stream_chat("test query"):
            results.append(chunk)
        assert results == chunks

    @pytest.mark.asyncio
    async def test_stream_chat_empty_stream(self, chat_service):
        async def mock_astream(**kwargs):
            return
            yield  # make it an async generator

        chat_service.graph.astream = mock_astream
        results = []
        async for chunk in chat_service.stream_chat("test"):
            results.append(chunk)
        assert results == []

    def test_chat_service_stores_dependencies(self, chat_service):
        assert chat_service.graph is not None
        assert chat_service.embedding_client is not None
        assert chat_service.meta_mysql_repository is not None
        assert chat_service.dw_mysql_repository is not None
        assert chat_service.column_qdrant_repository is not None
        assert chat_service.value_es_repository is not None
        assert chat_service.metric_qdrant_repository is not None


# ---------------------------------------------------------------------------
# MetaKnowledgeService
# ---------------------------------------------------------------------------

class TestMetaKnowledgeService:
    @pytest.fixture
    def service(self):
        from app.service.meta_knowledge_service import MetaKnowledgeService
        return MetaKnowledgeService(
            dw_mysql_repository=AsyncMock(),
            meta_mysql_repository=AsyncMock(),
            embedding_client=AsyncMock(),
            column_qdrant_repository=AsyncMock(),
            metric_qdrant_repository=AsyncMock(),
            value_es_repository=AsyncMock(),
        )

    def test_convert_column_mysql_to_qdrant(self, service):
        from app.models.mysql.column_info_mysql import ColumnInfoMySQL
        col = ColumnInfoMySQL(
            id="t.c", name="c", type="varchar(32)", role="dimension",
            examples=["a", "b"], description="col desc", alias=["alias1"],
            table_id="t"
        )
        result = service._convert_column_info_from_mysql_to_qdrant(col)
        # Qdrant model may be dataclass or dict-like
        rid = result.id if hasattr(result, "id") else result["id"]
        rname = result.name if hasattr(result, "name") else result["name"]
        assert rid == "t.c"
        assert rname == "c"

    def test_convert_metric_mysql_to_qdrant(self, service):
        from app.models.mysql.metric_info_mysql import MetricInfoMySQL
        metric = MetricInfoMySQL(
            id="m1", name="m1", description="metric desc",
            relevant_columns=["t.c1", "t.c2"], alias=["alias_m"]
        )
        result = service._convert_metric_info_from_mysql_to_qdrant(metric)
        rid = result.id if hasattr(result, "id") else result["id"]
        rname = result.name if hasattr(result, "name") else result["name"]
        assert rid == "m1"
        assert rname == "m1"

    @pytest.mark.asyncio
    async def test_save_tables_to_meta_db(self, service):
        from app.config.meta_config import ColumnConfig, TableConfig
        service.dw_repository.get_column_types = AsyncMock(
            return_value={"col1": "varchar(64)", "col2": "int"}
        )
        service.dw_repository.get_column_values = AsyncMock(return_value=["val1", "val2"])

        mock_session = AsyncMock()
        mock_session.begin = MagicMock()
        mock_session.begin.return_value.__aenter__ = AsyncMock()
        mock_session.begin.return_value.__aexit__ = AsyncMock()
        service.meta_repository.session = mock_session
        service.meta_repository.save_table_infos = AsyncMock()
        service.meta_repository.save_column_infos = AsyncMock()

        tables = [TableConfig(
            name="test_table", role="fact", description="desc",
            columns=[
                ColumnConfig(name="col1", role="dimension", description="c1", alias=[], sync=True),
                ColumnConfig(name="col2", role="measure", description="c2", alias=[], sync=False),
            ]
        )]
        table_infos, column_infos = await service._save_tables_to_meta_db(tables)
        assert len(table_infos) == 1
        assert len(column_infos) == 2
        assert table_infos[0].id == "test_table"
        assert column_infos[0].id == "test_table.col1"

    @pytest.mark.asyncio
    async def test_sync_columns_to_qdrant(self, service):
        from app.models.mysql.column_info_mysql import ColumnInfoMySQL

        # name + description + 2 aliases = 4 records, each needs 1 embedding
        service.embedding_client.aembed_documents = AsyncMock(
            side_effect=lambda texts: [[0.1] * 128] * len(texts)
        )
        service.column_qdrant_repository.ensure_collection = AsyncMock()
        service.column_qdrant_repository.upsert = AsyncMock()

        columns = [ColumnInfoMySQL(
            id="t.c", name="c", type="varchar", role="dimension",
            examples=["a"], description="desc", alias=["a1", "a2"],
            table_id="t"
        )]
        await service._sync_columns_to_qdrant(columns)
        service.column_qdrant_repository.ensure_collection.assert_called_once()
        service.column_qdrant_repository.upsert.assert_called_once()
        args = service.column_qdrant_repository.upsert.call_args[0]
        assert len(args[0]) == 4  # name + desc + 2 aliases = 4 records
        assert len(args[2]) == 4  # 4 payloads

    @pytest.mark.asyncio
    async def test_save_metrics_to_meta_db(self, service):
        from app.config.meta_config import MetricConfig
        mock_session = AsyncMock()
        mock_session.begin = MagicMock()
        mock_session.begin.return_value.__aenter__ = AsyncMock()
        mock_session.begin.return_value.__aexit__ = AsyncMock()
        service.meta_repository.session = mock_session
        service.meta_repository.save_metric_infos = AsyncMock()
        service.meta_repository.save_column_metrics = AsyncMock()

        metrics = [MetricConfig(
            name="m1", description="metric", relevant_columns=["t.c1"], alias=["a1"]
        )]
        result = await service._save_metrics_to_meta_db(metrics)
        assert len(result) == 1
        assert result[0].id == "m1"
        service.meta_repository.save_metric_infos.assert_called_once()
        service.meta_repository.save_column_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_metrics_to_qdrant(self, service):
        from app.models.mysql.metric_info_mysql import MetricInfoMySQL
        service.embedding_client.aembed_documents = AsyncMock(
            return_value=[[0.1] * 128] * 4
        )
        service.metric_qdrant_repository.ensure_collection = AsyncMock()
        service.metric_qdrant_repository.upsert = AsyncMock()

        metrics = [MetricInfoMySQL(
            id="m1", name="m1", description="desc",
            relevant_columns=["t.c1"], alias=["a1"]
        )]
        await service._sync_metrics_to_qdrant(metrics)
        service.metric_qdrant_repository.ensure_collection.assert_called_once()
        service.metric_qdrant_repository.upsert.assert_called_once()
        args = service.metric_qdrant_repository.upsert.call_args[0]
        assert len(args[0]) == 3  # name + desc + 1 alias

    @pytest.mark.asyncio
    async def test_sync_values_to_es(self, service):
        from app.config.meta_config import ColumnConfig, MetaConfig, TableConfig
        from app.models.mysql.column_info_mysql import ColumnInfoMySQL
        from app.models.mysql.table_info_mysql import TableInfoMySQL

        service.full_text_repository.ensure_index = AsyncMock()
        service.full_text_repository.batch_index = AsyncMock()
        service.dw_repository.get_column_values = AsyncMock(
            return_value=["val1", "val2", "val3"]
        )

        table_infos = [TableInfoMySQL(
            id="t1", name="t1", role="fact", description="desc"
        )]
        column_infos = [
            ColumnInfoMySQL(
                id="t1.c1", name="c1", type="varchar", role="dimension",
                examples=[], description="col1", alias=[], table_id="t1",
            ),
            ColumnInfoMySQL(
                id="t1.c2", name="c2", type="int", role="measure",
                examples=[], description="col2", alias=[], table_id="t1",
            ),
        ]
        meta_config = MetaConfig(
            tables=[
                TableConfig(
                    name="t1", role="fact", description="desc",
                    columns=[
                        ColumnConfig(name="c1", role="dimension", description="col1",
                                     alias=[], sync=True),
                        ColumnConfig(name="c2", role="measure", description="col2",
                                     alias=[], sync=False),
                    ],
                ),
            ],
            metrics=[],
        )

        await service._sync_values_to_es(table_infos, column_infos, meta_config)

        service.full_text_repository.ensure_index.assert_called_once()
        service.full_text_repository.batch_index.assert_called_once()
        docs = service.full_text_repository.batch_index.call_args[0][0]
        # Only c1 has sync=True, so 3 values
        assert len(docs) == 3
        assert docs[0]["column_name"] == "c1"
        assert docs[0]["table_name"] == "t1"

    @pytest.mark.asyncio
    async def test_sync_values_to_es_no_sync_columns(self, service):
        from app.config.meta_config import ColumnConfig, MetaConfig, TableConfig
        from app.models.mysql.column_info_mysql import ColumnInfoMySQL
        from app.models.mysql.table_info_mysql import TableInfoMySQL

        service.full_text_repository.ensure_index = AsyncMock()
        service.full_text_repository.batch_index = AsyncMock()

        table_infos = [TableInfoMySQL(id="t1", name="t1", role="fact", description="d")]
        column_infos = [
            ColumnInfoMySQL(
                id="t1.c1", name="c1", type="varchar", role="dimension",
                examples=[], description="col1", alias=[], table_id="t1",
            ),
        ]
        meta_config = MetaConfig(
            tables=[
                TableConfig(
                    name="t1", role="fact", description="d",
                    columns=[
                        ColumnConfig(name="c1", role="dimension", description="col1",
                                     alias=[], sync=False),
                    ],
                ),
            ],
            metrics=[],
        )

        await service._sync_values_to_es(table_infos, column_infos, meta_config)

        service.full_text_repository.batch_index.assert_called_once()
        docs = service.full_text_repository.batch_index.call_args[0][0]
        assert len(docs) == 0

    @pytest.mark.asyncio
    async def test_build_meta_knowledge_full(self, service):
        from app.config.meta_config import ColumnConfig, MetaConfig, MetricConfig, TableConfig
        from app.models.mysql.column_info_mysql import ColumnInfoMySQL
        from app.models.mysql.table_info_mysql import TableInfoMySQL
        from app.models.mysql.metric_info_mysql import MetricInfoMySQL

        # Mock all internal methods
        service._save_tables_to_meta_db = AsyncMock(
            return_value=(
                [TableInfoMySQL(id="t1", name="t1", role="fact", description="d")],
                [ColumnInfoMySQL(
                    id="t1.c1", name="c1", type="varchar", role="dimension",
                    examples=[], description="col1", alias=[], table_id="t1",
                )],
            )
        )
        service._sync_columns_to_qdrant = AsyncMock()
        service._sync_values_to_es = AsyncMock()
        service._save_metrics_to_meta_db = AsyncMock(
            return_value=[MetricInfoMySQL(
                id="m1", name="m1", description="desc",
                relevant_columns=["t1.c1"], alias=[],
            )]
        )
        service._sync_metrics_to_qdrant = AsyncMock()

        meta_config = MetaConfig(
            tables=[
                TableConfig(
                    name="t1", role="fact", description="d",
                    columns=[
                        ColumnConfig(name="c1", role="dimension", description="col1",
                                     alias=[], sync=True),
                    ],
                ),
            ],
            metrics=[
                MetricConfig(name="m1", description="desc",
                             relevant_columns=["t1.c1"], alias=[]),
            ],
        )

        with patch("app.service.meta_knowledge_service.load_config", return_value=meta_config):
            await service.build_meta_knowledge("fake_config.yaml")

        service._save_tables_to_meta_db.assert_called_once()
        service._sync_columns_to_qdrant.assert_called_once()
        service._sync_values_to_es.assert_called_once()
        service._save_metrics_to_meta_db.assert_called_once()
        service._sync_metrics_to_qdrant.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_meta_knowledge_tables_only(self, service):
        from app.config.meta_config import ColumnConfig, MetaConfig, TableConfig

        service._save_tables_to_meta_db = AsyncMock(return_value=([], []))
        service._sync_columns_to_qdrant = AsyncMock()
        service._sync_values_to_es = AsyncMock()
        service._save_metrics_to_meta_db = AsyncMock()
        service._sync_metrics_to_qdrant = AsyncMock()

        meta_config = MetaConfig(
            tables=[
                TableConfig(name="t1", role="fact", description="d",
                            columns=[]),
            ],
            metrics=[],
        )

        with patch("app.service.meta_knowledge_service.load_config", return_value=meta_config):
            await service.build_meta_knowledge("fake_config.yaml")

        service._save_tables_to_meta_db.assert_called_once()
        service._save_metrics_to_meta_db.assert_not_called()
        service._sync_metrics_to_qdrant.assert_not_called()


# ---------------------------------------------------------------------------
# ValueESRepository
# ---------------------------------------------------------------------------

class TestValueESRepository:
    @pytest.fixture
    def es_client(self):
        client = AsyncMock()
        client.indices = AsyncMock()
        client.indices.exists = AsyncMock(return_value=False)
        client.indices.create = AsyncMock()
        client.bulk = AsyncMock()
        client.search = AsyncMock()
        return client

    @pytest.fixture
    def repo(self, es_client):
        from app.repositories.es.value_es_repository import ValueESRepository
        return ValueESRepository(es_client)

    @pytest.mark.asyncio
    async def test_ensure_index_creates_when_missing(self, repo, es_client):
        es_client.indices.exists = AsyncMock(return_value=False)
        await repo.ensure_index()
        es_client.indices.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_index_skips_when_exists(self, repo, es_client):
        es_client.indices.exists = AsyncMock(return_value=True)
        await repo.ensure_index()
        es_client.indices.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_index(self, repo, es_client):
        from app.models.es.value_info_es import ValueInfoES
        docs = [
            ValueInfoES(id="a", value="v1", type="varchar", column_id="t.c",
                        column_name="c", table_id="t", table_name="t"),
            ValueInfoES(id="b", value="v2", type="varchar", column_id="t.c",
                        column_name="c", table_id="t", table_name="t"),
        ]
        await repo.batch_index(docs, batch_size=10)
        es_client.bulk.assert_called_once()
        ops = es_client.bulk.call_args[1]["operations"]
        # 2 docs * 2 operations each (index action + doc)
        assert len(ops) == 4

    @pytest.mark.asyncio
    async def test_batch_index_multiple_batches(self, repo, es_client):
        from app.models.es.value_info_es import ValueInfoES
        docs = [
            ValueInfoES(id=f"d{i}", value=f"v{i}", type="varchar",
                        column_id="t.c", column_name="c",
                        table_id="t", table_name="t")
            for i in range(5)
        ]
        await repo.batch_index(docs, batch_size=2)
        # 5 docs / batch_size 2 = 3 batches
        assert es_client.bulk.call_count == 3

    @pytest.mark.asyncio
    async def test_query_returns_results(self, repo, es_client):
        es_client.search = AsyncMock(return_value={
            "hits": {
                "hits": [
                    {"_source": {"id": "a", "value": "test", "type": "varchar",
                                 "column_id": "t.c", "column_name": "c",
                                 "table_id": "t", "table_name": "t"}},
                ]
            }
        })
        results = await repo.query("test")
        assert len(results) == 1
        assert results[0]["id"] == "a"

    @pytest.mark.asyncio
    async def test_query_empty_results(self, repo, es_client):
        es_client.search = AsyncMock(return_value={"hits": {"hits": []}})
        results = await repo.query("nonexistent")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# build_meta_knowledge CLI script
# ---------------------------------------------------------------------------

class TestBuildMetaKnowledgeScript:
    @pytest.mark.asyncio
    async def test_build_function_wires_dependencies(self):
        from pathlib import Path
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_service = AsyncMock()
        mock_service.build_meta_knowledge = AsyncMock()

        mock_dw = MagicMock()
        mock_dw.init = MagicMock()
        mock_dw.close = AsyncMock()
        mock_dw.session_factory = MagicMock()
        mock_dw.session_factory.return_value.__aenter__ = AsyncMock()
        mock_dw.session_factory.return_value.__aexit__ = AsyncMock()

        mock_meta = MagicMock()
        mock_meta.init = MagicMock()
        mock_meta.close = AsyncMock()
        mock_meta.session_factory = MagicMock()
        mock_meta.session_factory.return_value.__aenter__ = AsyncMock()
        mock_meta.session_factory.return_value.__aexit__ = AsyncMock()

        mock_embedding = MagicMock()
        mock_embedding.init = MagicMock()
        mock_embedding.close = AsyncMock()

        mock_qdrant = MagicMock()
        mock_qdrant.init = MagicMock()
        mock_qdrant.close = AsyncMock()

        mock_es = MagicMock()
        mock_es.init = MagicMock()
        mock_es.close = AsyncMock()

        patches = [
            patch("app.scripts.build_meta_knowledge.dw_client_manager", mock_dw),
            patch("app.scripts.build_meta_knowledge.meta_client_manager", mock_meta),
            patch("app.scripts.build_meta_knowledge.embedding_client_manager", mock_embedding),
            patch("app.scripts.build_meta_knowledge.qdrant_client_manager", mock_qdrant),
            patch("app.scripts.build_meta_knowledge.es_client_manager", mock_es),
            patch("app.scripts.build_meta_knowledge.MetaKnowledgeService",
                  return_value=mock_service),
        ]

        from app.scripts.build_meta_knowledge import build

        for p in patches:
            p.start()

        try:
            await build(Path("fake_config.yaml"))
            mock_service.build_meta_knowledge.assert_called_once_with(Path("fake_config.yaml"))
            mock_dw.init.assert_called_once()
            mock_dw.close.assert_called_once()
        finally:
            for p in patches:
                p.stop()
