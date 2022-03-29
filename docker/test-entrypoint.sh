#!/bin/bash

set -e

mkdir -p $STATIC_ROOT/published-projects
mkdir -p $MEDIA_ROOT/{active-projects,archived-projects,credential-applications,published-projects,users}

./docker/wait-for-it.sh --strict $DB_HOST:5432
./docker/wait-for-it.sh --strict $GCS_HOST:4443

cd physionet-django
python manage.py makemigrations --dry-run --no-input --check
python manage.py resetdb
python manage.py loaddemo
coverage run --source='.' manage.py test --verbosity=3 --keepdb
coverage report -m
