# Directory File Content

- `physionet.sock`: The socket file uWSGI and nginx use to communicate.
- `physionet_nginx.conf`: The nginx configuration file for the PhysioNet site.
- `physionet_uwsgi.ini`: Initialization file for uWSGI.
- `uwsgi_params`: Generic parameters for uWSGI.
- `post-receive`: The post-receive hook that runs in the bare repository in the staging/production servers.
- `uwsgi.service`: The uWSGI emperor mode configuration service file.

# Development Workflow

## Servers

- Development: Done on local developer machines.
- Staging server: For staging changes before they are applied to production. Aims to replicate the production environment. Hosts the `pn-staging` remote bare repository. Accessed through url: `staging.physionet.org`. Available through internal network only.
- Production server: For live production. Hosts the `pn-production` remote bare repository. Accessed through `beta.physionet.org` or `physionet.org` when ready. Initially available through internal network only.

## Git Branches

- `<new feature branch>`: make a branch off the `dev` branch to begin implementing a feature or fix.
- `dev`: the branch with the latest development features, accepted by all developers, run locally.
- `staging`: stable version of the code, run against replication of the live database.
- `production`: stable version of the code, run against live database.

## Workflow

- Pull requests are made against the `dev` branch on Github to introduce bug fixes, new functionality. These are merged manually after review and automated tests against a test database. Merging to `dev` triggers a pull request to the `staging` branch.
- Merge the `dev` branch into the `staging` branch via pull request on Github, following a successful merge into `dev`. Push the `staging` branch to the staging server. Run tests on, and inspect the staging server. If errors are found, revert to the previous stable staging state.
- When the changes appear stable on the staging server, the `staging` branch is manually merged with the `production` branch via pull request on Github. Push the `production` branch to the production server. If errors are found, revert to the previous stable production state.

# Initial Server Setup

Run these commands once only, on the staging and production servers.

## System Packages

Run as root:
```
apt-get update
apt-get install -y python3-dev python3-pip build-essential libpq-dev postgresql postgresql-contrib nginx
apt-get install upgrade
pip3 install --upgrade pip
pip3 install virtualenv uwsgi
```

## Dedicated User

Create a user for the site. They should own all the site's files, and all interactions with the site should be run by them.

Append this to their `.bashrc` for when you need to to manually run management commands:

`export DJANGO_SETTINGS_MODULE=physionet.settings.<staging OR production>`

## Postgres Database Setup

Create the user and database called `physionet`. Enter the password.

```
sudo -i -u postgres
createuser physionet -P
createdb physionet -O physionet
exit
```

Set the authentication system for the `physionet` user to md5 password in the postgres settings file: `/etc/postgresql/<version>/main/pg_hba.conf file`, by adding this line above the default setting entries:

`local   all             physionet                               md5 `

Restart the postgres server with:

`/etc/init.d/postgresql restart`


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

Add the `post-receive` file to the bare repository's `hooks` directory. Ensure it is executable:

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

A service file was created to be controlled  by systemctl. This file will say requirements
for this service to run, it will set the user and group for the emperor mode, and
sets the log location to syslog.

## Setting up the cron for the scheduled tasks

Scheduled tasks have been added, it uses the system cron executing the tasks twice a day. (this can be changed if needed.)
`0 */12 * * * export DJANGO_SETTINGS_MODULE=physionet.settings.staging  && source /physionet/python-env/physionet/bin/activate && python /physionet/physionet-build/physionet-django/manage.py runcrons >> /var/log/cronjob.log`
