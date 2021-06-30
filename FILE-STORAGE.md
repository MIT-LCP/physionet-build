# File Storage Configurations

This project aims to support multiple file storage options which can be configured using the `STORAGE_TYPE` environment variable as shown in the settings file. Options are:

- LOCAL (files are stored on the same filesystem as the hosting server)
- S3

## S3 File Storage

Ref: https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html

Setup requird to use S3:

- Create an IAM user with programmatic access, and attach the `AmazonS3FullAccess` policy.
- Set the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables from the user.
- Create a bucket for non-published project files. Set the `AWS_STORAGE_BUCKET_NAME` environment variable to match.
- Each published project will have its own bucket. Note that this differs from local storage where public project files are written to the `published_projects` directory within the static root. One reason for the separation is to more easily set requester pays per bucket.

Note about psycopg2-binary installation for M1 Mac which is required for `django-storages`: https://github.com/psycopg/psycopg2/issues/1286
