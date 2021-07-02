# File Storage Configurations

This project aims to support multiple file storage options which can be configured using the `STORAGE_TYPE` environment variable as shown in the settings file. Options are:

- LOCAL (files are stored on the same filesystem as the hosting server)
- S3

## Local Filesystem

- Static files are stored in the `STATIC_ROOT` folder. Directly served by nginx.
- User-uploaded media files are stored in the `MEDIA_ROOT` folder. Authorization is done by Django views and then an `X-Accel-Redirect` to nginx if approved.
- When projects get published, if it is a public project, files get moved to a `published_projects` subdirectory within `STATIC_ROOT`. Otherwise they get moved into a `published_projects` subdirectory within `MEDIA_ROOT`.

## S3 File Storage

Ref: https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html

Setup requird to use S3:

- Create an IAM user with programmatic access, and attach the `AmazonS3FullAccess` policy.
- Set the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables from the user.
- Create a bucket for static files.

Bucket policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicRead",
      "Effect": "Allow",
      "Principal": "*",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::hdn-data-platform-static/*"
    }
  ]
}
```

CORS configuration (needed for font-awsome):

```json
[
  {
    "AllowedHeaders": [],
    "AllowedMethods": ["GET"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": []
  }
]
```

- Create a bucket all user-uploaded media files. Set the `AWS_STORAGE_BUCKET_NAME` environment variable to match. No public access.

- Each published project will have its own bucket. Note that this differs from local storage where public project files are written to the `published_projects` directory within the static root. One reason for the separation is to more easily set requester pays per bucket and view analytics. 

Note about psycopg2-binary installation for M1 Mac which is required for `django-storages`: https://github.com/psycopg/psycopg2/issues/1286

## Serving Files and URLs

Static files are all public, so just use the `{% static %}` tag in the django templates.

Media files are not inherently public. For media assets that require access control, create a url endpoint for each asset, and process the authorization in the view (or middleware). After validating:
- If using local FS, redirect to nginx.
- If using S3, get the signed url from the backend and place it into the template.

eg. See `def profile_photo`.

With S3 uploads, it is possible to link directly to the S3 location in the template with: `<a src="{{ <model>.<fieldname>.url}}">`. Django automatically generates a signed URL for the S3 location. Only do this if the media asset should be publically accessible.

Ref: https://testdriven.io/blog/storing-django-static-and-media-files-on-amazon-s3/
