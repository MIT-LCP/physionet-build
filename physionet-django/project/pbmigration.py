import datetime
import os
import pdb
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

for slug, title, pubdate in dbs[:2]:
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


# Write all the pbank LegacyProject data to fixtures
with open('project/fixtures/pbank.json', 'w') as f:
    data = serializers.serialize('json', LegacyProject.objects.all(),
        stream=f)
    JsonSerializer = serializers.get_serializer('json')
    json_serializer = JsonSerializer()
    json_serializer.serialize(LegacyProject.objects.all(), f)


LegacyProject.objects.all().delete()
