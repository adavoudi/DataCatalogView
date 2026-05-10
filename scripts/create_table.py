"""Create an Iceberg table with sample data and assign SI LF-Tags.

This script assumes the AdminRole, drops any existing table, creates an
Iceberg table with sample data using CTAS (CREATE TABLE AS SELECT), then
assigns SI LF-Tags to each column and verifies the assignments.

Column tag assignments:
  - id   → SI=false
  - name → SI=false
  - ssn  → SI=true

Exit codes:
    0 - Success
    1 - Role assumption failure
    2 - Table creation failure
    3 - Tag assignment or verification failure
"""

import sys

import boto3
from botocore.exceptions import ClientError

from config import (
    ACCOUNT_ID,
    ADMIN_ROLE_ARN,
    ATHENA_WORKGROUP,
    DATA_LAKE_BUCKET,
    DATABASE_NAME,
    REGION,
    TABLE_NAME,
)
from helpers import assume_role, get_query_results, run_athena_query, wait_for_query

# Column-to-SI-value mapping
COLUMN_TAG_ASSIGNMENTS: dict[str, str] = {
    "id": "false",
    "name": "false",
    "ssn": "true",
}


def drop_table(session: boto3.Session) -> None:
    """Drop the table if it already exists.

    Args:
        session: A boto3 Session with AdminRole credentials.

    Raises:
        RuntimeError: If the DROP query fails.
    """
    query = f"DROP TABLE IF EXISTS `{DATABASE_NAME}`.`{TABLE_NAME}`"
    print(f"Dropping table {DATABASE_NAME}.{TABLE_NAME} if it exists...")
    print(f"[SQL] {query}")
    query_id = run_athena_query(session, query, DATABASE_NAME, ATHENA_WORKGROUP)
    wait_for_query(session, query_id)
    print("Drop complete.")


def create_table(session: boto3.Session) -> None:
    """Create an Iceberg table with schema definition.

    Creates the table structure without data using CREATE TABLE with explicit
    column definitions and Iceberg table properties.

    Args:
        session: A boto3 Session with AdminRole credentials.

    Raises:
        RuntimeError: If the CREATE TABLE query fails.
    """
    location = f"s3://{DATA_LAKE_BUCKET}/{DATABASE_NAME}/{TABLE_NAME}"
    query = (
        f"CREATE TABLE {DATABASE_NAME}.{TABLE_NAME} (\n"
        f"  id int,\n"
        f"  name string,\n"
        f"  ssn string\n"
        f")\n"
        f"LOCATION '{location}'\n"
        f"TBLPROPERTIES (\n"
        f"  'table_type'='iceberg',\n"
        f"  'compression_level'='3',\n"
        f"  'format'='PARQUET',\n"
        f"  'write_compression'='ZSTD'\n"
        f")"
    )

    print(f"Creating Iceberg table {DATABASE_NAME}.{TABLE_NAME}...")
    print(f"[SQL] {query}")
    query_id = run_athena_query(session, query, DATABASE_NAME, ATHENA_WORKGROUP)
    wait_for_query(session, query_id)
    print(f"Table {DATABASE_NAME}.{TABLE_NAME} created successfully.")


def insert_sample_data(session: boto3.Session) -> None:
    """Insert sample data into the Iceberg table.

    Args:
        session: A boto3 Session with AdminRole credentials.

    Raises:
        RuntimeError: If the INSERT query fails.
    """
    query = (
        f"INSERT INTO {DATABASE_NAME}.{TABLE_NAME}\n"
        f"SELECT * FROM (VALUES\n"
        f"  (1, 'Alice Johnson', '123-45-6789'),\n"
        f"  (2, 'Bob Smith', '987-65-4321'),\n"
        f"  (3, 'Charlie Brown', '555-12-3456')\n"
        f") AS t(id, name, ssn)"
    )

    print(f"Inserting sample data into {DATABASE_NAME}.{TABLE_NAME}...")
    print(f"[SQL] {query}")
    query_id = run_athena_query(session, query, DATABASE_NAME, ATHENA_WORKGROUP)
    wait_for_query(session, query_id)
    print(f"Sample data inserted into {DATABASE_NAME}.{TABLE_NAME} successfully.")


def assign_si_tag(
    lf_client, database: str, table: str, column: str, si_value: str
) -> dict:
    """Assign SI LF-Tag to a specific column. Returns API response.

    Args:
        lf_client: A boto3 Lake Formation client.
        database: The Glue database name.
        table: The Glue table name.
        column: The column name to tag.
        si_value: The SI tag value ("true" or "false").

    Returns:
        The API response dict from AddLFTagsToResource.

    Raises:
        ClientError: If the Lake Formation API call fails.
    """
    response = lf_client.add_lf_tags_to_resource(
        Resource={
            "TableWithColumns": {
                "DatabaseName": database,
                "Name": table,
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
    return response


def verify_tag_assignment(
    lf_client, database: str, table: str, column: str, expected_si: str
) -> bool:
    """Verify that a column has the expected SI tag value.

    Args:
        lf_client: A boto3 Lake Formation client.
        database: The Glue database name.
        table: The Glue table name.
        column: The column name to verify.
        expected_si: The expected SI tag value ("true" or "false").

    Returns:
        True if the column has the expected SI tag value, False otherwise.
    """
    response = lf_client.get_resource_lf_tags(
        Resource={
            "TableWithColumns": {
                "DatabaseName": database,
                "Name": table,
                "ColumnNames": [column],
            }
        },
    )

    # Check LFTagsOnColumns for the expected tag
    for column_tags in response.get("LFTagsOnColumns", []):
        if column in column_tags.get("Name", column_tags.get("ColumnNames", [])):
            pass
        for tag in column_tags.get("LFTags", []):
            if tag.get("TagKey") == "SI":
                tag_values = tag.get("TagValues", [])
                if expected_si in tag_values:
                    return True
    return False


def assign_and_verify_tags(session: boto3.Session) -> None:
    """Assign SI tags to all columns and verify the assignments.

    Args:
        session: A boto3 Session with AdminRole credentials.

    Raises:
        SystemExit: Exits with code 3 if any assignment or verification fails.
    """
    lf_client = session.client("lakeformation")
    failures: list[str] = []

    # Assign SI tags to each column
    print(f"\nAssigning SI tags to columns in {DATABASE_NAME}.{TABLE_NAME}:")
    for column, si_value in COLUMN_TAG_ASSIGNMENTS.items():
        print(f"  Assigning SI={si_value} to column '{column}'...", end=" ")
        try:
            response = assign_si_tag(
                lf_client, DATABASE_NAME, TABLE_NAME, column, si_value
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

    # Verify tag assignments
    print(f"\nVerifying SI tag assignments on {DATABASE_NAME}.{TABLE_NAME}:")
    for column, expected_si in COLUMN_TAG_ASSIGNMENTS.items():
        print(f"  Verifying column '{column}' has SI={expected_si}...", end=" ")
        try:
            if verify_tag_assignment(
                lf_client, DATABASE_NAME, TABLE_NAME, column, expected_si
            ):
                print("OK")
            else:
                error_msg = (
                    f"Column '{column}': expected SI={expected_si} but tag not found"
                )
                failures.append(error_msg)
                print("FAILED")
                print(f"    {error_msg}")
        except ClientError as e:
            error_msg = (
                f"Column '{column}' verification: "
                f"{e.response['Error']['Message']}"
            )
            failures.append(error_msg)
            print("FAILED")
            print(f"    {error_msg}")
        except Exception as e:
            error_msg = f"Column '{column}' verification: {e}"
            failures.append(error_msg)
            print("FAILED")
            print(f"    {error_msg}")

    # Report results
    if failures:
        print(f"\n{len(failures)} failure(s) occurred:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        sys.exit(3)

    print("\nAll SI tag assignments completed and verified successfully.")


def main() -> None:
    """Assume AdminRole, create Iceberg table, and assign SI tags."""
    # Step 1: Assume AdminRole
    try:
        print(f"Assuming AdminRole: {ADMIN_ROLE_ARN}")
        session = assume_role(ADMIN_ROLE_ARN, "CreateTableSession", REGION)
        print("Successfully assumed AdminRole.")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 2: Drop and recreate table
    try:
        drop_table(session)
        create_table(session)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    # Step 3: Assign and verify SI LF-Tags
    assign_and_verify_tags(session)

    # Step 4: Insert sample data
    try:
        insert_sample_data(session)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    # Step 5: Query table to verify data
    try:
        query = f"SELECT * FROM {DATABASE_NAME}.{TABLE_NAME}"
        print(f"\nVerifying data with query: {query}")
        query_id = run_athena_query(session, query, DATABASE_NAME, ATHENA_WORKGROUP)
        wait_for_query(session, query_id)
        results = get_query_results(session, query_id)
        print(f"Query returned {len(results)} row(s):")
        for row in results:
            print(f"  {row}")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    print("\nDone. Iceberg table created, SI tags assigned, and sample data verified.")


if __name__ == "__main__":
    main()
