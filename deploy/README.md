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

```
# Create the necessary directories
mkdir /physionet
cd /physionet
mkdir physionet-build media static python-env
# Create the bare repository
git init --bare physionet-build.git
# Create the virtual environment
cd python-env
virtualenv -p/usr/bin/python3 physionet
# Copy over the .env file into /physionet/physionet-build
scp <somewhere>/.env /physionet/physionet-build/
```

Create the `post-receive` file in the bare repository's `hooks` directory:

```
#!/bin/bash
destination=/physionet/physionet-build/
echo "Deploying into $destination"
GIT_WORK_TREE=$destination git checkout --force

echo "Updating content"
cd $destination
source /physionet/python-env/physionet/bin/activate
pip install -r requirements.txt
cd physionet-django
python manage.py collectstatic
python manage.py makemigrations
python manage.py migrate
touch physionet/wsgi.py

echo "Done"

```

Ensure it is executable:

`chmod +x post-receive`

## Deploying to the Bare Repository

Add the remote bare repositories from your local development machines:

`git remote add <pn-staging OR pn-production> <user>@<address>:/physionet/physionet-build.git`

Push to the remotes when appropriate

`git push <pn-staging OR pn-production> <staging OR production>`

## Setting up nginx and uwsgi

http://uwsgi-docs.readthedocs.io/en/latest/tutorials/Django_and_nginx.html

Symlink the nginx configuration file for the site, and remove the default:

```
sudo ln -s /physionet/physionet-build/deploy/physionet_nginx.conf /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
```

Restarting nginx: `sudo /etc/init.d/nginx restart`

The nginx error log file: `/var/log/nginx/error.log`

Set the `DJANGO_SETTINGS_MODULE` environment variable as appropriate in the
`physionet_uwsgi.ini` file to reference the correct settings file.

Setup for uWSGI to run in emperor mode. Link the init file for physionet into the vassals folder.
```
sudo mkdir /etc/uwsgi
sudo mkdir /etc/uwsgi/vassals
sudo ln -s /physionet/physionet-build/deploy/physionet_uwsgi.ini /etc/uwsgi/vassals/
# This runs uwsgi in emperor mode with the pn user and group
# uwsgi --emperor /etc/uwsgi/vassals --uid pn --gid pn
```

## Setting up the system to run uwsgi upon startup

The `/etc/rc.local` file runs upon system startup. Create it and make it executable
(755) and owned by root if not already existing. Ensure the following is contained
in the file:
```
#!/bin/sh -e

uwsgi --emperor /etc/uwsgi/vassals --uid pn --gid pn

exit 0

```

Kill the emperor mode process if needed.
