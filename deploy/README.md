# Files in Current Directory

- `emperor.uwsgi.service`: The uWSGI emperor mode configuration service file.
- `physionet_nginx.conf`: The nginx configuration file for the PhysioNet site.
- `physionet_uwsgi.ini`: Initialization file for uWSGI.
- `post-receive`: The post-receive hook that runs in the bare repository in the staging/production servers.
- `uwsgi_params`: Generic parameters for uWSGI.

They will need to be copied respectively to:
- `/etc/systemd/system/emperor.uwsgi.service`
- `/etc/nginx/sites-available/physionet_nginx.conf`
- `/etc/uwsgi/vassals/physionet_uwsgi.ini`
- `/physionet/physionet-build.git/hooks/post-receive`
- No need to copy.


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

Create a user for the site. ie: `pn`. They should own all the site's files, and all interactions with the site should be run by them.

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

Run as root:

```
# Create the necessary directories
mkdir /physionet
cd /physionet
mkdir physionet-build python-env deploy
# Create the bare repository
git init --bare physionet-build.git
# Add the `post-receive` file to the bare repository's `hooks` directory. Ensure it is executable
scp <somewhere>/post-receive /physionet/physionet-build.git/hooks/post-receive
chmod +x /physionet/physionet-build.git/hooks/post-receive
# Create the virtual environment
cd python-env
virtualenv -p/usr/bin/python3 physionet
cd /physionet
# Copy over the .env file into /physionet/physionet-build
scp <somewhere>/.env /physionet/physionet-build/
# The software folder should be owned by the dedicated user. The socket file directory should be accessible by nginx.
chown -R pn.pn /physionet
chown pn.www-data /physionet/deploy
chmod g+w /physionet/deploy
# Make the static and media roots
mkdir /data
mkdir /data/pn-static
mkdir /data/pn-static/published-projects
mkdir /data/pn-media
mkdir /data/pn-media/{active-projects,archived-projects,credential-applications,published-projects,users}
chown -R pn.pn /data/{pn-media,pn-static}
```

The directory structure for the site's software and files will be:
- `/physionet` : custom software for running the site
- `/physionet/physionet-build/` : the deployed content of this django project
- `/physionet/physionet-build.git/` : the bare git repository of this project
- `/physionet/python-env/` : for storing python environments
- `/physionet/deploy/` : for storing the socket file
- `/data/pn-static/` : the static root
- `/data/pn-media/` : the media root


## Deploying to the Bare Repository

Before deploying for the first time, make sure to set the variables in the `post-receive` file in the bare repository.

Add the remote bare repositories from your local development machines:

`git remote add <pn-staging OR pn-production> <user>@<address>:/physionet/physionet-build.git`

Push to the remotes when appropriate

`git push <pn-staging OR pn-production> <staging OR production>`

If there are database structure changes, log into the server and make the migrations.

`python manage.py makemigrations;python manage.py migrate`

Touch the uwsgi vassal file to force the emperor process to start new workers which reflect the updated changes.

`touch /etc/uwsgi/vassals/physionet_uwsgi.ini`


## Setting up nginx and uwsgi

http://uwsgi-docs.readthedocs.io/en/latest/tutorials/Django_and_nginx.html

Copy the nginx configuration file for the site to the `sites-available` directory, symlink it to `sites-enabled`, and remove the default symlink. Fill in the correct domain variables in the file the first time. Make sure to update this file whenever it is updated in this project.

```
sudo cp /physionet/physionet-build/deploy/physionet_nginx.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/physionet_nginx.conf /etc/nginx/sites-enabled/physionet_nginx.conf
sudo rm /etc/nginx/sites-enabled/default
```

Restarting nginx: `sudo /etc/init.d/nginx restart`

The nginx error log file: `/var/log/nginx/error.log`

Set the `DJANGO_SETTINGS_MODULE` environment variable as appropriate in the `physionet_uwsgi.ini` file to reference the correct settings file.

Setup for uWSGI to run in emperor mode. Fill in the missing environment variable in the uwsgi init file, and copy it into the vassals folder. Make sure to update this file whenever it is updated in this project.
```
sudo mkdir /etc/uwsgi
sudo mkdir /etc/uwsgi/vassals
sudo cp /physionet/physionet-build/deploy/physionet_uwsgi.ini /etc/uwsgi/vassals/
# This runs uwsgi in emperor mode with the pn user and group
# uwsgi --emperor /etc/uwsgi/vassals --uid pn --gid pn
```

## Setting up the system to run uWSGI with systemctl

The `emperor.uwsgi.service` file was created to be controlled by systemctl. This file will say requirements for this service to run, it will set the user and group for the emperor mode, and sets the log location to syslog.

`sudo cp /physionet/physionet-build/deploy/emperor.uwsgi.service /etc/systemd/system/`

Restarting and checking the status of the service:

`sudo systemctl restart emperor.uwsgi.service`
`sudo systemctl status emperor.uwsgi.service`


## Initial Site Content

There is initial data for the site (licenses, tags, etc) in `site-data.json` fixture files in the fixtures directories of certain apps. Load them before deploying the site for the first time with:

`python manage.py loaddata site-data`.


## Setting up the cron for the scheduled tasks

Scheduled tasks have been added, it uses the system cron executing the tasks twice a day. (this can be changed if needed.)
`0 */12 * * * export DJANGO_SETTINGS_MODULE=physionet.settings.staging  && source /physionet/python-env/physionet/bin/activate && python /physionet/physionet-build/physionet-django/manage.py runcrons >> /var/log/cronjob.log`

## Pushing into staging or live

To move the content from dev into staging or live, make sure your local dev is up to date. Then run the following with either staging or production. If you have origin as the only remote, this will only update in GitHub.
```
git checkout staging
git rebase dev
git push origin staging
git push pn-staging staging
```

After this, enter the server and run any migrations (if needed), then touch the vassal file.
```
./manage.py makemigrations
./manage.py migrate
touch /etc/uwsgi/vassals/physionet_uwsgi.ini 
```