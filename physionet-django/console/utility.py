import json
import logging

from django.conf import settings
from django.contrib.sites.models import Site
from django.urls import reverse
from django.utils import timezone
from requests import get, post, put
from requests.auth import HTTPBasicAuth

from project.cloud.gcp import (
    add_email_bucket_access,
    bucket_info,
    check_bucket_exists,
    create_access_group,
    create_bucket,
    create_directory_service,
    make_bucket_public,
    remove_bucket_permissions,
    update_access_group,
    upload_files,
)
from project.validators import validate_doi

LOGGER = logging.getLogger(__name__)


class DOIExistsError(Exception):
    pass


class DOICreationError(Exception):
    pass


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

    If event is "publish", project must be a PublishedProject object.
    If event is "draft", project may be either a PublishedProject or
    an ActiveProject.

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
        if not project.is_latest_version:
            raise Exception("core_project=True requires the latest version")
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

    if event == "publish":
        publish_datetime = project.publish_datetime
    elif event == "draft":
        publish_datetime = timezone.now()
    else:
        raise Exception("event must be 'publish' or 'draft'")

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
            "relatedIdentifierType": "DOI",
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
                "publicationYear": publish_datetime.year,
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
