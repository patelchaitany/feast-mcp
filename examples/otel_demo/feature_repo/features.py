from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource
from feast.data_format import ParquetFormat
from feast.types import Float64, Int64, String, ValueType

customer = Entity(
    name="customer_id",
    description="Unique customer identifier",
    value_type=ValueType.STRING,
)

customer_profile_source = FileSource(
    file_format=ParquetFormat(),
    path="data/customer_profiles.parquet",
    timestamp_field="event_timestamp",
)

customer_profile = FeatureView(
    name="customer_profile",
    entities=[customer],
    schema=[
        Field(name="name", dtype=String),
        Field(name="email", dtype=String),
        Field(name="plan_tier", dtype=String),
        Field(name="account_age_days", dtype=Int64),
        Field(name="total_spend", dtype=Float64),
    ],
    source=customer_profile_source,
    ttl=timedelta(days=1),
)
