# PhysioNet API

PhysioNet provides a read-only REST API for metadata about published projects (datasets, software, challenges and models), and a token-based API for creating annotations.

- **Base URL:** `https://physionet.org/api/v1/` for project endpoints, `https://physionet.org/api/annotations/` for annotation endpoints.
- **Format:** JSON, unless stated otherwise.
- **Methods:** project endpoints accept `GET` only; annotation endpoints accept `POST` only.

> This documentation describes the API as it currently behaves. It is a first draft: please report anything that doesn't match.

## Contents

- [Authentication](#authentication)
- [Rate limits](#rate-limits)
- [Errors](#errors)
- [Project endpoints](#project-endpoints)
  - [List published projects](#list-published-projects)
  - [Search published projects](#search-published-projects)
  - [List the versions of a project](#list-the-versions-of-a-project)
  - [Get a project version](#get-a-project-version)
  - [Check access to a project version](#check-access-to-a-project-version)
  - [Download the SHA256SUMS.txt file](#download-the-sha256sumstxt-file)
- [Annotation endpoints](#annotation-endpoints)
  - [Create a collection](#create-a-collection)
  - [Create an annotation type](#create-an-annotation-type)
  - [Create an annotation](#create-an-annotation)
  - [Location types](#location-types)
  - [Annotation errors](#annotation-errors)
- [Legacy endpoints](#legacy-endpoints)
- [Other APIs](#other-apis)

## Authentication

Most project endpoints work **without authentication**. Authenticating raises your rate limit and, for the access endpoint, shows your own access status.

| Method | How | Accepted by |
|---|---|---|
| None (anonymous) | — | List, search, versions, detail, access status |
| HTTP Basic | `curl -u USERNAME https://physionet.org/api/v1/...` (prompts for your PhysioNet password) | All project endpoints |
| Session | Being logged in to physionet.org in the same browser | All project endpoints |
| Personal access token | `Authorization: Bearer pnpat_...` header. Create tokens at [Settings → Tokens](https://physionet.org/settings/tokens/). | `sha256sums` (with the `data:download` scope) and the annotation endpoints |
| OAuth 2.0 access token | `Authorization: Bearer ...` header, issued to a registered OAuth application | Search and versions (rate limit only), `sha256sums` (with `data:download`) and the annotation endpoints |

Notes:
- Always use HTTPS. The `sha256sums` endpoint rejects tokens sent over plain HTTP.
- The access status endpoint does **not** accept tokens, because its response reveals credentialing and training status. Use Basic or session authentication.

## Rate limits

| Client | Limit |
|---|---|
| Anonymous | 20 requests per hour, per IP address |
| Authenticated | 100 requests per hour, per user |

The limit is shared across the project endpoints, except `sha256sums`, which isn't rate limited. When it is exceeded, the API returns `429 Too Many Requests` with a `Retry-After` header (in seconds).

The list endpoint returns every published project in one response, so you rarely need to call it more than once.

## Errors

Errors use standard HTTP status codes with a JSON body:

| Status | When | Body |
|---|---|---|
| `400 Bad Request` | Invalid query parameter (e.g. an unknown `resource_type`) or invalid annotation data | `{"error": "..."}` or field errors |
| `401 Unauthorized` | Authentication is required or the credentials are invalid | `{"detail": "..."}` |
| `403 Forbidden` | Authenticated, but not allowed (e.g. no access to the project, or a token without the required scope) | `{"detail": "..."}` or `{"error": "..."}` |
| `404 Not Found` | Unknown project or version | `{"detail": "..."}` |
| `429 Too Many Requests` | Rate limit exceeded | `{"detail": "..."}` |

## Project endpoints

Project fields:

| Field | Type | Description |
|---|---|---|
| `public_project_uuid` | string (UUID) | Persistent identifier of the project version |
| `slug` | string | Project identifier used in URLs (e.g. `mimiciv`) |
| `version` | string | Version (e.g. `3.1`) |
| `title` | string | Title |
| `short_description` | string | One-line description |
| `abstract` | string (HTML) | Abstract, as **HTML** |
| `license` | object | `{"name": "..."}` |
| `dua` | object or null | Data use agreement, `{"name": "..."}` |
| `main_storage_size` | integer | Total size of the files, in bytes |
| `compressed_storage_size` | integer | Size of the ZIP file, in bytes |
| `resource_type` | string | `Database`, `Software`, `Challenge` or `Model` |
| `access_policy` | string | `Open`, `Restricted`, `Credentialed` or `Contributor Review` |
| `topics` | array of strings | Keywords |
| `source_url` | string (URL) | Project page on PhysioNet |

### List published projects

```
GET /api/v1/projects/published/
```

Returns **all** published project versions, ordered by internal ID, as a JSON array. The response is not paginated.

Each item has the [project fields](#project-endpoints) plus:

| Field | Type | Description |
|---|---|---|
| `core_doi` | string or null | DOI that resolves to the latest version |
| `version_doi` | string or null | DOI of this version |
| `is_latest_version` | boolean | Whether this is the latest version |
| `publish_date` | string (date) | Publication date, `YYYY-MM-DD` |

Example:

```
curl https://physionet.org/api/v1/projects/published/
```

```json
[
  {
    "public_project_uuid": "5df79f41-857f-4e97-95d3-6e2cf0f2fe3b",
    "slug": "slpdb",
    "version": "1.0.0",
    "core_doi": "10.13026/3p18-8q66",
    "version_doi": "10.13026/C23K5S",
    "is_latest_version": true,
    "short_description": "Recordings of multiple physiologic signals during sleep...",
    "publish_date": "1999-08-03",
    "title": "MIT-BIH Polysomnographic Database",
    "abstract": "<p>The MIT-BIH Polysomnographic Database is a collection of ...",
    "license": {"name": "Open Data Commons Attribution License v1.0"},
    "dua": null,
    "main_storage_size": 663056564,
    "compressed_storage_size": 663076626,
    "resource_type": "Database",
    "access_policy": "Open",
    "topics": ["sleep", "eeg", "ecg", "multiparameter", "respiration", "apnea"],
    "source_url": "https://physionet.org/content/slpdb/1.0.0/"
  }
]
```

### Search published projects

```
GET /api/v1/projects/search/
```

Searches published projects by keyword, ordered by relevance. Returns a JSON array with the same fields as the [list endpoint](#list-published-projects).

| Query parameter | Required | Description |
|---|---|---|
| `search_term` | No | Keywords to search for |
| `resource_type` | No | `database`, `software`, `challenge`, `model` or `all` (default). Case-insensitive. Repeat the parameter to combine types. |

Example:

```
curl "https://physionet.org/api/v1/projects/search/?search_term=sleep&resource_type=database"
```

An unknown `resource_type` returns `400` with `{"error": "Invalid resource_type"}`.

### List the versions of a project

```
GET /api/v1/projects/{slug}/versions/
```

Returns every published version of a project, as a JSON array. An unknown slug returns an empty array.

| Field | Type | Description |
|---|---|---|
| `slug` | string | Project identifier |
| `title` | string | Title |
| `version` | string | Version |
| `abstract` | string (HTML) | Abstract, as HTML |
| `citation` | string | Citation in Vancouver style |

Example:

```
curl https://physionet.org/api/v1/projects/slpdb/versions/
```

### Get a project version

```
GET /api/v1/projects/{slug}/versions/{version}/
```

Returns one project version, with the [project fields](#project-endpoints) plus:

| Field | Type | Description |
|---|---|---|
| `doi` | string or null | DOI of this version |
| `publish_datetime` | string (date-time) | Publication date and time |
| `project_home_page` | string | External home page, if any |
| `funding` | array | Funders: `funder_name`, `funder_identifier`, `funder_identifier_type`, `award_number`, `award_title`, `award_uri` |

Example:

```
curl https://physionet.org/api/v1/projects/slpdb/versions/1.0.0/
```

### Check access to a project version

```
GET /api/v1/projects/{slug}/versions/{version}/access/
```

Describes whether the requester can download the files of a project version directly from PhysioNet, and which steps are missing. Use `latest` as `{version}` for the latest version.

This endpoint is informational: it does not grant access, and each file request is authorized separately. Cloud access (e.g. AWS, Google Cloud) is not covered.

| Field | Type | Description |
|---|---|---|
| `slug`, `version` | string | Project and resolved version |
| `access_policy` | string | Access policy |
| `authenticated` | boolean | Whether the request was authenticated |
| `can_download` | boolean | Whether the requester can download the files now |
| `status` | string | `ready`, `sign_in_required`, `action_required` or `unavailable` |
| `reason` | string or null | When `unavailable`: `deprecated_files`, `embargoed`, `downloads_disabled`, `region_blocked` or `other` |
| `requirements` | array | Access steps, each with `id`, `code` (`sign_in`, `credentialing`, `training`, `dua` or `review`), `label`, `status` (`complete`, `pending`, `required` or `unknown`) and `url` |
| `project_url` | string (URL) | Project page |

For anonymous requests, steps that depend on the user are reported as `unknown`.

Example (anonymous):

```
curl https://physionet.org/api/v1/projects/mimiciv/versions/latest/access/
```

```json
{
  "slug": "mimiciv",
  "version": "3.1",
  "access_policy": "Credentialed",
  "authenticated": false,
  "can_download": false,
  "status": "sign_in_required",
  "reason": null,
  "requirements": [
    {"id": "sign_in", "code": "sign_in", "label": "Sign in to PhysioNet", "status": "required", "url": "https://physionet.org/login/"},
    {"id": "credentialing", "code": "credentialing", "label": "PhysioNet credentialing", "status": "unknown", "url": "https://physionet.org/settings/credentialing/"},
    {"id": "training:1", "code": "training", "label": "CITI Data or Specimens Only Research", "status": "unknown", "url": "https://physionet.org/settings/training/"},
    {"id": "dua", "code": "dua", "label": "Data use agreement", "status": "unknown", "url": "https://physionet.org/content/mimiciv/3.1/"}
  ],
  "project_url": "https://physionet.org/content/mimiciv/3.1/"
}
```

To see your own status, authenticate with Basic authentication:

```
curl -u USERNAME https://physionet.org/api/v1/projects/mimiciv/versions/latest/access/
```

### Download the SHA256SUMS.txt file

```
GET /api/v1/projects/published/{slug}/{version}/sha256sums/
```

Returns the project's `SHA256SUMS.txt` file (plain text, as an attachment), which lists the SHA-256 checksum of every file. Use it to verify downloaded files.

- Requires authentication, and access to the project's files.
- Tokens (personal or OAuth) must have the `data:download` scope.

Example:

```
curl -H "Authorization: Bearer pnpat_..." -o SHA256SUMS.txt \
  https://physionet.org/api/v1/projects/published/slpdb/1.0.0/sha256sums/
sha256sum -c SHA256SUMS.txt
```

Returns `403` if you don't have access to the project, and `404` if the project has no `SHA256SUMS.txt` file.

## Annotation endpoints

These endpoints create annotations on published project files. An annotation belongs to a **collection**, has a **type** that defines its labels and the kind of location it uses, and points to a **location** within a project file.

They accept only personal access tokens or OAuth tokens (`Authorization: Bearer ...`), with the scope listed for each endpoint, and expect a JSON request body (`Content-Type: application/json`). Successful requests return `201 Created` with the created object.

| Endpoint | Scope |
|---|---|
| `POST /api/annotations/collection/create/` | `annotations:collections:write` |
| `POST /api/annotations/type/create/` | `annotations:types:write` |
| `POST /api/annotations/collections/{collection_slug}/` | `annotations:annotations:write` |

### Create a collection

```
POST /api/annotations/collection/create/
```

| Field | Required | Description |
|---|---|---|
| `slug` | Yes, in practice | Unique identifier, used in the URL to add annotations to the collection |
| `name` | Yes | Name |
| `description` | No | Description |

Example:

```
curl -X POST https://physionet.org/api/annotations/collection/create/ \
  -H "Authorization: Bearer pnpat_..." \
  -H "Content-Type: application/json" \
  -d '{"slug": "example-ecg-beats", "name": "Example ECG beat annotations", "description": "Beat labels for an example ECG record."}'
```

```json
{
  "id": "eb5423b6-987a-4b2d-b9d6-196855d1b639",
  "slug": "example-ecg-beats",
  "name": "Example ECG beat annotations",
  "description": "Beat labels for an example ECG record.",
  "created_by": 1,
  "created_datetime": "2026-11-25T13:53:41.130996-05:00",
  "updated_datetime": "2026-11-25T13:53:41.131037-05:00"
}
```

`created_by` is the ID of the user who owns the token.

### Create an annotation type

```
POST /api/annotations/type/create/
```

| Field | Required | Description |
|---|---|---|
| `slug` | Yes | Unique identifier, used to refer to the type when creating annotations |
| `name` | Yes | Name |
| `description` | No | Description |
| `label_schema` | Yes | [JSON Schema](https://json-schema.org/) that the `labels` of each annotation must match |
| `allowed_location_type` | Yes | `timeseries_interval`, `image_bbox` or `text_span` |
| `version` | No | Version of the type (default `1.0.0`) |

Example:

```
curl -X POST https://physionet.org/api/annotations/type/create/ \
  -H "Authorization: Bearer pnpat_..." \
  -H "Content-Type: application/json" \
  -d '{
        "slug": "example-beat-label",
        "name": "Beat label",
        "description": "Beat type for an ECG interval.",
        "label_schema": {
          "type": "object",
          "properties": {"beat": {"type": "string", "enum": ["N", "V", "A"]}},
          "required": ["beat"]
        },
        "allowed_location_type": "timeseries_interval",
        "version": "1.0.0"
      }'
```

```json
{
  "id": "1041221f-4017-42ed-b290-b8c6a66c6c49",
  "slug": "example-beat-label",
  "name": "Beat label",
  "description": "Beat type for an ECG interval.",
  "label_schema": {
    "type": "object",
    "properties": {"beat": {"type": "string", "enum": ["N", "V", "A"]}},
    "required": ["beat"]
  },
  "allowed_location_type": "timeseries_interval",
  "version": "1.0.0",
  "created_datetime": "2026-11-25T13:53:41.441700-05:00"
}
```

### Create an annotation

```
POST /api/annotations/collections/{collection_slug}/
```

| Field | Required | Description |
|---|---|---|
| `annotation_type` | Yes | Slug of the annotation type |
| `project` | Yes | Slug of the published project |
| `file_path` | Yes | Path of the annotated file within the project |
| `labels` | Yes | Labels, matching the type's `label_schema` |
| `location` | Yes | Where the annotation is in the file (see [Location types](#location-types)). Its `location_type` must match the type's `allowed_location_type`. |

Annotations can currently be created only for projects that have a single published version.

Example:

```
curl -X POST https://physionet.org/api/annotations/collections/example-ecg-beats/ \
  -H "Authorization: Bearer pnpat_..." \
  -H "Content-Type: application/json" \
  -d '{
        "annotation_type": "example-beat-label",
        "project": "adfecgdb",
        "file_path": "r01.edf",
        "labels": {"beat": "N"},
        "location": {"location_type": "timeseries_interval", "channel": "Direct_1", "start": 1000, "end": 1250}
      }'
```

```json
{
  "id": "dddad541-162a-4219-b232-b2c6f4d89973",
  "collection": "example-ecg-beats",
  "annotation_type": "example-beat-label",
  "project": "adfecgdb",
  "file_path": "r01.edf",
  "labels": {"beat": "N"},
  "created_by": 1,
  "created_datetime": "2026-11-25T13:53:41.728126-05:00",
  "updated_datetime": "2026-11-25T13:53:41.728135-05:00",
  "location": {
    "id": "05e98f2f-4c34-4fcd-b725-baeecc263366",
    "location_type": "timeseries_interval",
    "coord_system": "samples",
    "created_datetime": "2026-11-25T13:53:41.727055-05:00",
    "channel": "Direct_1",
    "start": 1000,
    "end": 1250,
    "created_by": 1
  }
}
```

### Location types

Every location has a `location_type` and an optional `coord_system`, which describes the units of its coordinates. If `coord_system` is omitted, the default for the type is used.

| `location_type` | Fields | Default `coord_system` |
|---|---|---|
| `timeseries_interval` | `start`, `end` (integers); `channel` (optional) | `samples` |
| `image_bbox` | `x`, `y`, `width`, `height` (integers): top-left corner and size | `pixels` |
| `text_span` | `begin`, `end` (integers); `encoding` (default `utf-8`) | `char_offset` |

### Annotation errors

| Status | When | Example body |
|---|---|---|
| `400 Bad Request` | `labels` don't match the type's `label_schema` | `{"non_field_errors": ["'X' is not one of ['N', 'V', 'A']"]}` |
| `400 Bad Request` | `location_type` doesn't match the type's `allowed_location_type` | `{"non_field_errors": ["Location type must be 'timeseries_interval' ..."]}` |
| `400 Bad Request` | The annotation type, collection or project doesn't exist | `{"annotation_type": ["Object with slug=no-such-type does not exist."]}` |
| `401 Unauthorized` | No token | `{"detail": "Authentication credentials were not provided."}` |
| `401 Unauthorized` | Invalid or expired token | `{"detail": "Invalid or expired token."}` |
| `403 Forbidden` | The token doesn't have the required scope | `{"detail": "You do not have permission to perform this action."}` |

## Legacy endpoints

These older paths still work and return the same responses. New integrations should use the paths above.

| Legacy path | Same as |
|---|---|
| `/api/v1/project/published/` | `/api/v1/projects/published/` |
| `/api/v1/project/published/search/` | `/api/v1/projects/search/` |
| `/api/v1/project/published/{slug}/` | `/api/v1/projects/{slug}/versions/` |
| `/api/v1/project/published/{slug}/{version}/` | `/api/v1/projects/{slug}/versions/{version}/` |

## Other APIs

PhysioNet is also an OAuth 2.0 and OpenID Connect provider for registered partner applications (`/oauth/` and `/.well-known/openid-configuration`). These endpoints are not covered here.
