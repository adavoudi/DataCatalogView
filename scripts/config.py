"""
Shared configuration for AWS Lakehouse SI Tagging scripts.

Reads configuration values from environment variables first, falling back to
a Terraform output JSON file (generated via `terraform output -json > terraform_output.json`).
"""

import json
import os
from pathlib import Path

# Path to Terraform output JSON file (relative to project root)
_TERRAFORM_OUTPUT_FILE = (
    Path(__file__).resolve().parent.parent / "terraform" / "terraform_output.json"
)


def _load_terraform_outputs() -> dict:
    """Load Terraform outputs from JSON file if it exists.

    Expected format (from `terraform output -json`):
    {
        "output_name": {
            "value": "actual_value",
            "type": "string"
        }
    }
    """
    
    if _TERRAFORM_OUTPUT_FILE.is_file():
        with open(_TERRAFORM_OUTPUT_FILE, "r") as f:
            raw = json.load(f)
        # Extract the "value" field from each output
        return {key: entry["value"] for key, entry in raw.items() if "value" in entry}
    return {}


def _get_config(env_var: str, tf_output_key: str, default: str | None = None) -> str:
    """Resolve a configuration value.

    Priority:
      1. Environment variable
      2. Terraform output JSON value
      3. Provided default

    Raises ValueError if no value can be resolved.
    """
    # 1. Environment variable
    value = os.environ.get(env_var)
    if value:
        return value

    # 2. Terraform output JSON
    tf_outputs = _load_terraform_outputs()
    value = tf_outputs.get(tf_output_key)
    if value:
        return value

    # 3. Default
    if default is not None:
        return default

    raise ValueError(
        f"Configuration '{env_var}' is not set. "
        f"Set the environment variable '{env_var}' or ensure "
        f"'{tf_output_key}' exists in {_TERRAFORM_OUTPUT_FILE}."
    )


# --- Configuration Values ---

ACCOUNT_ID: str = _get_config("ACCOUNT_ID", "account_id", default="")
REGION: str = _get_config("AWS_REGION", "region", default="eu-central-1")
DATABASE_NAME: str = _get_config("DATABASE_NAME", "database_name")
TABLE_NAME: str = _get_config("TABLE_NAME", "table_name", default="sample_data")
VIEW_NAME: str = _get_config("VIEW_NAME", "view_name", default="sample_data_view")
DATA_LAKE_BUCKET: str = _get_config("DATA_LAKE_BUCKET", "data_lake_bucket_name")
QUERY_RESULTS_BUCKET: str = _get_config(
    "QUERY_RESULTS_BUCKET", "query_results_bucket_name"
)
ATHENA_WORKGROUP: str = _get_config("ATHENA_WORKGROUP", "workgroup_name")
print(ATHENA_WORKGROUP)
ADMIN_ROLE_ARN: str = _get_config("ADMIN_ROLE_ARN", "admin_role_arn")
SI_ROLE_ARN: str = _get_config("SI_ROLE_ARN", "si_role_arn")
NONSI_ROLE_ARN: str = _get_config("NONSI_ROLE_ARN", "nonsi_role_arn")
