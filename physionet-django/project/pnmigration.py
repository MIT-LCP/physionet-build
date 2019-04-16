import datetime
import os
import pdb
import pytz
import requests
from urllib.request import urlopen

from django.core import serializers

from project.models import LegacyProject, PublishedProject


def load_legacy_html(slug):
    """
    Load data from a pbank database and create a LegacyProject object
    # Some pages end with this: <!--#include virtual="/dir-footer.shtml"-->
    """
    try:
        f = urlopen('https://physionet.org/physiobank/database/{}/HEADER.shtml'.format(slug))
    except:
        f = urlopen('https://physionet.org/physiobank/database/{}/index.shtml'.format(slug))
    content = f.read().decode('utf8')
    f.close()
    return content


# List of all physiobank databases
dbs = open('project/DBS.tsv')
dbs = dbs.readlines()
dbs = [d.split('\t') for d in dbs]


def create_legacy_projects():
    """
    Import the pbank html content into new LegacyProject objects.

    This does nothing for physiotools which is more irregular.
    """
    for slug, title, pubdate in dbs:
        r = requests.get('https://physionet.org/physiobank/database/{}/HEADER.shtml'.format(slug))
        if r.status_code != 200:
            r = requests.get('https://physionet.org/physiobank/database/{}/index.shtml'.format(slug))
            if r.status_code != 200:
                print('{} does not exist'.format(slug))
                continue
        content = load_legacy_html(slug=slug)
        p = LegacyProject.objects.create(title=title, slug=slug,
            full_description=content, publish_date=datetime.datetime.strptime(pubdate.strip(), '%d %B %Y'))


def write_legacy_fixtures(resource_type=None):
    """
    Write all the LegacyProject data to fixtures. Specify resource
    type if desired.

    """
    if resource_type is None:
        resource_type = [0, 1, 2]
    elif resource_type in [0, 1, 2]:
        resource_type = [resource_type]

    for rt in resource_type:
        file = ['project/fixtures/pbank.json', 'project/fixtures/ptools.json',
                'project/fixtures/challenge.json'][rt]
        with open(file, 'w') as f:
            data = serializers.serialize('json', LegacyProject.objects.filter(
                resource_type=rt), stream=f, indent=2)


def publish_legacy(slug, make_file_roots=False):
    "publish a legacy project given by the slug"
    lp = LegacyProject.objects.get(slug=slug)
    lp.publish(make_file_roots)


def publish_all_legacy(make_file_roots=False):
    "Publish all legacy projects"
    for l in LegacyProject.objects.all().order_by('publish_date'):
        l.publish(make_file_roots)


def clear_all_legacy():
    "clear all legacy objects"
    LegacyProject.objects.all().delete()


def clear_all_published():
    "Remove all published projects"
    for p in PublishedProject.objects.all():
        p.remove(force=True)
