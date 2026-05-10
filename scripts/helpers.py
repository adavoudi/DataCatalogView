"""Shared utility functions for AWS Lakehouse SI Tagging scripts.

Provides helper functions for assuming IAM roles, executing Athena queries,
waiting for query completion, and retrieving query results.
"""

import time

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config


def assume_role(role_arn: str, session_name: str, region: str = None) -> boto3.Session:
    """Assume an IAM role and return a boto3 session with temporary credentials.

    Uses STS AssumeRole to obtain temporary credentials for the specified role,
    then creates and returns a new boto3 Session configured with those credentials.

    Args:
        role_arn: The ARN of the IAM role to assume.
        session_name: A name for the role session (used for auditing).

    Returns:
        A boto3.Session configured with the assumed role's temporary credentials.

    Raises:
        RuntimeError: If the role assumption fails, with a descriptive message
            including the role ARN and failure reason.
    """
    try:
        config = Config(region_name=region)
        sts_client = boto3.client("sts", config=config)
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
        )
        credentials = response["Credentials"]
        session = boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=region,
        )
        return session
    except ClientError as e:
        raise RuntimeError(
            f"Failed to assume role {role_arn}: {e.response['Error']['Message']}"
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"Failed to assume role {role_arn}: {e}"
        ) from e


def run_athena_query(
    session: boto3.Session, query: str, database: str, workgroup: str
) -> str:
    """Execute an Athena query and return the query execution ID.

    Starts an Athena query execution using the provided session credentials.

    Args:
        session: A boto3 Session (typically from assume_role).
        query: The SQL query string to execute.
        database: The Glue database name to query against.
        workgroup: The Athena workgroup to use for execution.

    Returns:
        The query execution ID string.

    Raises:
        RuntimeError: If the query submission fails, with a descriptive message.
    """
    try:
        athena_client = session.client("athena")
        response = athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": database},
            WorkGroup=workgroup,
        )
        return response["QueryExecutionId"]
    except ClientError as e:
        raise RuntimeError(
            f"Failed to start Athena query: {e.response['Error']['Message']}"
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"Failed to start Athena query: {e}"
        ) from e


def wait_for_query(
    session: boto3.Session, query_execution_id: str, timeout: int = 60
) -> dict:
    """Wait for an Athena query to complete and return the execution status.

    Polls the query execution status until it reaches a terminal state
    (SUCCEEDED, FAILED, or CANCELLED) or the timeout is exceeded.

    Args:
        session: A boto3 Session (typically from assume_role).
        query_execution_id: The ID of the query execution to monitor.
        timeout: Maximum seconds to wait for completion (default: 60).

    Returns:
        The query execution status dict from the Athena API response,
        containing fields like State, StateChangeReason, etc.

    Raises:
        RuntimeError: If the query times out, fails, or is cancelled.
    """
    athena_client = session.client("athena")
    start_time = time.time()

    while True:
        response = athena_client.get_query_execution(
            QueryExecutionId=query_execution_id
        )
        status = response["QueryExecution"]["Status"]
        state = status["State"]

        if state == "SUCCEEDED":
            return status

        if state == "FAILED":
            reason = status.get("StateChangeReason", "Unknown reason")
            raise RuntimeError(
                f"Athena query {query_execution_id} failed: {reason}"
            )

        if state == "CANCELLED":
            raise RuntimeError(
                f"Athena query {query_execution_id} was cancelled"
            )

        elapsed = time.time() - start_time
        if elapsed >= timeout:
            raise RuntimeError(
                f"Athena query {query_execution_id} timed out after {timeout} seconds"
            )

        time.sleep(2)


def get_query_results(
    session: boto3.Session, query_execution_id: str
) -> list[dict]:
    """Retrieve query results as a list of row dictionaries.

    Fetches the results of a completed Athena query and returns them as a list
    of dictionaries, where each dictionary maps column names to their values.

    Args:
        session: A boto3 Session (typically from assume_role).
        query_execution_id: The ID of the completed query execution.

    Returns:
        A list of dictionaries, one per result row. Each dictionary maps
        column names (strings) to their values (strings or None).
    """
    athena_client = session.client("athena")
    results = []
    next_token = None

    while True:
        kwargs = {"QueryExecutionId": query_execution_id}
        if next_token:
            kwargs["NextToken"] = next_token

        response = athena_client.get_query_results(**kwargs)
        result_set = response["ResultSet"]

        # Extract column names from metadata
        column_info = result_set["ResultSetMetadata"]["ColumnInfo"]
        column_names = [col["Name"] for col in column_info]

        # Process rows (first row in first page is the header row)
        rows = result_set["Rows"]
        start_index = 1 if not next_token else 0

        for row in rows[start_index:]:
            row_dict = {}
            for i, datum in enumerate(row["Data"]):
                value = datum.get("VarCharValue")
                row_dict[column_names[i]] = value
            results.append(row_dict)

        next_token = response.get("NextToken")
        if not next_token:
            break

    return results
