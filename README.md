Total cost from start to finish: 80

Initial prompt:

```
I want to create an terraform project for an AWS project. The goal is to create a lakehouse with S3 + athena + lakeformation. I want to also have three roles: 



1. AdminRole: which has write access to the athena database and has full SI access.

2. SIRole: which has read access to SI columns

3. NonSIRole: which has read access to no SI columns



We first setup these with terraform. Then in python using boto3, I want to first create a table with sample data using the AdminRole and also assign SI tag to one of the columns. Then create a data Catalog view (https://docs.aws.amazon.com/lake-formation/latest/dg/working-with-views.html) using athena (via python again) (https://docs.aws.amazon.com/lake-formation/latest/dg/create-views.html) and then also assign proper SI tags to it. Then i want to test with the two other roles to see if they can query the view and if the SI taginmg on the view works as expected. 
```




**Note:** In order to be able to assign LF tags to a Data Catalog View, we have to do **one** of the followings:

1. Make the role/user the admin of the lakeformation (not recommended)
2. Give the role/user the `ALL` access to resources which have a specific LF tag. But for this to work, we should either assign that tag as default to the database, or first create the view and then via terraform, assign a tag to it. In this case, if you drop the view, you have to apply the terraform tag again!!
3. Give `ALL` access to all tables within a specific database. In this case, we can easily create DCV views and assign LF tags to them. This database should be limited only to that specific user/role to reduce security risks. 

---

## AWS Glue Data Catalog Multi-Dialect Views: Findings & Setup Guide

### What is a Multi-Dialect View?

An AWS Glue Data Catalog view (also called a Multi-Dialect View or MDV) is a single view object in the Glue Data Catalog that can hold SQL definitions in multiple engine-specific dialects (e.g., Athena/Trino and Redshift). This allows different query engines to query the same logical view using their own SQL syntax, while permissions are managed centrally through Lake Formation.

Key characteristics:
- A single view object in the Glue catalog with multiple SQL definitions (one per engine)
- Permissions are managed once via Lake Formation (tag-based or named resource)
- Users only need access to the view — not the underlying tables
- Supports `SECURITY DEFINER` mode where the view creator's permissions are used at query time

**References:**
- [Building AWS Glue Data Catalog views](https://docs.aws.amazon.com/lake-formation/latest/dg/working-with-views.html)
- [Creating Data Catalog views using DDL statements](https://docs.aws.amazon.com/lake-formation/latest/dg/create-views.html)
- [Use Data Catalog views in Athena](https://docs.aws.amazon.com/athena/latest/ug/views-glue.html)

---

### How to Make a Multi-Dialect View Work Across Athena and Redshift Spectrum

#### Step 1: Create the View via Athena (Registers the Trino/Athena Dialect)

Use `CREATE PROTECTED MULTI DIALECT VIEW` in Athena:

```sql
CREATE OR REPLACE PROTECTED MULTI DIALECT VIEW mydb.my_view SECURITY DEFINER AS
SELECT * FROM mydb.my_table
```

This registers **only the Athena (Trino) dialect**. At this point, querying the view from Redshift Spectrum will fail with:

```
AwsClientException: InvalidInputException from glue - Dialect [REDSHIFT 1.0] not present
```

**Reference:** [CREATE PROTECTED MULTI DIALECT VIEW](https://docs.aws.amazon.com/athena/latest/ug/create-view.html)

#### Step 2: Add the Redshift Dialect from Redshift

The Redshift dialect **cannot** be added from Athena. It must be added by running `ALTER EXTERNAL VIEW` from within Redshift itself:

```sql
ALTER EXTERNAL VIEW "external_schema"."my_view" FORCE AS
SELECT * FROM "external_schema"."my_table"
```

The `FORCE` keyword makes this idempotent — it updates the dialect if it already exists.

**Important:** This statement cannot run inside a transaction block. When using `redshift_connector` in Python, you must call `conn.rollback()` then set `conn.autocommit = True` before executing it:

```python
conn.rollback()
conn.autocommit = True
cursor.execute(alter_sql)
conn.autocommit = False
```

**References:**
- [ALTER EXTERNAL VIEW (Redshift)](https://docs.aws.amazon.com/redshift/latest/dg/r_ALTER_EXTERNAL_VIEW.html)
- [ALTER VIEW DIALECT (Athena)](https://docs.aws.amazon.com/athena/latest/ug/alter-view-dialect.html)

---

### IAM & Lake Formation Permissions Required

#### For the Redshift Spectrum Role (service role attached to the namespace):

1. **IAM Policy — `glue:UpdateTable`**: Required because `ALTER EXTERNAL VIEW` updates the view's metadata in the Glue catalog.

2. **Lake Formation — `ALTER` on the view/table**: Lake Formation enforces its own permission layer on top of IAM. The Spectrum role needs LF `ALTER` permission on the view. 
   
   **Important:** Tag-based access control (TBAC) grants for `ALTER` may not work reliably if the view hasn't been tagged yet at the time of the ALTER. Use a direct wildcard grant on the database instead:

   ```hcl
   resource "aws_lakeformation_permissions" "redshift_spectrum_alter_tables" {
     principal   = aws_iam_role.redshift_spectrum.arn
     permissions = ["ALTER"]

     table {
       wildcard      = true
       database_name = aws_glue_catalog_database.lakehouse_db.name
       catalog_id    = local.account_id
     }
   }
   ```

3. **Lake Formation — `SELECT` via TBAC**: For actually querying the view data, the Spectrum role needs `SELECT` (granted via tag-based access control).

4. **Lake Formation — `DESCRIBE` on the database**: So Redshift can resolve the external schema against the Glue catalog.

#### Security Consideration

Granting `ALTER` to the RedshiftSpectrumRole means any Redshift user who can run DDL could potentially modify views. Mitigations:

- **One-time setup**: Run `ALTER EXTERNAL VIEW` once during deployment, then remove the `ALTER` LF permission. The dialect persists in the Glue catalog.
- **Redshift RBAC**: Restrict which Redshift users can run `ALTER EXTERNAL VIEW` at the database level.
- **Scoped grants**: Instead of wildcard, grant `ALTER` only on the specific view (requires post-deployment scripting since the view is created outside Terraform).

---

### Connecting to Redshift Serverless with IAM Auth (Python)

When using `redshift_connector` with a Serverless workgroup that has `manage_admin_password = true`:

1. You **must** set `iam=True` — without it, the driver attempts password auth which fails (no static password exists).
2. You **must** provide `serverless_work_group` — the workgroup name (extracted from the endpoint hostname).
3. Your IAM identity needs `redshift-serverless:GetCredentials` on the workgroup.

```python
conn = redshift_connector.connect(
    iam=True,
    host=host,
    port=5439,
    database="dev",
    user="admin",
    access_key_id=creds.access_key,
    secret_access_key=creds.secret_key,
    session_token=creds.token,
    region="us-east-1",
    is_serverless=True,
    serverless_work_group="my-workgroup",
)
```

**Reference:** [Examples of using the Amazon Redshift Python connector](https://docs.aws.amazon.com/redshift/latest/mgmt/python-connect-examples.html)

---

### Redshift Serverless + Terraform: VPC Requirements

If you set `publicly_accessible = true` on the workgroup, the VPC **must** have:
- An Internet Gateway attached
- A route table with a `0.0.0.0/0` route through the IGW
- Route table associations on the subnets

Without these, the workgroup gets stuck in `CREATING` state indefinitely (45+ minutes) because AWS cannot provision the public endpoint.

**Reference:** [Creating a workgroup with Redshift Serverless](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-workgroup-namespace.html)

---

### Summary of the Full Flow

```
1. terraform apply          → Provisions infra (VPC, Redshift, Glue DB, IAM, LF permissions)
2. python create_table.py   → Creates Glue table with sample data, assigns SI tags
3. python create_view.py    → Creates PROTECTED MULTI DIALECT VIEW via Athena, assigns SI tags to view columns
4. python query_spectrum_view.py →
     a. Connects to Redshift Serverless (IAM auth)
     b. Creates external schema pointing to Glue DB
     c. Runs ALTER EXTERNAL VIEW to add Redshift dialect
     d. Queries the view via Spectrum
```
