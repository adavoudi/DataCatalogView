"""Query the Redshift Spectrum external schema view.

Connects to the Redshift Serverless workgroup using the caller's own AWS
credentials (IAM authentication), creates the external schema `dcv_spectrum`
if it does not already exist, then queries the view
`dcv_spectrum.sample_data_view` and prints the results.

The RedshiftSpectrumRole is an internal service role attached to the Redshift
Serverless namespace — Redshift assumes it automatically when resolving Spectrum
queries against the Glue catalog. The script does not need to assume it.

Prerequisites:
  - `terraform apply` has been run and `terraform output -json` has been
    written to `terraform/terraform_output.json`.
  - The Redshift workgroup is reachable from this machine (VPC endpoint,
    VPN, or bastion host — the workgroup is not publicly accessible).
  - The caller's IAM identity has `redshift-serverless:GetCredentials` on
    the workgroup, or is the admin user whose password is in Secrets Manager.
  - `redshift_connector` is installed:  pip install redshift_connector

Usage:
    python query_spectrum_view.py

Environment variable overrides (all optional):
    REDSHIFT_HOST          — workgroup endpoint address
    REDSHIFT_PORT          — workgroup port (default: 5439)
    REDSHIFT_DATABASE      — database to connect to (default: dev)
    REDSHIFT_SPECTRUM_ROLE — ARN of RedshiftSpectrumRole (used only for CREATE EXTERNAL SCHEMA)
    REDSHIFT_USER          — Redshift user (default: admin)
    AWS_REGION             — AWS region (default: eu-central-1)

Exit codes:
    0 - Query succeeded
    1 - Configuration or connection error
    2 - Schema creation error
    3 - Query execution error
"""

import sys

import boto3
import redshift_connector

from config import ACCOUNT_ID, DATABASE_NAME, REGION, TABLE_NAME, _get_config

# ---------------------------------------------------------------------------
# Redshift-specific configuration (extends config.py pattern)
# ---------------------------------------------------------------------------

REDSHIFT_HOST: str = _get_config(
    "REDSHIFT_HOST", "redshift_endpoint_address"
)
REDSHIFT_PORT: int = int(
    _get_config("REDSHIFT_PORT", "redshift_endpoint_port", default="5439")
)
REDSHIFT_DATABASE: str = _get_config(
    "REDSHIFT_DATABASE", "redshift_database", default="dev"
)
REDSHIFT_SPECTRUM_ROLE_ARN: str = _get_config(
    "REDSHIFT_SPECTRUM_ROLE", "redshift_spectrum_role_arn"
)
REDSHIFT_USER: str = _get_config(
    "REDSHIFT_USER", "redshift_user", default="admin"
)

# External schema and table/view to query
SPECTRUM_SCHEMA: str = "dcv_spectrum"
VIEW_NAME: str = "sample_data_view"


def connect_to_redshift(
    host: str,
    port: int,
    database: str,
    user: str,
    region: str,
) -> redshift_connector.Connection:
    """Open a connection to Redshift Serverless using the caller's IAM credentials.

    Uses `redshift_connector` with IAM authentication. The caller's ambient
    AWS credentials (env vars, ~/.aws/credentials, instance profile, etc.) are
    used directly — no role assumption is needed.

    Args:
        host: Redshift Serverless endpoint address.
        port: Endpoint port (typically 5439).
        database: Database name to connect to.
        user: Redshift user name.
        region: AWS region.

    Returns:
        An open `redshift_connector.Connection`.

    Raises:
        RuntimeError: If the connection cannot be established.
    """
    try:
        # Resolve ambient credentials (env vars, ~/.aws/credentials, instance profile)
        session = boto3.Session(region_name=region)
        creds = session.get_credentials().get_frozen_credentials()

        # Extract workgroup name from the endpoint hostname
        # Format: <workgroup-name>.<account-id>.<region>.redshift-serverless.amazonaws.com
        workgroup_name = host.split(".")[0]

        conn = redshift_connector.connect(
            iam=True,
            host=host,
            port=port,
            database=database,
            user=user,
            access_key_id=creds.access_key,
            secret_access_key=creds.secret_key,
            session_token=creds.token,
            region=region,
            is_serverless=True,
            serverless_work_group=workgroup_name,
        )
        return conn
    except Exception as e:
        raise RuntimeError(
            f"Failed to connect to Redshift at {host}:{port}: {e}"
        ) from e


def ensure_external_schema(
    conn: redshift_connector.Connection,
    schema: str,
    glue_database: str,
    iam_role_arn: str,
    catalog_id: str,
    region: str,
) -> None:
    """Create the Spectrum external schema if it does not already exist.

    Checks `SVV_EXTERNAL_SCHEMAS` for the schema name. If absent, issues
    `CREATE EXTERNAL SCHEMA` pointing at the Glue Data Catalog database.
    This is idempotent — running it when the schema already exists is a no-op.

    Args:
        conn: An open Redshift connection.
        schema: The external schema name to create (e.g., `dcv_spectrum`).
        glue_database: The Glue Data Catalog database name (e.g., `dcv_db`).
        iam_role_arn: ARN of the IAM role Spectrum uses for catalog access.
        catalog_id: AWS account ID that owns the Glue catalog.
        region: AWS region where the Glue catalog lives.

    Raises:
        RuntimeError: If the schema check or creation query fails.
    """
    check_sql = (
        "SELECT COUNT(*) FROM SVV_EXTERNAL_SCHEMAS "
        f"WHERE schemaname = '{schema}'"
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(check_sql)
            (count,) = cursor.fetchone()
    except Exception as e:
        raise RuntimeError(f"Failed to check for external schema '{schema}': {e}") from e

    if count > 0:
        print(f"  External schema '{schema}' already exists — skipping creation.")
        return

    print(f"  External schema '{schema}' not found — creating it...")
    create_sql = (
        f"CREATE EXTERNAL SCHEMA {schema} "
        f"FROM DATA CATALOG "
        f"DATABASE '{glue_database}' "
        f"IAM_ROLE '{iam_role_arn}' "
        f"CATALOG_ID '{catalog_id}' "
        f"REGION '{region}'"
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(create_sql)
        conn.commit()
        print(f"  External schema '{schema}' created successfully.")
    except Exception as e:
        raise RuntimeError(
            f"Failed to create external schema '{schema}': {e}"
        ) from e


def ensure_redshift_dialect(
    conn: redshift_connector.Connection,
    schema: str,
    view: str,
    glue_database: str,
    table: str,
) -> None:
    """Add the Redshift dialect to a Data Catalog view if not already present.

    Runs ALTER EXTERNAL VIEW ... AS SELECT ... to register the Redshift SQL
    dialect for the multi-dialect view. If the dialect already exists, the
    FORCE keyword ensures it is updated without error.

    Args:
        conn: An open Redshift connection.
        schema: The external schema name (e.g., `dcv_spectrum`).
        view: The view name (e.g., `sample_data_view`).
        glue_database: The Glue database name (e.g., `dcv_db`).
        table: The base table name (e.g., `sample_data`).

    Raises:
        RuntimeError: If the ALTER statement fails.
    """
    alter_sql = (
        f'ALTER EXTERNAL VIEW "{schema}"."{view}" FORCE AS '
        f'SELECT * FROM "{schema}"."{table}"'
    )
    print(f"  Running: {alter_sql}")
    try:
        # Must end any open transaction before running DDL that cannot be in a tx block
        conn.rollback()
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(alter_sql)
        conn.autocommit = False
        print(f"  Redshift dialect ensured successfully.")
    except Exception as e:
        conn.autocommit = False
        raise RuntimeError(
            f"Failed to add Redshift dialect to view '{schema}.{view}': {e}"
        ) from e


def query_spectrum_view(
    conn: redshift_connector.Connection,
    schema: str,
    view: str,
) -> list[dict]:
    """Execute SELECT * against the Spectrum external schema view.

    Args:
        conn: An open Redshift connection.
        schema: The external schema name (e.g., `dcv_spectrum`).
        view: The view name (e.g., `sample_data_view`).

    Returns:
        A list of row dicts mapping column name → value.

    Raises:
        RuntimeError: If the query fails.
    """
    sql = f'SELECT * FROM "{schema}"."{view}"'
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        raise RuntimeError(
            f'Query failed — "{sql}": {e}'
        ) from e


def print_results(rows: list[dict]) -> None:
    """Print query results in a readable table format.

    Args:
        rows: List of row dicts from query_spectrum_view.
    """
    if not rows:
        print("  (no rows returned)")
        return

    columns = list(rows[0].keys())
    col_widths = {col: max(len(col), max(len(str(r[col])) for r in rows)) for col in columns}

    header = "  " + "  ".join(col.ljust(col_widths[col]) for col in columns)
    separator = "  " + "  ".join("-" * col_widths[col] for col in columns)

    print(header)
    print(separator)
    for row in rows:
        line = "  " + "  ".join(str(row[col]).ljust(col_widths[col]) for col in columns)
        print(line)
    print()
    print(f"  {len(rows)} row(s) returned.")


def main() -> None:
    """Connect to Redshift using ambient IAM credentials and query the Spectrum view."""
    print("Redshift Spectrum — Query sample_data_view")
    print("=" * 60)
    print()

    # Step 1: Connect to Redshift Serverless using ambient AWS credentials.
    # RedshiftSpectrumRole is an internal service role attached to the namespace —
    # Redshift assumes it automatically for Spectrum catalog calls. The script
    # connects as the admin user using the caller's own IAM credentials.
    print(f"Connecting to Redshift Serverless: {REDSHIFT_HOST}:{REDSHIFT_PORT}")
    print(f"  Database : {REDSHIFT_DATABASE}")
    print(f"  User     : {REDSHIFT_USER}")
    try:
        conn = connect_to_redshift(
            host=REDSHIFT_HOST,
            port=REDSHIFT_PORT,
            database=REDSHIFT_DATABASE,
            user=REDSHIFT_USER,
            region=REGION,
        )
        print("  Connected successfully.")
    except RuntimeError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print()

    # Step 2: Ensure the external schema exists (create it if not)
    print(f"Checking external schema '{SPECTRUM_SCHEMA}'...")
    try:
        ensure_external_schema(
            conn=conn,
            schema=SPECTRUM_SCHEMA,
            glue_database=DATABASE_NAME,
            iam_role_arn=REDSHIFT_SPECTRUM_ROLE_ARN,
            catalog_id=ACCOUNT_ID,
            region=REGION,
        )
    except RuntimeError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        conn.close()
        sys.exit(2)

    print()

    # Step 3: Add the Redshift dialect to the Data Catalog view (idempotent)
    # The view was created via Athena with only the Trino dialect. Redshift
    # needs its own dialect registered via ALTER EXTERNAL VIEW.
    print(f"Ensuring Redshift dialect on view '{SPECTRUM_SCHEMA}.{VIEW_NAME}'...")
    try:
        ensure_redshift_dialect(conn, SPECTRUM_SCHEMA, VIEW_NAME, DATABASE_NAME, TABLE_NAME)
    except RuntimeError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        conn.close()
        sys.exit(2)

    print()

    # Step 4: Query the Spectrum view
    sql = f'SELECT * FROM "{SPECTRUM_SCHEMA}"."{VIEW_NAME}"'
    print(f"Executing: {sql}")
    print()
    try:
        rows = query_spectrum_view(conn, SPECTRUM_SCHEMA, VIEW_NAME)
    except RuntimeError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        conn.close()
        sys.exit(3)
    finally:
        conn.close()

    # Step 4: Print results
    print_results(rows)


if __name__ == "__main__":
    main()
