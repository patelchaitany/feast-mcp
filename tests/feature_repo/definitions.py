from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from feast import Entity, FeatureService, FeatureView, Field, FileSource, PushSource
from feast.types import Array, Float32, Float64, Int64, String
from feast.value_type import ValueType

# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

driver: Entity = Entity(
    name="driver",
    join_keys=["driver_id"],
    value_type=ValueType.INT64,
)

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------

_REPO_DIR: str = os.path.dirname(os.path.abspath(__file__))
_PARQUET_PATH: str = os.path.join(_REPO_DIR, "data", "driver_stats.parquet")

driver_stats_source: FileSource = FileSource(
    name="driver_hourly_stats_source",
    path=_PARQUET_PATH,
    timestamp_field="event_timestamp",
    created_timestamp_column="created",
)

# ---------------------------------------------------------------------------
# Push source
# ---------------------------------------------------------------------------

driver_stats_push: PushSource = PushSource(
    name="driver_stats_push",
    batch_source=driver_stats_source,
)

# ---------------------------------------------------------------------------
# Feature view
# ---------------------------------------------------------------------------

driver_hourly_stats: FeatureView = FeatureView(
    name="driver_hourly_stats",
    entities=[driver],
    ttl=timedelta(hours=24),
    schema=[
        Field(name="conv_rate", dtype=Float64),
        Field(name="acc_rate", dtype=Float64),
        Field(name="avg_daily_trips", dtype=Int64),
    ],
    online=True,
    source=driver_stats_push,
)

# ---------------------------------------------------------------------------
# Document / vector feature view
# ---------------------------------------------------------------------------

_DOC_PARQUET_PATH: str = os.path.join(_REPO_DIR, "data", "documents.parquet")

doc_source: FileSource = FileSource(
    name="doc_source",
    path=_DOC_PARQUET_PATH,
    timestamp_field="event_timestamp",
    created_timestamp_column="created",
)

item: Entity = Entity(
    name="item",
    join_keys=["item_id"],
    value_type=ValueType.INT64,
)

document_embeddings: FeatureView = FeatureView(
    name="document_embeddings",
    entities=[item],
    ttl=timedelta(days=1),
    schema=[
        Field(name="embedding", dtype=Array(Float32), vector_index=True),
        Field(name="content", dtype=String),
    ],
    online=True,
    source=doc_source,
)

# ---------------------------------------------------------------------------
# Feature service
# ---------------------------------------------------------------------------

driver_activity: FeatureService = FeatureService(
    name="driver_activity",
    features=[driver_hourly_stats],
)

# ---------------------------------------------------------------------------
# Test data generation
# ---------------------------------------------------------------------------


def generate_test_data() -> None:
    """Create deterministic Parquet files for driver stats and document embeddings."""
    data_dir: Path = Path(_REPO_DIR) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # --- driver stats ---
    driver_ids: list[int] = list(range(1001, 1021))
    num_rows: int = len(driver_ids)

    base_ts: datetime = datetime(2026, 1, 1)
    timestamps: list[datetime] = [base_ts] * num_rows

    conv_rates: list[float] = [float(did) * 0.001 for did in driver_ids]
    acc_rates: list[float] = [float(did) * 0.0005 for did in driver_ids]
    avg_daily_trips: list[int] = [did % 100 for did in driver_ids]

    driver_table: pa.Table = pa.table(
        {
            "driver_id": pa.array(driver_ids, type=pa.int64()),
            "conv_rate": pa.array(conv_rates, type=pa.float64()),
            "acc_rate": pa.array(acc_rates, type=pa.float64()),
            "avg_daily_trips": pa.array(avg_daily_trips, type=pa.int64()),
            "event_timestamp": pa.array(timestamps, type=pa.timestamp("us")),
            "created": pa.array(timestamps, type=pa.timestamp("us")),
        }
    )

    driver_path: Path = data_dir / "driver_stats.parquet"
    pq.write_table(driver_table, str(driver_path))
    print(f"Wrote {num_rows} rows to {driver_path}")

    # --- document embeddings (128-dim vectors) ---
    embedding_dim: int = 128
    num_docs: int = 10
    item_ids: list[int] = list(range(1, num_docs + 1))
    contents: list[str] = [f"document about topic {i}" for i in item_ids]
    embeddings: list[list[float]] = [
        [float(i) / embedding_dim + float(j) / 1000 for j in range(embedding_dim)]
        for i in item_ids
    ]
    doc_ts: list[datetime] = [base_ts] * num_docs

    doc_table: pa.Table = pa.table(
        {
            "item_id": pa.array(item_ids, type=pa.int64()),
            "embedding": pa.array(
                embeddings, type=pa.list_(pa.float32())
            ),
            "content": pa.array(contents, type=pa.string()),
            "event_timestamp": pa.array(doc_ts, type=pa.timestamp("us")),
            "created": pa.array(doc_ts, type=pa.timestamp("us")),
        }
    )

    doc_path: Path = data_dir / "documents.parquet"
    pq.write_table(doc_table, str(doc_path))
    print(f"Wrote {num_docs} rows to {doc_path}")


if __name__ == "__main__":
    generate_test_data()
