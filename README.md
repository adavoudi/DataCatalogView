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

