# Initial Server Setup

Run these commands once only, on the staging and production servers.

## System Packages

```
apt-get update
apt-get install -y python3-dev python3-pip build-essential libpq-dev postgresql postgresql-contrib nginx
apt-get install upgrade
pip3 install --upgrade pip
pip3 install virtualenv uwsgi
```

## Postgres Database Setup

Create the user and database called `physionet`. Enter the password.

```
sudo -i -u postgres
createuser physionet -P
createdb physionet -O physionet
exit
```

Set the authentication system for the `physionet` user to md5 in the postgres
settings file: `/etc/postgresql/<version>/main/pg_hba.conf file`, by adding this line:

`local   all             physionet                               md5 `

## File Directories and Python Environments

Set the environment variable to reference the correct settings file.

**For Production Server**:
`export DJANGO_SETTINGS_MODULE=physionet.settings.production`

**For Staging Server**
`export DJANGO_SETTINGS_MODULE=physionet.settings.production`

```
mkdir /physionet
cd /physionet
mkdir physionet-django media static python-env
cd python-env
virtualenv -p/usr/bin/python3 physionet
```

## Setting up nginx and uwsgi

http://uwsgi-docs.readthedocs.io/en/latest/tutorials/Django_and_nginx.html

