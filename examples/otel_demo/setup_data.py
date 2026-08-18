"""
Generates sample data, applies the Feast registry, and writes features into
the online store — so the OTEL demo has a real Feast feature server to serve.

Usage:
    cd MCP/examples/otel_demo
    python setup_data.py
"""

import os
import sys

import pandas as pd

REPO_DIR = os.path.join(os.path.dirname(__file__), "feature_repo")
DATA_DIR = os.path.join(REPO_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

NOW = pd.Timestamp.now()


def generate_customer_profiles() -> pd.DataFrame:
    customers = [
        {
            "customer_id": "C1001",
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "plan_tier": "enterprise",
            "account_age_days": 730,
            "total_spend": 24500.00,
        },
        {
            "customer_id": "C1002",
            "name": "Bob Smith",
            "email": "bob@example.com",
            "plan_tier": "pro",
            "account_age_days": 365,
            "total_spend": 8400.00,
        },
        {
            "customer_id": "C1003",
            "name": "Carol Lee",
            "email": "carol@example.com",
            "plan_tier": "starter",
            "account_age_days": 90,
            "total_spend": 990.00,
        },
    ]
    df = pd.DataFrame(customers)
    df["event_timestamp"] = NOW
    return df


def main() -> None:
    print("Generating customer profile data...")
    customers_df = generate_customer_profiles()
    customers_path = os.path.join(DATA_DIR, "customer_profiles.parquet")
    customers_df.to_parquet(customers_path, index=False)
    print(f"  Saved {len(customers_df)} customer profiles to {customers_path}")

    print("Applying Feast registry...")
    sys.path.insert(0, REPO_DIR)
    from feast import FeatureStore
    from features import customer, customer_profile

    store = FeatureStore(repo_path=REPO_DIR)
    store.apply([customer, customer_profile])

    print("Writing customer profiles to the online store...")
    store.write_to_online_store(feature_view_name="customer_profile", df=customers_df)
    print("  Done.")

    print("\nSetup complete! Start the demo with:")
    print("  ./run_demo.sh")


if __name__ == "__main__":
    main()
