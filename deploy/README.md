# Initial Server Setup

Run these commands once only, on the staging and production servers.

## System Packages

apt-get update
apt-get install python3-dev python3-pip build-essential libpq-dev postgresql postgresql-contrib nginx
apt-get install upgrade
pip3 install --update pip
pip3 install virtualenv uwsgi

## Postgres Database Setup

sudo -i -u postgres
createuser physionet
createdb physionet -O physionet


## File Directories and Python Environments

**For Production Server**:
`$DJANGO_SETTINGS_MODULE=physionet.settings.production`

**For Staging Server**
`$DJANGO_SETTINGS_MODULE=physionet.settings.production`

Nothing to be done for development environments.

```
mkdir /physionet
cd /physionet
mkdir physionet-django media static python-env
cd python-env
virtualenv -p/usr/bin/python3 physionet
```
