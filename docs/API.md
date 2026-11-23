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

These endpoints create annotations on published project files. They accept only personal access tokens or OAuth tokens (`Authorization: Bearer ...`), with the scope listed for each endpoint.

| Endpoint | Scope | Creates |
|---|---|---|
| `POST /api/annotations/collection/create/` | `annotations:collections:write` | An annotation collection: `slug`, `name`, `description` |
| `POST /api/annotations/type/create/` | `annotations:types:write` | An annotation type: `slug`, `name`, `description`, `label_schema` (JSON Schema for labels), `allowed_location_type`, `version` |
| `POST /api/annotations/collections/{collection_slug}/` | `annotations:annotations:write` | An annotation in a collection: `annotation_type` (slug), `project` (slug), `file_path`, `labels`, `location` |

`location` is an object whose `location_type` is `timeseries_interval`, `image_bbox` or `text_span`, with the fields for that type. Successful requests return `201 Created` with the created object.

> TODO: add request and response examples for each annotation endpoint, and the fields of each location type.

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
