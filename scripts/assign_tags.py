"""Assign SI LF-Tags to table columns using Lake Formation.

This script assumes the AdminRole, assigns SI=true or SI=false LF-Tags to
each column in the sample table, and verifies the assignments.

Column assignments:
  - id   → SI=false
  - name → SI=false
  - ssn  → SI=true

Exit codes:
  0 — Success
  1 — Role assumption failure
  3 — Tag assignment or verification failure
"""

import sys

from botocore.exceptions import ClientError

from config import ACCOUNT_ID, ADMIN_ROLE_ARN, DATABASE_NAME, REGION, TABLE_NAME
from helpers import assume_role

# Column-to-SI-value mapping
COLUMN_TAG_ASSIGNMENTS: dict[str, str] = {
    "id": "false",
    "name": "false",
    "ssn": "true",
}


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


def main() -> None:
    """Assume AdminRole, assign SI tags to all columns, verify assignments."""
    # Assume AdminRole
    print(f"Assuming AdminRole: {ADMIN_ROLE_ARN}")
    try:
        session = assume_role(ADMIN_ROLE_ARN, "AssignTagsSession", REGION)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

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


if __name__ == "__main__":
    main()
