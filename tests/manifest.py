from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ServerType(Enum):
    FEATURE_SERVER = "feature_server"
    REGISTRY = "registry"


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"


@dataclass(frozen=True)
class ToolTestSpec:
    tool_name: str
    feast_endpoint: str
    http_method: HttpMethod
    server_type: ServerType
    sample_inputs: list[dict[str, Any]]
    migrated: bool = False
    mutation: bool = False
    verify_endpoint: str | None = None
    verify_expected: dict[str, Any] | None = None
    skip_reason: str | None = None


@dataclass(frozen=True)
class DiscoveredEndpoint:
    path: str
    method: str
    server_type: ServerType
    request_schema: dict[str, Any]
    response_schema: dict[str, Any]
    parameters: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Feature Server Tools (11 entries)
# ---------------------------------------------------------------------------

FEATURE_SERVER_TOOLS: list[ToolTestSpec] = [
    ToolTestSpec(
        tool_name="features_get_online_features",
        feast_endpoint="/get-online-features",
        http_method=HttpMethod.POST,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[
            {
                "entities": {"driver_id": [1001, 1002]},
                "features": [
                    "driver_hourly_stats:conv_rate",
                    "driver_hourly_stats:acc_rate",
                ],
            },
        ],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="features_search",
        feast_endpoint="/search",
        http_method=HttpMethod.POST,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[
            {
                "features": [
                    "document_embeddings:embedding",
                    "document_embeddings:content",
                ],
                "query": [0.1] * 128,
                "top_k": 3,
                "api_version": 2,
                "distance_metric": "COSINE",
            },
        ],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="retrieve_online_documents",
        feast_endpoint="/retrieve-online-documents",
        http_method=HttpMethod.POST,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[
            {
                "features": [
                    "document_embeddings:embedding",
                    "document_embeddings:content",
                ],
                "query": [0.1] * 128,
                "top_k": 3,
                "api_version": 2,
                "distance_metric": "COSINE",
            },
        ],
    ),
    ToolTestSpec(
        tool_name="features_push",
        feast_endpoint="/push",
        http_method=HttpMethod.POST,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[
            {
                "push_source_name": "driver_stats_push",
                "df": {
                    "driver_id": [9001],
                    "conv_rate": [0.85],
                    "acc_rate": [0.45],
                    "avg_daily_trips": [15],
                    "event_timestamp": ["2026-01-01T00:00:00"],
                    "created": ["2026-01-01T00:00:00"],
                },
                "to": "online",
            },
        ],
        migrated=True,
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="write_to_online_store",
        feast_endpoint="/write-to-online-store",
        http_method=HttpMethod.POST,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[
            {
                "feature_view_name": "driver_hourly_stats",
                "df": {
                    "driver_id": [9002],
                    "conv_rate": [0.90],
                    "acc_rate": [0.50],
                    "avg_daily_trips": [20],
                    "event_timestamp": ["2026-01-01T00:00:00"],
                    "created": ["2026-01-01T00:00:00"],
                },
                "allow_registry_cache": True,
            },
        ],
        mutation=True,
        verify_endpoint="/get-online-features",
    ),
    ToolTestSpec(
        tool_name="features_materialize",
        feast_endpoint="/materialize",
        http_method=HttpMethod.POST,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[
            {
                "start_ts": "2026-01-01T00:00:00",
                "end_ts": "2026-01-02T00:00:00",
            },
        ],
        migrated=True,
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="features_materialize_incremental",
        feast_endpoint="/materialize-incremental",
        http_method=HttpMethod.POST,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[
            {
                "end_ts": "2026-01-02T00:00:00",
            },
        ],
        migrated=True,
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="features_health",
        feast_endpoint="/health",
        http_method=HttpMethod.GET,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[{}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="features_list_vector_stores",
        feast_endpoint="/v1/vector_stores",
        http_method=HttpMethod.GET,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[{}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="features_get_vector_store",
        feast_endpoint="/v1/vector_stores/{vector_store_id}",
        http_method=HttpMethod.GET,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[
            {
                "vector_store_id": "vs_354af22fc1693607e9b0aa24",
            },
        ],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="features_vector_store_search",
        feast_endpoint="/v1/vector_stores/{vector_store_id}/search",
        http_method=HttpMethod.POST,
        server_type=ServerType.FEATURE_SERVER,
        sample_inputs=[
            {
                "vector_store_id": "vs_354af22fc1693607e9b0aa24",
                "query": "topic",
                "max_num_results": 5,
            },
        ],
        migrated=True,
        skip_reason="requires embedding_model config (e.g. sentence-transformers)",
    ),
]


# ---------------------------------------------------------------------------
# Registry Tools (59 entries)
# ---------------------------------------------------------------------------

REGISTRY_TOOLS: list[ToolTestSpec] = [
    # --- entities (5 routes) ---
    ToolTestSpec(
        tool_name="registry_list_entities",
        feast_endpoint="/api/v1/entities",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="list_all_entities",
        feast_endpoint="/api/v1/entities/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    ToolTestSpec(
        tool_name="registry_get_entity",
        feast_endpoint="/api/v1/entities/{name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"name": "driver", "project": "mcp_test_project"}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="apply_entity",
        feast_endpoint="/api/v1/entities",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "name": "test_entity",
                "project": "mcp_test_project",
                "join_key": "test_id",
                "value_type": 2,
                "description": "test entity",
            },
        ],
        mutation=True,
        verify_endpoint="/api/v1/entities/{name}",
    ),
    ToolTestSpec(
        tool_name="delete_entity",
        feast_endpoint="/api/v1/entities/{name}",
        http_method=HttpMethod.DELETE,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"name": "test_entity", "project": "mcp_test_project"}],
        mutation=True,
    ),
    # --- data_sources (5 routes) ---
    ToolTestSpec(
        tool_name="registry_list_data_sources",
        feast_endpoint="/api/v1/data_sources",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="list_all_data_sources",
        feast_endpoint="/api/v1/data_sources/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    ToolTestSpec(
        tool_name="registry_get_data_source",
        feast_endpoint="/api/v1/data_sources/{name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {"name": "driver_hourly_stats_source", "project": "mcp_test_project"},
        ],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="apply_data_source",
        feast_endpoint="/api/v1/data_sources",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "name": "test_source",
                "project": "mcp_test_project",
                "type": 1,
                "description": "test source",
            },
        ],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="delete_data_source",
        feast_endpoint="/api/v1/data_sources/{name}",
        http_method=HttpMethod.DELETE,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"name": "test_source", "project": "mcp_test_project"}],
        mutation=True,
    ),
    # --- feature_views (5 routes) ---
    ToolTestSpec(
        tool_name="registry_list_feature_views",
        feast_endpoint="/api/v1/feature_views",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="list_all_feature_views",
        feast_endpoint="/api/v1/feature_views/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    ToolTestSpec(
        tool_name="registry_get_feature_view",
        feast_endpoint="/api/v1/feature_views/{name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {"name": "driver_hourly_stats", "project": "mcp_test_project"},
        ],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="apply_feature_view",
        feast_endpoint="/api/v1/feature_views",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "name": "test_fv",
                "project": "mcp_test_project",
                "entities": ["driver"],
                "features": [{"name": "test_feat", "value_type": 2}],
                "batch_source": "driver_stats_source",
                "online": True,
            },
        ],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="delete_feature_view",
        feast_endpoint="/api/v1/feature_views/{name}",
        http_method=HttpMethod.DELETE,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"name": "test_fv", "project": "mcp_test_project"}],
        mutation=True,
    ),
    # --- feature_services (5 routes) ---
    ToolTestSpec(
        tool_name="registry_list_feature_services",
        feast_endpoint="/api/v1/feature_services",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="list_all_feature_services",
        feast_endpoint="/api/v1/feature_services/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    ToolTestSpec(
        tool_name="registry_get_feature_service",
        feast_endpoint="/api/v1/feature_services/{name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {"name": "driver_activity", "project": "mcp_test_project"},
        ],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="apply_feature_service",
        feast_endpoint="/api/v1/feature_services",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "name": "test_fs",
                "project": "mcp_test_project",
                "features": [
                    {
                        "feature_view_name": "driver_hourly_stats",
                        "feature_names": ["conv_rate"],
                    },
                ],
            },
        ],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="delete_feature_service",
        feast_endpoint="/api/v1/feature_services/{name}",
        http_method=HttpMethod.DELETE,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"name": "test_fs", "project": "mcp_test_project"}],
        mutation=True,
    ),
    # --- features (5 routes, ALL read-only) ---
    ToolTestSpec(
        tool_name="registry_list_features",
        feast_endpoint="/api/v1/features",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="get_feature",
        feast_endpoint="/api/v1/features/{feature_view}/{name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "feature_view": "driver_hourly_stats",
                "name": "conv_rate",
                "project": "mcp_test_project",
            },
        ],
    ),
    ToolTestSpec(
        tool_name="list_all_features",
        feast_endpoint="/api/v1/features/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    ToolTestSpec(
        tool_name="list_labels",
        feast_endpoint="/api/v1/labels",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="list_all_labels",
        feast_endpoint="/api/v1/labels/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    # --- label_views (3 routes, ALL read-only) ---
    ToolTestSpec(
        tool_name="list_label_views",
        feast_endpoint="/api/v1/label_views",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="list_all_label_views",
        feast_endpoint="/api/v1/label_views/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    ToolTestSpec(
        tool_name="get_label_view",
        feast_endpoint="/api/v1/label_views/{name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {"name": "test_label_view", "project": "mcp_test_project"},
        ],
    ),
    # --- saved_datasets (9 routes) ---
    ToolTestSpec(
        tool_name="list_saved_datasets",
        feast_endpoint="/api/v1/saved_datasets",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="list_all_saved_datasets",
        feast_endpoint="/api/v1/saved_datasets/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    ToolTestSpec(
        tool_name="get_saved_dataset",
        feast_endpoint="/api/v1/saved_datasets/{name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {"name": "test_dataset", "project": "mcp_test_project"},
        ],
    ),
    ToolTestSpec(
        tool_name="get_saved_dataset_data",
        feast_endpoint="/api/v1/saved_datasets/data/{name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "name": "test_dataset",
                "project": "mcp_test_project",
                "limit": 10,
            },
        ],
    ),
    ToolTestSpec(
        tool_name="get_saved_dataset_job",
        feast_endpoint="/api/v1/saved_datasets/jobs/{job_id}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"job_id": "test-job-1"}],
    ),
    ToolTestSpec(
        tool_name="list_saved_dataset_jobs",
        feast_endpoint="/api/v1/saved_datasets/jobs",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="register_saved_dataset",
        feast_endpoint="/api/v1/saved_datasets",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "name": "test_sd",
                "project": "mcp_test_project",
                "features": ["driver_hourly_stats:conv_rate"],
                "join_keys": ["driver_id"],
            },
        ],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="create_saved_dataset",
        feast_endpoint="/api/v1/saved_datasets/create",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "name": "test_sd_create",
                "project": "mcp_test_project",
                "feature_service_name": "driver_activity",
                "entity_source_type": "inline",
            },
        ],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="delete_saved_dataset",
        feast_endpoint="/api/v1/saved_datasets/{name}",
        http_method=HttpMethod.DELETE,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"name": "test_sd", "project": "mcp_test_project"}],
        mutation=True,
    ),
    # --- permissions (4 routes) ---
    ToolTestSpec(
        tool_name="list_permissions",
        feast_endpoint="/api/v1/permissions",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="get_permission",
        feast_endpoint="/api/v1/permissions/{name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {"name": "admin_permission", "project": "mcp_test_project"},
        ],
    ),
    ToolTestSpec(
        tool_name="apply_permission",
        feast_endpoint="/api/v1/permissions",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "name": "test_perm",
                "project": "mcp_test_project",
                "types": ["FEATURE_VIEW"],
                "actions": ["DESCRIBE", "READ_ONLINE"],
                "policy": {
                    "role_based_policy": {"roles": ["test-role"]},
                },
            },
        ],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="delete_permission",
        feast_endpoint="/api/v1/permissions/{name}",
        http_method=HttpMethod.DELETE,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"name": "test_perm", "project": "mcp_test_project"}],
        mutation=True,
    ),
    # --- projects (3 routes) ---
    ToolTestSpec(
        tool_name="registry_list_projects",
        feast_endpoint="/api/v1/projects",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="registry_get_project",
        feast_endpoint="/api/v1/projects/{name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"name": "mcp_test_project"}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="refresh_registry",
        feast_endpoint="/api/v1/registry/refresh",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
        mutation=True,
    ),
    # --- lineage (5 routes, ALL read-only) ---
    ToolTestSpec(
        tool_name="get_registry_lineage",
        feast_endpoint="/api/v1/lineage/registry",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="get_registry_lineage_all",
        feast_endpoint="/api/v1/lineage/registry/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    ToolTestSpec(
        tool_name="registry_get_lineage",
        feast_endpoint="/api/v1/lineage/objects/{object_type}/{object_name}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "object_type": "featureView",
                "object_name": "driver_hourly_stats",
                "project": "mcp_test_project",
            },
        ],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="registry_get_lineage",
        feast_endpoint="/api/v1/lineage/complete",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
        migrated=True,
    ),
    ToolTestSpec(
        tool_name="get_complete_lineage_all",
        feast_endpoint="/api/v1/lineage/complete/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    # --- metrics (3 routes, ALL read-only) ---
    ToolTestSpec(
        tool_name="get_resource_counts",
        feast_endpoint="/api/v1/metrics/resource_counts",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="get_popular_tags",
        feast_endpoint="/api/v1/metrics/popular_tags",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project", "limit": 4}],
    ),
    ToolTestSpec(
        tool_name="get_recently_visited",
        feast_endpoint="/api/v1/metrics/recently_visited",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    # --- monitoring (11 routes) ---
    ToolTestSpec(
        tool_name="compute_metrics",
        feast_endpoint="/api/v1/monitoring/compute",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "project": "mcp_test_project",
                "feature_view_name": "driver_hourly_stats",
            },
        ],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="auto_compute_metrics",
        feast_endpoint="/api/v1/monitoring/auto_compute",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="compute_log_metrics",
        feast_endpoint="/api/v1/monitoring/compute/log",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "project": "mcp_test_project",
                "feature_service_name": "driver_activity",
            },
        ],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="auto_compute_log_metrics",
        feast_endpoint="/api/v1/monitoring/auto_compute/log",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="compute_transient_metrics",
        feast_endpoint="/api/v1/monitoring/compute/transient",
        http_method=HttpMethod.POST,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "project": "mcp_test_project",
                "feature_view_name": "driver_hourly_stats",
            },
        ],
        mutation=True,
    ),
    ToolTestSpec(
        tool_name="get_monitoring_job",
        feast_endpoint="/api/v1/monitoring/jobs/{job_id}",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"job_id": "test-job-1"}],
    ),
    ToolTestSpec(
        tool_name="get_feature_metrics",
        feast_endpoint="/api/v1/monitoring/metrics/features",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="get_feature_view_metrics",
        feast_endpoint="/api/v1/monitoring/metrics/feature_views",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="get_feature_service_metrics",
        feast_endpoint="/api/v1/monitoring/metrics/feature_services",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="get_baseline_metrics",
        feast_endpoint="/api/v1/monitoring/metrics/baseline",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[
            {
                "project": "mcp_test_project",
                "feature_view_name": "driver_hourly_stats",
                "feature_name": "conv_rate",
            },
        ],
    ),
    ToolTestSpec(
        tool_name="get_timeseries_metrics",
        feast_endpoint="/api/v1/monitoring/metrics/timeseries",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    # --- search (1 route, read-only) ---
    ToolTestSpec(
        tool_name="registry_search_registry",
        feast_endpoint="/api/v1/search",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"query": "driver"}],
        migrated=True,
    ),
    # --- compute_engines (3 routes, ALL read-only) ---
    ToolTestSpec(
        tool_name="list_compute_engines",
        feast_endpoint="/api/v1/compute_engines",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
    ToolTestSpec(
        tool_name="list_all_compute_engines",
        feast_endpoint="/api/v1/compute_engines/all",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{}],
    ),
    ToolTestSpec(
        tool_name="list_materialization_jobs",
        feast_endpoint="/api/v1/materialization_jobs",
        http_method=HttpMethod.GET,
        server_type=ServerType.REGISTRY,
        sample_inputs=[{"project": "mcp_test_project"}],
    ),
]
