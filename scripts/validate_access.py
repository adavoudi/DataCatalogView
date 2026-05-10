"""Access control validation for SIRole and NonSIRole.

Validates that Lake Formation tag-based access control (TBAC) is working
correctly by querying the Data Catalog view as each role and verifying:
- SIRole can see all columns including SI=true tagged columns
- NonSIRole can see non-SI columns but is denied access to SI=true columns

Exit codes:
    0 - All validations passed
    1 - Role assumption failure
    4 - Validation failure (access control not working as expected)
    5 - Unexpected error
"""

import sys

import boto3

from config import (
    ATHENA_WORKGROUP,
    DATABASE_NAME,
    NONSI_ROLE_ARN,
    REGION,
    SI_ROLE_ARN,
    VIEW_NAME,
)
from helpers import (
    assume_role,
    get_query_results,
    run_athena_query,
    wait_for_query,
)


def validate_si_role_access(session: boto3.Session) -> bool:
    """Validate SIRole can query view and see SI-tagged columns.

    Executes SELECT * on the view and verifies that:
    - The query succeeds
    - The 'ssn' column (SI=true) is present in results
    - At least one row of data is returned with non-null ssn values

    Args:
        session: A boto3 Session with SIRole credentials.

    Returns:
        True if validation passes, False otherwise.
    """
    print("=" * 60)
    print("SIRole Validation: Querying view with SELECT *")
    print("=" * 60)

    query = f"SELECT * FROM {VIEW_NAME}"
    print(f"  Query: {query}")
    print(f"  Database: {DATABASE_NAME}")
    print(f"  Workgroup: {ATHENA_WORKGROUP}")
    print()

    try:
        query_id = run_athena_query(session, query, DATABASE_NAME, ATHENA_WORKGROUP)
        print(f"  Query execution ID: {query_id}")

        wait_for_query(session, query_id)
        print("  Query completed successfully.")

        results = get_query_results(session, query_id)
        print(f"  Rows returned: {len(results)}")
        print()

        # Verify at least 1 row returned
        if len(results) == 0:
            print("  FAIL: No rows returned from view query.")
            return False

        # Verify 'ssn' column (SI=true) is present in results
        first_row = results[0]
        column_names = list(first_row.keys())
        print(f"  Columns in result: {column_names}")

        if "ssn" not in column_names:
            print("  FAIL: 'ssn' column (SI=true) is NOT present in results.")
            print("  SIRole should be able to see SI-tagged columns.")
            return False

        # Verify ssn column has data
        ssn_values = [row.get("ssn") for row in results]
        non_null_ssn = [v for v in ssn_values if v is not None]

        if len(non_null_ssn) == 0:
            print("  FAIL: 'ssn' column is present but contains no data.")
            return False

        # Print results for manual verification
        print()
        print("  Query Results:")
        print("  " + "-" * 50)
        for row in results:
            print(f"    {row}")
        print("  " + "-" * 50)
        print()
        print("  PASS: SIRole can see all columns including SI=true (ssn).")
        return True

    except RuntimeError as e:
        print(f"  FAIL: Unexpected error during SIRole validation: {e}")
        return False


def validate_nonsi_role_access(session: boto3.Session) -> bool:
    """Validate NonSIRole cannot see SI-tagged columns.

    Performs two queries:
    1. SELECT id, name (non-SI columns) — expects success
    2. SELECT ssn (SI column) — expects access denial

    Args:
        session: A boto3 Session with NonSIRole credentials.

    Returns:
        True if validation passes (non-SI access works, SI access denied),
        False otherwise.
    """
    print("=" * 60)
    print("NonSIRole Validation: Testing access control")
    print("=" * 60)

    # --- Query 1: Non-SI columns (expect success) ---
    print()
    print("  Test 1: Query non-SI columns (id, name) — expect SUCCESS")
    print("  " + "-" * 50)

    query_nonsi = f"SELECT id, name FROM {VIEW_NAME}"
    print(f"  Query: {query_nonsi}")

    try:
        query_id = run_athena_query(
            session, query_nonsi, DATABASE_NAME, ATHENA_WORKGROUP
        )
        print(f"  Query execution ID: {query_id}")

        wait_for_query(session, query_id)
        print("  Query completed successfully.")

        results = get_query_results(session, query_id)
        print(f"  Rows returned: {len(results)}")

        if len(results) == 0:
            print("  FAIL: No rows returned for non-SI column query.")
            return False

        # Print results for manual verification
        print()
        print("  Query Results (non-SI columns):")
        print("  " + "-" * 50)
        for row in results:
            print(f"    {row}")
        print("  " + "-" * 50)
        print()
        print("  PASS: NonSIRole can query non-SI columns successfully.")

    except RuntimeError as e:
        print(f"  FAIL: Non-SI column query failed unexpectedly: {e}")
        return False

    # --- Query 2: SI column (expect access denial) ---
    print()
    print("  Test 2: Query SI column (ssn) — expect ACCESS DENIED")
    print("  " + "-" * 50)

    query_si = f"SELECT ssn FROM {VIEW_NAME}"
    print(f"  Query: {query_si}")

    try:
        query_id = run_athena_query(
            session, query_si, DATABASE_NAME, ATHENA_WORKGROUP
        )
        print(f"  Query execution ID: {query_id}")

        # Wait for query — if it fails with access denial, wait_for_query
        # will raise RuntimeError with the failure reason
        wait_for_query(session, query_id)

        # If we get here, the query succeeded — access control is NOT working
        print("  FAIL: Query on SI column succeeded — access control is NOT enforced.")
        print("  NonSIRole should NOT be able to query SI=true columns.")
        return False

    except RuntimeError as e:
        error_message = str(e)
        # Check if this is an expected access denial
        if _is_access_denied_error(error_message):
            print(f"  Access denied (expected): {error_message}")
            print()
            print("  PASS: NonSIRole is correctly denied access to SI columns.")
            return True
        else:
            # Unexpected error — not an access denial
            print(f"  FAIL: Query failed with unexpected error: {error_message}")
            print("  Expected an access denial error, but got a different failure.")
            return False


def _is_access_denied_error(error_message: str) -> bool:
    """Determine if an error message indicates an access denial.

    Checks for common access denial patterns in Athena/Lake Formation errors.

    Args:
        error_message: The error message string to check.

    Returns:
        True if the error appears to be an access denial.
    """
    access_denied_patterns = [
        "AccessDeniedException",
        "Access Denied",
        "access denied",
        "Insufficient permissions",
        "insufficient permissions",
        "not authorized",
        "Not authorized",
        "ACCESS_DENIED",
        "Insufficient Lake Formation permission",
    ]
    return any(pattern in error_message for pattern in access_denied_patterns)


def main() -> None:
    """Assume each role and validate access control.

    Assumes SIRole and NonSIRole in sequence, running validation checks
    for each. Prints results to stdout and exits with appropriate code.

    Exit codes:
        0 - All validations passed
        1 - Role assumption failure
        4 - Validation failure (access control not working as expected)
        5 - Unexpected error
    """
    print("AWS Lakehouse SI Tagging — Access Control Validation")
    print("=" * 60)
    print()

    # --- Validate SIRole ---
    print("Assuming SIRole...")
    try:
        si_session = assume_role(SI_ROLE_ARN, "SIRoleValidation", REGION)
        print(f"  Successfully assumed SIRole: {SI_ROLE_ARN}")
        print()
    except RuntimeError as e:
        print(f"  ERROR: Failed to assume SIRole: {e}")
        sys.exit(1)

    try:
        si_result = validate_si_role_access(si_session)
    except Exception as e:
        print(f"  UNEXPECTED ERROR during SIRole validation: {e}")
        sys.exit(5)

    print()

    # --- Validate NonSIRole ---
    print("Assuming NonSIRole...")
    try:
        nonsi_session = assume_role(NONSI_ROLE_ARN, "NonSIRoleValidation", REGION)
        print(f"  Successfully assumed NonSIRole: {NONSI_ROLE_ARN}")
        print()
    except RuntimeError as e:
        print(f"  ERROR: Failed to assume NonSIRole: {e}")
        sys.exit(1)

    try:
        nonsi_result = validate_nonsi_role_access(nonsi_session)
    except Exception as e:
        print(f"  UNEXPECTED ERROR during NonSIRole validation: {e}")
        sys.exit(5)

    # --- Summary ---
    print()
    print("=" * 60)
    print("Validation Summary")
    print("=" * 60)
    print(f"  SIRole validation:    {'PASS' if si_result else 'FAIL'}")
    print(f"  NonSIRole validation: {'PASS' if nonsi_result else 'FAIL'}")
    print()

    if si_result and nonsi_result:
        print("All validations PASSED. Access control is working as expected.")
        sys.exit(0)
    else:
        print("One or more validations FAILED. Access control is NOT working as expected.")
        sys.exit(4)


if __name__ == "__main__":
    main()
