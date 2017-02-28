# Software Installation and Workflow Notes #

## Installed Packages ##

The following should be called on each of the three servers:

```
sudo apt-get install emacs	// 24.5.1
sudo apt-get install git	// 2.11.0
sudo apt-get install postgresql postgresql-contrib	// psql (PostgreSQL) 9.6.2
sudo apt-get install python-pip		// 9.0.1
sudo apt-get install python-django	// 1.10.5
sudo apt-get install apache2		// 2.4.25
sudo apt-get install libapache2-mod-wsgi	// 4.5.11-1
```

### Python ###

Default installed Python versions:
- Python 2.7.13
- Python 3.5.13

The 'requirements.txt' file is created using `pip freeze`.

No Python packages are installed using pip. 

The Django project is created with: `django-admin startproject physionet` (Python 2.7.13 Django 1.10.5). The project directory is renamed to 'physionet-django'. 

## Deployment ##

### File Locations and Initializations ###

For each of the three Physionet servers:

- The bare git repository (of this project) is stored in: `/physionet/git/physionet-build.git`. Must be initialized once for each server: `mkdir -p /physionet/git/physionet-build.git && cd /physionet/git/physionet-build.git && git init --bare`. The *post-receive* hook file must be manually created and made executable. 
- The implemented Django project is stored in: `/physionet/www/physionet-django`. Must be initialized once for each server: `mkdir /physionet/www/physionet-django`
- The apache settings files are stored in the standard debian location: `/etc/apache2/`. The *physionet.conf* apache configuration file in which we store the virtual host settings must be created and enabled once for each server: `sudo a2ensite physionet.conf`
- When changes are pushed, the bare repository's contents are cloned into a temporary working directory in: `/physionet/tmp/physionet-build-tmp`. The base directory must be initialized once for each server: `mkdir -p /physionet/tmp`
- The static front-end files (css, etc) are served in STATIC_ROOT, which we define as the *static* directory within the django project root. The apache configuration file must allow access to the full static directory (`/physionet/www/physionet-django/static`), static files (including the django admin css files) must be collected using `python manage.py collectstatic` upon deployment using hooks, and the *urls* file must have its *urlpatterns* variable appended with `static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)`. 

### Git Branches ###

The content in each of the three main branches is to be used only by its corresponding server. The branches are:

- dev - The unstable development branch. Hosted at [dev.physionet.org](dev.physionet.org) by server physionet-dev: *192.168.11.101*
- staging - For the stable unreleased version of the website. Hosted at [staging.physionet.org](staging.physionet.org) by server physionet-staging: *192.168.11.102*
- live - For the live public version of the website. Hosted at [physionet.org](physionet.org) by server physionet-live: *192.168.11.103*

When adding/editing content, create a new git branch. Work flow: **personal branch** --> **dev** --> **staging** --> **live**. Each merging stage requires a pull request.

Developers are to edit the content of this git project on their local computers. In addition to the [github remote](https://github.com/MIT-LCP/physionet-build), they should add the remote repositories for each of the three servers: 
- `git remote add deploy-dev ssh://<username>@192.168.11.101:/physionet/git/physionet-build.git`
- `git remote add deploy-staging ssh://<username>@192.168.11.102:/physionet/git/physionet-build.git`
- `git remote add deploy-live ssh://<username>@192.168.11.103:/physionet/git/physionet-build.git`

### Deploy Workflow ###

- Create a new branch and commit your changes.
- Push the new branch to github.
- Create a pull request to the *dev* branch on github
- When the pull request is successfully merged, pull the `dev` branch to your local machine.
- Push the changes of the dev branch to the development server: `git push deploy-dev dev`. The *post-receive* hook script will be run.
- Continue for *staging* and then *live* branch when appropriate. 

