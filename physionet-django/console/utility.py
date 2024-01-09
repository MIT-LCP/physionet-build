from os import walk, chdir, listdir, path
from requests.auth import HTTPBasicAuth
from requests import post, put, get
import json

import google.auth
import google.auth.impersonated_credentials
from google.api_core.exceptions import BadRequest
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from django.utils import timezone
from google.cloud import storage
from django.contrib.sites.models import Site
from django.conf import settings
from django.urls import reverse
from project.validators import validate_doi

import logging

LOGGER = logging.getLogger(__name__)
ROLES = ['roles/storage.legacyBucketReader',
         'roles/storage.legacyObjectReader',
         'roles/storage.objectViewer']


class DOIExistsError(Exception):
    pass


class DOICreationError(Exception):
    pass

# Manage GCP buckets

def check_bucket_exists(project, version):
    """
    Check if a bucket exists.
    """
    storage_client = storage.Client()
    bucket_name, email = bucket_info(project, version)
    if storage_client.lookup_bucket(bucket_name):
        return True
    return False

def create_bucket(project, version, title, protected=True):
    """
    Create a bucket with either public or private permissions.

    There are two different types of buckets:
     - Public which are open to the world.
     - Private which access is handled by an organizational email.
    """
    storage_client = storage.Client()
    bucket_name, email = bucket_info(project, version)

    bucket = storage_client.bucket(bucket_name)
    # Only bucket-level permissions are enforced; there are no per-file ACLs.
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True
    # Clients accessing this bucket will be billed for download costs.
    bucket.requester_pays = True
    storage_client.create_bucket(bucket)

    LOGGER.info("Created bucket {0} for project {1}".format(
        bucket_name.lower(), project))
    if protected:
        remove_bucket_permissions(bucket)
        group = create_access_group(bucket, project, version, title)
        LOGGER.info("Removed permissions from bucket {0} and created {1} "
                    "for read access".format(bucket_name.lower(), group))
    else:
        make_bucket_public(bucket)
        LOGGER.info("Made bucket {0} public".format(bucket_name.lower()))


def bucket_info(project, version):
    """
    Generate the bucket name or the email for managing access to the bucket.

    Returns the bucketname and the email if the project is not public.
    """
    name = '{0}{1}-{2}'.format(settings.GCP_BUCKET_PREFIX, project, version)
    email = '{0}@{1}'.format(name, settings.GCP_DOMAIN)
    bucket = '{0}.{1}'.format(name, settings.GCP_DOMAIN)

    return bucket, email


def make_bucket_public(bucket):
    """
    Make a bucket public to all users.
    """
    policy = bucket.get_iam_policy()
    for role in ROLES:
        policy[role].add('allUsers')
    bucket.set_iam_policy(policy)
    LOGGER.info("Made bucket {} public".format(bucket.name))


def remove_bucket_permissions(bucket):
    """
    Remove all permissions from a bucket for everyone except the owner.
    """
    policy = bucket.get_iam_policy()
    to_remove = []

    for role in policy:
        if role != 'roles/storage.legacyBucketOwner':
            for member in policy[role]:
                to_remove.append([role, member])

    for item in to_remove:
        policy[item[0]].discard(item[1])

    if to_remove:
        bucket.set_iam_policy(policy)
        LOGGER.info("Removed all read permissions from "
                    "bucket {}".format(bucket.name))


def create_access_group(bucket, project, version, title):
    """
    Create an access group with appropriate permissions, if the group does not
    already exist.

    Returns:
        bool: False if there was an error or change to the API. True otherwise.
    """
    bucket_name, email = bucket_info(project, version)
    service = create_directory_service(settings.GCP_DELEGATION_EMAIL)

    # Get all the members of the Google group
    try:
        outcome = service.groups().list(domain=settings.GCP_DOMAIN).execute()
        if not any(group['email'] in email for group in outcome['groups']):
            creation = service.groups().insert(body={
                'email': email,
                'name': '{0} v{1}'.format(title, version),
                'description': "Access group for the project {0} version "
                               "{1}.".format(title, version)}).execute()
            if creation['kind'] != 'admin#directory#group':
                LOGGER.info("Error {0} creating the "
                            "group {1}.".format(creation, email))
                return False
            LOGGER.info("Access group {0} was created.".format(email))
            if update_access_group(email):
                LOGGER.info("Access group {0} was updated.".format(email))
        else:
            LOGGER.info("Access group {0} already exists.".format(email))
    except HttpError as e:
        if json.loads(e.content)['error']['message'] != 'Member already exists.':
            LOGGER.info("Error {0} creating the access group {1} for "
                        "{1}.".format(e.content, email, project))
            raise e
        else:
            LOGGER.info("Access group {0} already exists.".format(email))

    return email


def update_access_group(email):
    """
    Set permissions for an access group.

    Returns:
        bool: False if there was an error or change to the API. True otherwise.
    """
    service = create_directory_service(settings.GCP_DELEGATION_EMAIL,
                                       group=True)
    update = service.groups().update(groupUniqueId=email, body={
        'allowExternalMembers': 'true',
        'whoCanPostMessage': 'ALL_OWNERS_CAN_POST',
        'whoCanModerateMembers': 'OWNERS_AND_MANAGERS',
        'whoCanJoin': 'INVITED_CAN_JOIN'}).execute()

    if update['kind'] != 'groupsSettings#groups':
        LOGGER.info("Error {0} setting the permissions for group "
                    "{1}".format(update, email))
        return False

    return True


def add_email_bucket_access(project, email, group=False):
    """
    Grant access to a bucket for the specified email address.

    Returns:
        bool: True is access is successfully granted. False otherwise.
    """
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(project.gcp.bucket_name)
    policy = bucket.get_iam_policy()

    if group:
        for role in ROLES:
            policy[role].add('group:'+email)
    else:
        for role in ROLES:
            policy[role].add('user:'+email)

    try:
        bucket.set_iam_policy(policy)
        LOGGER.info("Added email {0} to the project {1} access list".format(
            email, project))
        return True
    except BadRequest:
        LOGGER.info("Error in the request. The email {} was "
                    "ignored.".format(email))
        return False


def upload_files(project):
    """
    Upload files to a bucket. Gets a list of all the files under the project
    root directory, then sends each file individually. Check storage size to
    confirm that the zip file was created.
    """
    file_root = project.file_root()
    subfolders_fullpath = [x[0] for x in walk(file_root)]
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(project.gcp.bucket_name)

    for indx, location in enumerate(subfolders_fullpath):
        chdir(location)
        files = [f for f in listdir('.') if path.isfile(f)]
        for file in files:
            temp_dir = location.replace(file_root, '')
            if temp_dir != '':
                blob = bucket.blob(path.join(temp_dir, file)[1:])
                blob.upload_from_filename(file)
            else:
                blob = bucket.blob(file)
                blob.upload_from_filename(file)

    if project.compressed_storage_size:
        zip_name = project.zip_name()
        chdir(project.project_file_root())
        blob = bucket.blob(zip_name)
        blob.upload_from_filename(zip_name)


def create_directory_service(user_email, group=False):
    """
    Create an Admin SDK Directory Service object authorized with the service
    accounts that act on behalf of the given user.

    Args:
        user_email: The user's email address. Needs permission to access the
                    Admin API.
    Returns:
        Admin SDK Directory Service object.
    """
    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
    credentials, _  = google.auth.default(scopes=[
        'https://www.googleapis.com/auth/admin.directory.group',
        'https://www.googleapis.com/auth/apps.groups.settings',
    ])

    # The email for delegating credentials to the service account is required.
    credentials = credentials.with_claims({'sub': user_email})

    if group:
        return build('groupssettings', 'v1', credentials=credentials)
    return build('admin', 'directory_v1', credentials=credentials)


def register_doi(payload, project):
    """
    Create a DOI with basic project information via a POST request. Saves
    the DOI to the project.doi field.

    Args:
        payload (dict): The metadata to be sent to the DataCite API.
        project (obj): The ActiveProject, PublishedProject, or CoreProject
            that is associated with the payload.

    Example of the API return response.
    {
       'data':{
          'id':'10.7966/v2jx-h492',
          'type':'dois',
          'attributes':{
             'doi':'10.7966/v2jx-h492',
             'prefix':'10.7966',
             'suffix':'v2jx-h492',
             'identifiers':None,
             'creators':[ ],
             'titles':[ { 'title':'Example title' } ],
             'publisher':'PhysioNet-dev',
             'container':{ },
             'publicationYear':2020,
             'subjects':None,
             'contributors':[ ],
             'dates':None,
             'language':None,
             'types':{ 'resourceTypeGeneral':'Dataset' },
             'relatedIdentifiers':None,
             'sizes':None,
             'formats':None,
             'version':None,
             'rightsList':[ ],
             'descriptions':None,
             'geoLocations':None,
             'fundingReferences':None,
             'xml':'',
             'url':None,
             'contentUrl':None,
             'metadataVersion':0,
             'schemaVersion':None,
             'source':None,
             'isActive':False,
             'state':'draft',
             'reason':None,
             'landingPage':None,
             'viewCount':0,
             'downloadCount':0,
             'referenceCount':0,
             'citationCount':0,
             'partCount':0,
             'partOfCount':0,
             'versionCount':0,
             'versionOfCount':0,
             'viewsOverTime':[ ],
             'downloadsOverTime':[ ],
             'created':'2020-02-09T15:24:49.000Z',
             'registered':None,
             'published':'2020',
             'updated':'2020-02-09T15:24:49.000Z'
          },
          'relationships':{
             'client':{
                'data':{
                   'id':'XYZ.XYZ',
                   'type':'clients'
                }
             },
             'media':{
                'data':{
                   'id':'10.7966/v2jx-h492',
                   'type':'media'
                }
             },
             'references':{ 'data':[ ] },
             'citations':{ 'data':[ ] },
             'parts':{ 'data':[ ] },
             'versions':{ 'data':[ ] }
          }
       },
       'included':[
          {
             'id':'XYZ.XYZ',
             'type':'clients',
             'attributes':{
                'name':'XYZ',
                'symbol':'XYZ.XYZ',
                'year':2019,
                'contactEmail':'XYZ@XYZ.XYZ',
                'alternateName':None,
                'description':None,
                'language':None,
                'clientType':'repository',
                'domains':'*',
                're3data':None,
                'opendoar':None,
                'issn':{ },
                'url':'https://www.physionet.org/',
                'created':'2019-02-25T18:25:27.000Z',
                'updated':'2020-01-23T20:10:43.000Z',
                'isActive':True,
                'hasPassword':True
             },
             'relationships':{
                'provider':{
                   'data':{
                      'id':'XYZ',
                      'type':'providers'
                   }
                },
                'prefixes':{
                   'data':[
                      {
                         'id':'10.7966',
                         'type':'prefixes'
                      }
                   ]
                }
             }
          }
       ]
    }
    """
    headers = {'Content-Type': 'application/vnd.api+json'}
    request_url = settings.DATACITE_API_URL

    # Check whether the project already has a DOI assigned.
    # type(project) returns CoreProject, ActiveProject, or PublishedProject
    queryset = type(project).objects.filter(id=project.id, doi=None)

    # Hold DOI field to prevent multiple calls from registering multiple DOIs.
    if queryset.update(doi='PENDING') != 1:
        raise DOIExistsError('Project already has a DOI')
    doi = None

    try:
        response = post(request_url, data=json.dumps(payload), headers=headers,
                        auth=HTTPBasicAuth(settings.DATACITE_USER,
                        settings.DATACITE_PASS))

        if response.status_code < 200 or response.status_code >= 300:
            # Remove the pending status
            raise DOICreationError("""There was an unknown error creating the
                DOI. Here is the response text: {}""".format(response.text))

        content = json.loads(response.text)
        doi = content['data']['attributes']['doi']
        validate_doi(doi)

        event = payload['data']['attributes']['event']
        title = payload['data']['attributes']['titles'][0]['title']
        LOGGER.info("DOI ({0}) for project '{1}' created: {2}.".format(event,
                                                                       title,
                                                                       doi))
    finally:
        # Update the DOI field for the project
        queryset = type(project).objects.filter(id=project.id, doi='PENDING')
        queryset.update(doi=doi)


def update_doi(doi, payload):
    """
    Update metadata for a registered DOI via a PUT request.

    Args:
        doi (str): The doi to be updated.
        payload (dict): The metadata to be sent to the DataCite API.
    """
    headers = {'Content-Type': 'application/vnd.api+json'}
    request_url = '{0}/{1}'.format(settings.DATACITE_API_URL, doi)

    response = put(request_url, data=json.dumps(payload), headers=headers,
                   auth=HTTPBasicAuth(settings.DATACITE_USER,
                   settings.DATACITE_PASS))

    if response.status_code < 200 or response.status_code >= 300:
        raise Exception("""There was an unknown error updating the DOI. Here
            is the response text: {0}""".format(response.text))

    event = payload['data']['attributes']['event']
    title = payload['data']['attributes']['titles'][0]['title']

    LOGGER.info("DOI ({0}) for project '{1}' updated: {2}.".format(event,
                                                                   title, doi))


def generate_doi_payload(project, core_project=False, event="draft"):
    """
    Generate a payload for registering or updating a DOI.

    Args:
        project (obj): Project object.
        core_project (bool): If the metadata relates to the core project
            then core_project=True, else core_project=False.
        event (str): Either "draft" or "publish".

    Returns:
        payload (dict): The metadata to be sent to the DataCite API.
    """
    current_site = Site.objects.get_current()

    if event == "publish" and core_project:
        project_url = "https://{0}{1}".format(current_site, reverse(
            'published_project_latest', args=(project.slug,)))
    elif event == "publish":
        project_url = "https://{0}{1}".format(current_site, reverse(
            'published_project', args=(project.slug, project.version)))
    else:
        project_url = ""

    if core_project:
        version = "latest"
    else:
        version = project.version

    authors = []
    if event == "publish":
        author_list = project.author_list().order_by('display_order')
        for author in author_list:
            author_metadata = {"givenName": author.first_names,
                               "familyName": author.last_name,
                               "name": author.get_full_name(reverse=True)}
            author_metadata["affiliation"] = [{"name": a.name} for a in author.affiliations.all()]
            if author.user.has_orcid():
                author_metadata["nameIdentifiers"] = [{
                    "nameIdentifier": f'https://orcid.org/{author.user.get_orcid_id()}',
                    "nameIdentifierScheme": "ORCID",
                    "schemeUri": "https://orcid.org/"
                }]
            authors.append(author_metadata)

    # link to parent or child projects
    if event == "publish" and core_project:
        # add children if core project
        versions = project.core_project.get_published_versions()
        relation = []
        for v in versions:
            relation.append({"relationType": "HasVersion",
                             "relatedIdentifier": v.doi,
                             "relatedIdentifierType": "DOI"})
    elif event == "publish":
        # add parent if not core project
        relation = [{
          "relationType": "IsVersionOf",
          "relatedIdentifier": project.core_project.doi,
          "relatedIdentifierType": "DOI"
        }]
    else:
        relation = []

    # projects from which this project is derived
    for parent_project in project.parent_projects.all():
        if parent_project.doi:
            relation.append({
                "relationType": "IsDerivedFrom",
                "relatedIdentifier": parent_project.doi,
                "relatedIdentifierType": "DOI",
            })
        else:
            url = "https://{0}{1}".format(current_site, reverse(
                'published_project',
                args=(parent_project.slug, parent_project.version)))
            relation.append({
                "relationType": "IsDerivedFrom",
                "relatedIdentifier": url,
                "relatedIdentifierType": "URL",
            })

    resource_type = 'Dataset'
    if project.resource_type.name == 'Software':
        resource_type = 'Software'

    payload = {
        "data": {
            "type": "dois",
            "attributes": {
                "event": event,
                "prefix": settings.DATACITE_PREFIX,
                "titles": [{
                    "title": project.title
                }],
                "publisher": current_site.name,
                "publicationYear": timezone.now().year,
                "types": {
                    "resourceTypeGeneral": resource_type
                },
                "creators": authors,
                "version": version,
                "descriptions": [{
                    "description": project.abstract_text_content(),
                    "descriptionType": "Abstract"
                }],
                "url": project_url,
                "relatedIdentifiers": relation,
            }
        }
    }

    return payload


def get_doi_status(project_doi):
    """
    Get the status of a DOI which can be draft, registered or findable.
    """
    headers = {'Content-Type': 'application/vnd.api+json'}
    url = '{0}/{1}'.format(settings.DATACITE_API_URL, project_doi)
    response = get(url, headers=headers, auth=HTTPBasicAuth(
        settings.DATACITE_USER, settings.DATACITE_PASS))
    if response.status_code < 200 or response.status_code >= 300:
        if response.status_code == 404:
            raise Exception("DOI {} not found.".format(project_doi))
        raise Exception("There was an unknown error updating the DOI, here is \
            the response text: {0}".format(response.text))
    content = json.loads(response.text)
    state = content['data']['attributes']['state']
    if state and isinstance(state, str):
        return state
    raise Exception('Unkown state of the DOI')
