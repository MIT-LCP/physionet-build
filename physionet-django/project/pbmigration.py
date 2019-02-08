import datetime
import os
import pdb
import pytz
import requests
from urllib.request import urlopen

from django.core import serializers

from project.models import LegacyProject


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


dbs = open('project/DBS.tsv')
dbs = dbs.readlines()
dbs = [d.split('\t') for d in dbs]


def create_legacy_projects():
    """
    Import the pb html content into new LegacyProject objects
    """
    for slug, title, pubdate in dbs:
        r = requests.get('https://physionet.org/physiobank/database/{}/HEADER.shtml'.format(slug))
        if r.status_code != 200:
            r = requests.get('https://physionet.org/physiobank/database/{}/index.shtml'.format(slug))
            if r.status_code != 200:
                pdb.set_trace()
                print('{} does not exist'.format(slug))
                continue
        content = load_legacy_html(slug=slug)
        p = LegacyProject.objects.create(title=title, slug=slug,
            full_description=content, publish_date=datetime.datetime.strptime(pubdate.strip(), '%d %B %Y'))


def write_legacy_fixtures():
    "Write all the pbank LegacyProject data to fixtures"
    with open('project/fixtures/pbank.json', 'w') as f:
        data = serializers.serialize('json', LegacyProject.objects.all(),
            stream=f)


def publish_legacy(slug):
    "publish a legacy project given by the slug"
    lp = LegacyProject.objects.get(slug=slug)
    lp.publish()


def publish_all_legacy():
    "Publish all legacy projects"
    for l in LegacyProject.objects.all().order_by('publish_date'):
        if l.doi:
            l.publish()


def clear_all_legacy():
    "clear all legacy objects"
    LegacyProject.objects.all().delete()


def clear_all_published():
    "Remove all published projects"
    for p in PublishedProject.objects.all():
        p.remove(force=True)
