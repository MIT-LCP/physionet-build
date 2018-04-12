# Directory File Content

- `physionet.sock` : The socket file uWSGI and nginx use to communicate.
- `physionet_nginx.conf` : The nginx configuration file for the PhysioNet site.
- `physionet_uwsgi.ini` : Initialization file for uWSGI.
- `uwsgi_params` : Generic parameters for uWSGI.

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
mkdir media static python-env
cd python-env
virtualenv -p/usr/bin/python3 physionet
```

## Setting up nginx and uwsgi

http://uwsgi-docs.readthedocs.io/en/latest/tutorials/Django_and_nginx.html

Symlink the nginx configuration file for the site:

`sudo ln -s /physionet/physionet-build/deploy/physionet_nginx.conf /etc/nginx/sites-enabled/`


Run uWSGI with the initialization file settings:
```
cd /physionet/physionet-build/deploy
uwsgi --ini physionet_uwsgi.ini
```

Restart nginx:

`sudo /etc/init.d/nginx restart`

nginx error log file: `/var/log/nginx/error.log`
