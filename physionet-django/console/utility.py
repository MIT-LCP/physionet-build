from os import walk, chdir, listdir, path
from requests.auth import HTTPBasicAuth
from requests import post, put, get
import json
import pdb

from oauth2client.service_account import ServiceAccountCredentials
from google.api_core.exceptions import BadRequest
from django.contrib.sites.models import Site
from googleapiclient.discovery import build
from django.utils.html import strip_tags
from django.utils import timezone
from google.cloud import storage
from django.conf import settings
from django.urls import reverse
from html2text import html2text

from project.validators import validate_doi

import logging

LOGGER = logging.getLogger(__name__)
Public_Roles = ['roles/storage.legacyBucketReader', 'roles/storage.legacyObjectReader',
    'roles/storage.objectViewer']

def check_bucket(project, version):
    """
    Function to check if a bucket already exists 
    """
    storage_client = storage.Client()
    domain = 'physionet.org'
    if 'production' not in settings.SETTINGS_MODULE:
        domain = 'testing-delete.' + domain
    bucket_name = '{0}-{1}.{2}'.format(project, version, domain)
    exists = storage_client.lookup_bucket(bucket_name)
    if exists:
        return bucket_name
    return False

def create_bucket(project, version, protected=False):
    """
    Function to create a bucket and set its permissions
    """
    storage_client = storage.Client()
    domain = 'physionet.org'
    if 'production' not in settings.SETTINGS_MODULE:
        domain = 'testing-delete.' + domain
    bucket_name = '{0}-{1}.{2}'.format(project, version, domain)
    bucket = storage_client.create_bucket(bucket_name)
    bucket = storage_client.bucket(bucket_name)
    bucket.iam_configuration.bucket_policy_only_enabled = True
    bucket.patch()
    LOGGER.info("Created bucket {0} for project {1}".format(bucket_name.lower(), project))
    if not protected:
        make_bucket_public(bucket)
    else:
        remove_bucket_permissions(bucket)
    return bucket_name

def make_bucket_public(bucket):
    """
    Function to make a bucket public to all users 
    """
    policy = bucket.get_iam_policy()
    for role in Public_Roles:
        policy[role].add('allUsers')
    bucket.set_iam_policy(policy)
    LOGGER.info("Made bucket {} public".format(bucket.name))

def remove_bucket_permissions(bucket):
    """
    Function to remove all permissions from bucket but owner 
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
        LOGGER.info("Removed all read permissions from bucket {}".format(bucket.name))

def add_email_bucket_access(project, email):
    """
    Function to add access to a bucket from a email 
    If the email is elegible to be used in GCP the set iam policy will pass
    If not, it will return a error as a bad requet.
    """
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(project.gcp.bucket_name)
    policy = bucket.get_iam_policy()
    for role in Public_Roles:
        policy[role].add('user:'+email)
    try:
        bucket.set_iam_policy(policy)
        LOGGER.info("Added email {0} to the project {1} access list".format(
            email, project))
        return True
    except BadRequest: 
        LOGGER.info("There was an error on the request. The email {} was ignored.".format(
            email))
        return False

def upload_files(project):
    """
    Function to send files to a bucket. Gets a list of all the 
    files under the project root directory then it sends each file 
    one by one. The only way to know if the zip file is created is to 
    heck the compressed sotrage size. If the zip is created, then send it.
    """
    file_root = project.file_root()
    subfolders_fullpath = [x[0] for x in walk(file_root)]
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(project.gcp.bucket_name)
    for indx, location in enumerate(subfolders_fullpath):
        chdir(location)
        files = [f for f in listdir('.') if path.isfile(f)]
        for file in files:
            temp_dir = location.replace(file_root,'')
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

############################################################
## Unused functions below this line, but usefull to have.
def set_bucket_permissions(bucket_name, email):
    """
    Function to set the permissions of a bucket to a specific group
    if ACL are used. At the moment we deal with bucket level permissions. 
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    bucket.acl.group(email).grant_read()
    bucket.acl.save()

def list_bucket_permissions(bucket):
    """
    Function to list all the permissions of a bucket.
    """
    policy = bucket.get_iam_policy()
    for role in policy:
        members = policy[role]
        print('Role: {}, Members: {}'.format(role, members))


def create_directory_service(user_email):
    """Build and returns an Admin SDK Directory service object authorized with the service accounts
    that act on behalf of the given user.
    Args:
      user_email: The email of the user. Needs permissions to access the Admin APIs.
    Returns:
      Admin SDK directory service object.
    """
    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
    credentials = ServiceAccountCredentials.from_p12_keyfile(
        settings.SERVICE_ACCOUNT_EMAIL,
        settings.SERVICE_ACCOUNT_PKCS12_FILE_PATH,
        settings.GCP_SECRET_KEY,
        scopes=['https://www.googleapis.com/auth/admin.directory.group'])
    # This requires the email used to delegate the credentials to the serivce account
    credentials = credentials.create_delegated(user_email)
    return build('admin', 'directory_v1', credentials=credentials)


def paginate(request, to_paginate, maximun):
    """
    Function to paginate the arguments. 
    """
    page = request.GET.get('page', 1)
    paginator = Paginator(to_paginate, maximun)
    paginated = paginator.get_page(page)
    return paginated


def create_doi_draft(project):
    """
    Create a draft DOI with some basic information about the project.

    A POST request is done to set the base information.
    The assigned DOI is returned to be used in the template.

    On successfull creation returns the asigned DOI
    On tests return empty leaving the DOI object the same

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
    url = settings.DATACITE_API_URL
    current_site = Site.objects.get_current()
    headers = {'Content-Type': 'application/vnd.api+json'}
    resource_type = 'Dataset'
    if project.resource_type.name == 'Software':
        resource_type = 'Software'

    payload = {
        "data": {
            "type": "dois",
            "attributes": {
                "event": "draft",
                "prefix": settings.DATACITE_PREFIX,
                "titles": [{
                    "title": project.title
                }],
                "publisher": current_site.name,
                "publicationYear": timezone.now().year,
                "types": {
                    "resourceTypeGeneral": resource_type
                },
            }
        }
    }

    response = post(url, data=json.dumps(payload), headers=headers,
        auth=HTTPBasicAuth(settings.DATACITE_USER, settings.DATACITE_PASS))
    if response.status_code < 200 or response.status_code >= 300:
        raise Exception("There was an unknown error submitting the DOI, here \
            is the response text: {}".format(response.text))

    content = json.loads(response.text)
    validate_doi(content['data']['attributes']['doi'])
    LOGGER.info("DOI draft for project {0} was created with DOI: {1}.".format(
        project.title, content['data']['attributes']['doi']))
    return content['data']['attributes']['doi']


def publish_doi(project):
    """
    Upate a DOI from draft to publish.

    The URL is made using the prefix and doi assigned to the project.
    """
    publish = False
    if project.doi:
        if get_doi_status(project.doi) == "draft":
            publish = True
        payload, url = generate_doi_info(project, publish=publish)
        send_doi_update(url, payload)
    if project.core_project.doi and project.is_latest_version:
        if get_doi_status(project.core_project.doi) == "draft":
            publish = True
        payload, url = generate_doi_info(project, core_project=True,
            publish=publish)
        send_doi_update(url, payload)


def send_doi_update(url, payload):
    """
    Execute a DOI change. This can be used to update and/or publish the DOI.

    A PUT request is done in order to update the information for the DOI.
    """
    headers = {'Content-Type': 'application/vnd.api+json'}
    response = put(url, data=json.dumps(payload), headers=headers,
        auth=HTTPBasicAuth(settings.DATACITE_USER, settings.DATACITE_PASS))
    if response.status_code < 200 or response.status_code >= 300:
        raise Exception("There was an unknown error updating the DOI, \
            here is the response text: {0}".format(response.text))


def generate_doi_info(project, core_project=False, publish=False):
    """
    Generate the payload and url to be used to update a DOI information.

    Returns the payload that will publish or update the DOI and its URL
    """
    current_site = Site.objects.get_current()
    #
    url = '{0}/{1}'.format(settings.DATACITE_API_URL, project.doi)
    project_url = "https://{0}{1}".format(current_site, reverse(
        'published_project', args=(project.slug, project.version)))

    if core_project:
        url = '{0}/{1}'.format(settings.DATACITE_API_URL,
            project.core_project.doi)
        project_url = "https://{0}/{1}".format(current_site, reverse(
            'published_project_latest', args=(project.slug,)))

    author_list = project.author_list().order_by('display_order')
    authors = []
    for author in author_list:
        authors.append({"givenName": author.user.profile.first_names,
                        "familyName": author.user.profile.last_name,
                        "name": author.get_full_name()})

    description = project.abstract_text_content()
    payload = {
        "data": {
            "type": "dois",
            "attributes": {
                "titles": [{
                    "title": project.title
                }],
                "publicationYear": timezone.now().year,
                "creators": authors,
                "descriptions": [{
                    "description": description,
                    "descriptionType": "Abstract"
                }],
                "url": project_url
            }
        }
    }
    if publish:
        payload["data"]["attributes"]["event"] = "publish"
    return payload, url


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
