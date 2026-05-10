"""Create a Data Catalog view with SI tag assignment in the AWS Lakehouse.

This script assumes the AdminRole, creates a PROTECTED MULTI DIALECT VIEW
over the base table, and assigns SI tags to the view columns matching the
base table tag assignments.

Column tag assignments:
  - id   → SI=false
  - name → SI=false
  - ssn  → SI=true

Exit codes:
    0 - Success
    1 - Role assumption failure
    2 - View creation failure
    3 - Tag assignment failure
"""

import sys

import boto3
from botocore.exceptions import ClientError

from config import (
    ADMIN_ROLE_ARN,
    ATHENA_WORKGROUP,
    DATABASE_NAME,
    REGION,
    TABLE_NAME,
    VIEW_NAME,
)
from helpers import assume_role, run_athena_query, wait_for_query

# Column-to-SI-value mapping for the view (mirrors base table tags)
COLUMN_TAG_MAP: dict[str, str] = {
    "id": "false",
    "name": "false",
    "ssn": "true",
}


def create_data_catalog_view(session: boto3.Session) -> None:
    """Drop (if exists) and create a PROTECTED MULTI DIALECT VIEW over the base table.

    First drops the view if it already exists, then creates it fresh using the
    CREATE PROTECTED MULTI DIALECT VIEW syntax required by Lake Formation Data
    Catalog views to enable tag-based access control.

    Args:
        session: A boto3 Session with AdminRole credentials.

    Raises:
        RuntimeError: If either the drop or create query fails.
    """
    # Step 1: Drop the view if it already exists
    drop_query = f"DROP VIEW IF EXISTS {DATABASE_NAME}.{VIEW_NAME}"

    # print(f"Dropping view {DATABASE_NAME}.{VIEW_NAME} if it exists...")
    # query_id = run_athena_query(session, drop_query, DATABASE_NAME, ATHENA_WORKGROUP)
    # wait_for_query(session, query_id)
    # print(f"View {DATABASE_NAME}.{VIEW_NAME} dropped (or did not exist).")
    # return

    # Step 2: Create the view
    create_query = (
        f"CREATE OR REPLACE PROTECTED MULTI DIALECT VIEW {DATABASE_NAME}.{VIEW_NAME} SECURITY DEFINER AS "
        f"SELECT * FROM {DATABASE_NAME}.{TABLE_NAME}"
    )

    print(f"Creating Data Catalog view {DATABASE_NAME}.{VIEW_NAME}...")
    query_id = run_athena_query(session, create_query, DATABASE_NAME, ATHENA_WORKGROUP)
    wait_for_query(session, query_id)
    print(f"View {DATABASE_NAME}.{VIEW_NAME} created successfully.")


def assign_view_tags(
    lf_client, database: str, view: str, column_tag_map: dict
) -> None:
    """Assign SI tags to view columns matching base table tags.

    Iterates over the column tag map and assigns the corresponding SI tag
    value to each column in the view. Continues on individual column failure
    and reports all failures at the end.

    Args:
        lf_client: A boto3 Lake Formation client.
        database: The Glue database name.
        view: The view name.
        column_tag_map: A dict mapping column names to SI tag values
            (e.g., {"id": "false", "name": "false", "ssn": "true"}).

    Raises:
        RuntimeError: If one or more tag assignments fail, with a message
            listing all failed columns and reasons.
    """
    failures: list[str] = []

    print(f"\nAssigning SI tags to view columns in {database}.{view}:")
    for column, si_value in column_tag_map.items():
        print(f"  Assigning SI={si_value} to column '{column}'...", end=" ")
        try:
            response = lf_client.add_lf_tags_to_resource(
                Resource={
                    "TableWithColumns": {
                        "DatabaseName": database,
                        "Name": view,
                        "ColumnNames": [column],
                    }
                },
                LFTags=[
                    {
                        "TagKey": "SI",
                        "TagValues": [si_value],
                    }
                ],
            )
            # Check for partial failures in the response
            lf_failures = response.get("Failures", [])
            if lf_failures:
                error_msg = (
                    f"Column '{column}' (SI={si_value}): "
                    f"{lf_failures[0].get('Error', {}).get('ErrorMessage', 'Unknown error')}"
                )
                failures.append(error_msg)
                print("FAILED")
                print(f"    {error_msg}")
            else:
                print("OK")
        except ClientError as e:
            print(e)
            error_msg = (
                f"Column '{column}' (SI={si_value}): "
                f"{e.response['Error']['Message']}"
            )
            failures.append(error_msg)
            print("FAILED")
            print(f"    {error_msg}")
        except Exception as e:
            error_msg = f"Column '{column}' (SI={si_value}): {e}"
            failures.append(error_msg)
            print("FAILED")
            print(f"    {error_msg}")

    if failures:
        raise RuntimeError(
            f"{len(failures)} tag assignment failure(s):\n"
            + "\n".join(f"  - {f}" for f in failures)
        )

    print("\nAll view column tags assigned successfully.")


def main() -> None:
    """Assume AdminRole, create view, assign tags to view columns."""
    # Step 1: Assume AdminRole
    try:
        print(f"Assuming AdminRole: {ADMIN_ROLE_ARN}")
        session = assume_role(ADMIN_ROLE_ARN, "CreateViewSession", REGION)
        print("Successfully assumed AdminRole.")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 2: Create the Data Catalog view
    try:
        create_data_catalog_view(session)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    # Step 3: Assign SI tags to view columns
    try:
        lf_client = session.client("lakeformation")
        assign_view_tags(lf_client, DATABASE_NAME, VIEW_NAME, COLUMN_TAG_MAP)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(3)

    print("\nDone. View created and SI tags assigned to view columns.")


if __name__ == "__main__":
    main()
