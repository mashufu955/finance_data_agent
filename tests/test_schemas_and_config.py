"""Tests for schemas, prompt_loader, meta_config."""

from __future__ import annotations

import pytest


class TestQuerySchema:
    def test_valid_query(self):
        from app.schemas.chat import QuerySchema
        schema = QuerySchema(query="test query")
        assert schema.query == "test query"

    def test_missing_query_raises(self):
        from app.schemas.chat import QuerySchema
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            QuerySchema()


class TestPromptLoader:
    def test_load_existing_prompt(self):
        from app.prompt.prompt_loader import load_prompt
        content = load_prompt("classify_query")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_load_nonexistent_prompt_raises(self):
        from app.prompt.prompt_loader import load_prompt
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt_xyz")


class TestMetaConfig:
    def test_meta_config_loaded(self):
        from app.config.meta_config import meta_config
        assert meta_config is not None
        assert hasattr(meta_config, "tables")
        assert hasattr(meta_config, "metrics")

    def test_meta_config_tables_not_empty(self):
        from app.config.meta_config import meta_config
        assert len(meta_config.tables) > 0

    def test_meta_config_metrics_not_empty(self):
        from app.config.meta_config import meta_config
        assert len(meta_config.metrics) > 0

    def test_table_config_fields(self):
        from app.config.meta_config import meta_config
        table = meta_config.tables[0]
        assert table.name
        assert table.role in ("fact", "dim")
        assert table.description
        assert len(table.columns) > 0

    def test_column_config_fields(self):
        from app.config.meta_config import meta_config
        col = meta_config.tables[0].columns[0]
        assert col.name
        assert col.role
        assert col.description
        assert isinstance(col.alias, list)
        assert isinstance(col.sync, bool)

    def test_metric_config_fields(self):
        from app.config.meta_config import meta_config
        metric = meta_config.metrics[0]
        assert metric.name
        assert metric.description
        assert len(metric.relevant_columns) > 0
        assert isinstance(metric.alias, list)
