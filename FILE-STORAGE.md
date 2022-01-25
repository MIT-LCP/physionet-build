# File Storage Configurations

This project aims to support multiple file storage options which can be configured using the `STORAGE_TYPE` environment variable as shown in the settings file. Options are:

- LOCAL (files are stored on the same filesystem as the hosting server)
- GCP

## Local Filesystem

- Static files are stored in the `STATIC_ROOT` folder. Directly served by nginx.
- User-uploaded media files are stored in the `MEDIA_ROOT` folder. Authorization is done by Django views and then an `X-Accel-Redirect` to nginx if approved.
- When projects get published, if it is a public project, files get moved to a `published_projects` subdirectory within `STATIC_ROOT`. Otherwise they get moved into a `published_projects` subdirectory within `MEDIA_ROOT`.

## GCS File Storage

Ref: https://django-storages.readthedocs.io/en/latest/backends/gcloud.html

Ref: https://googleapis.dev/python/storage/latest/

Setup required to use GCS:

- Create an IAM user (service account), and attach the Storage Admin (roles/storage.admin) role.
- Create a JSON key for the account and save it as `physionet-django/physionet-django/PhysioNet-Data-credentials.json`
- Create a bucket for static files. Choose uniform access control. Add public access (https://cloud.google.com/storage/docs/access-control/making-data-public). Set the `GCP_STATIC_BUCKET_NAME` environment variable to match.

CORS configuration (needed for font-awesome):

```json
[
    {
        "origin": ["*"],
        "method": ["GET"],
        "responseHeader": [],
        "maxAgeSeconds": 3600
    }
]
```

- Create a bucket all user-uploaded media files. Choose uniform access control. Set the `GCP_STORAGE_BUCKET_NAME` environment variable to match. No public access.

- Each published project will have its own bucket. Note that this differs from local storage where public project files are written to the `published_projects` directory within the static root. One reason for the separation is to more easily set requester pays per bucket and view analytics. Set the `GCP_BUCKET_LOCATION` environment variable to the location where new buckets should be created.

CORS configuration to allow direct uploads:

```json
[
  {
    "origin": ["https://your-website.com"],
    "responseHeader": [
      "Content-Type",
      "Access-Control-Allow-Origin",
      "X-Upload-Content-Length",
      "x-goog-resumable"
    ],
    "method": ["PUT", "OPTIONS"],
    "maxAgeSeconds": 3600
  }
]
```

Direct files upload flow:
- Generate a signed url by sending an HTTP POST request to the `generate_signed_url` endpoint, it accepts `filename` and `size`.
- Send a PUT request to the signed url with the file as a payload, you have to provide `X-Upload-Content-Length` header and set it to the file size. The file needs to match the one provided when generating the signed url, otherwise the request will fail.
 
## Serving Files and URLs

Static files are all public, so just use the `{% static %}` tag in the django templates.

Media files are not inherently public. For media assets that require access control, create a url endpoint for each asset, and process the authorization in the view (or middleware). After validating:
- If using local FS, redirect to nginx.
- If using GCS, get the signed url from the backend and place it into the template.

eg. See `def profile_photo`.

With GCS uploads, it is possible to link directly to the GCS location in the template with: `<a src="{{ <model>.<fieldname>.url}}">`. Django automatically generates a signed URL for the GCS location. Only do this if the media asset should be publicly accessible.

Note about psycopg2-binary installation for M1 Mac which is required for `django-storages`: https://github.com/psycopg/psycopg2/issues/1286
