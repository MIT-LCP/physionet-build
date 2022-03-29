#!/bin/bash

set -e

mkdir -p $STATIC_ROOT/published-projects
mkdir -p $MEDIA_ROOT/{active-projects,archived-projects,credential-applications,published-projects,users}

./docker/wait-for-it.sh $DB_HOST:5432
if [ -n "$GCS_HOST" ]; then
    ./docker/wait-for-it.sh $GCS_HOST:4443
fi

python physionet-django/manage.py migrate

if [ "$1" = "sleep" ]; then
    echo "Infinite sleep"
    exec /bin/sh -c "trap : TERM INT; (while true; do sleep 86400; done) & wait"
else
    exec $@
fi
