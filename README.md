# PhysioNet Build

The new PhysioNet platform built using Django. The new site is currently hosted at [https://physionet.org/](https://physionet.org/)

## Running Local Instance Using Django Server

- Install sqlite3: `sudo apt-get install sqlite3`.
- Create python environment with >=python 3.8.
- Activate virtual python environment.
- Install python packages in `requirements.txt`.
- Copy `.env.example` file to `.env`.
- Within the `physionet-django` directory:
  - Run: `python manage.py resetdb` to reset the database.
  - Run: `python manage.py loaddemo` to load the demo fixtures set up example files.
  - Run: `python manage.py runserver` to run the server.

The local development server will be available at [http://localhost:8000](http://localhost:8000).

## Running Local Instance Using Docker

- Install docker: [https://docs.docker.com/engine/install/](https://docs.docker.com/engine/install/).
- Copy the example config: `cp .env.example .env`.
- Build the physionet image: `docker-compose build`.
- Run `docker-compose up` to run the postgres database, development and test containers.
- In a separate shell:
  - Run: `docker-compose exec dev /bin/bash` to enter the development container shell.
  - Within the `physionet-django` directory:
    - Run: `python manage.py resetdb` to reset the database.
    - Run: `python manage.py loaddemo` to load the demo fixtures set up example files.
  - Run: `docker-compose exec test /bin/bash` to enter the test container shell.
  - Within the `physionet-django` directory:
    - Run: `python manage.py resetdb` to reset the database.
    - Run: `python manage.py loaddemo` to load the demo fixtures set up example files.
    - Run: `python manage.py test` to run the tests.

The local development server will be available at [http://localhost:8000](http://localhost:8000).

All the management commands should be executed inside the desired container (with `docker-compose exec dev /bin/bash/` or `docker-compose exec test /bin/bash`).

The code should dynamically reload in development, however, if there are any issues you can stop the `docker-compose up` command and run `docker-compose up --build` which will rebuild the physionet image.

Docker-compose uses volumes to persist the database contents and data directories (media and static files). To clean up the created containers, networks and volumes stop `docker-compose up` and run `docker-compose down -v`. Do not run `docker-compose down -v` if you want to retain current database contents.

## Using a debugger with Docker

To access a debug prompt raised using `breakpoint()`:

- Run `docker container ls` to get a list of active containers
- Find the "CONTAINER_ID" for the dev_1 container
- In a new shell, attach to the container with `docker attach CONTAINER_ID`

The debugger should now be available in the new shell. 

- To detach from the container, press "Control+p, "Control+q" in a sequence. Note: "Control+c" will stop the container dev_1. 

## Contribution Guidelines

- Familiarise yourself with the [PEP8 style guidelines](https://www.python.org/dev/peps/pep-0008/).
- Create a branch originating from the `dev` branch, titled after the new feature/change to be implemented.
- Write tests for your code where possible (see "Testing" section below). Confirm that all tests pass before making a pull request.
- If you create or alter any models or fields, you'll need to generate one or more accompanying migration scripts. Commit these scripts alongside your other changes.
- Make a pull request to the `dev` branch with a clear title and description of the changes. Tips for a good pull request: http://blog.ploeh.dk/2015/01/15/10-tips-for-better-pull-requests/

## Testing

If using docker, all of the commands should run inside the test container (`docker-compose exec test /bin/bash`). You may need to `pip install coverage` beforehand if not using docker.

- Unit tests for each app are kept in their `test*.py` files.
- To run the unit tests, change to the `physionet-django` directory and run `python manage.py test`.
- To check test coverage, change to the `physionet-django` directory and run `coverage run --source='.' manage.py test`. Next run `coverage html` to generate an html output of the coverage results.
- To check code style, change to the `physionet-django` directory and run `flake8 [PATH_TO_FILE(s)]`. As part of the `physionet-build-test` workflow, flake8 will be run only against modified code relative to `dev` or the base PR branch. 
Note: `flake8` is only installed in the workflow. To install it for local testing, see [here](https://flake8.pycqa.org/en/latest/).
- To run the browser tests in the `test_browser.py` files, selenium and the [firefox driver](https://github.com/mozilla/geckodriver/releases) are required. If you want to see the test run in your browser, remove the `options.set_headless(True)` lines in the `setUpClass` of the browser testing modules.

## Database Content During Development

During development, the following workflow is applied for convenience:
- The database engine is sqlite3 if not using docker. The db.sqlite3 file will not be tracked by git, and hence will not be uploaded and shared between developers
- Demo model instances will be specified in json files in the `fixtures` subdirectory of each app. Example file: `<BASE_DIR>/<appname>/fixtures/demo-<appname>.json`

To conveniently obtain a clean database with the latest applied migrations, run:`python manage.py resetdb`. This does not populate the database with any data.

When using docker, the migrated and empty database will be the default state and only `python manage.py loaddemo` has to be called in both `dev` and `test` containers.

### Creating a branch with migrations

If you need to add, remove, or modify any models or fields, your branch will also need to include the necessary migration script(s).  In most cases, Django can generate these scripts for you automatically, but you should still review them to be sure that they are doing what you intend.

After making a change (such as adding a field or changing options), run `./manage.py makemigrations` to generate a corresponding migration script.  Then run `./manage.py migrate` to run that script on your local sqlite database.

If you make changes and later decide to undo them without committing, the easiest way is to simply run `rm */migrations/*.py && git checkout */migrations` to revert to your current HEAD.  Then run `./manage.py makemigrations` again if necessary, followed by `./manage.py resetdb && ./manage.py loaddemo`.

If other migrations are committed to dev in the meantime, you will need to resolve the resulting conflicts before your feature branch can be merged back into dev.  There are two ways to do this:

#### Merging migrations

If the two sets of changes are independent, they can be combined by merging `dev` into the feature branch and adding a "merge migration":
 * `git checkout my-new-feature && git pull && rm */migrations/*.py && git checkout */migrations`
 * `git merge --no-ff --no-commit origin/dev`
 * `./manage.py makemigrations --merge`
The latter command will ask you to confirm that the changes do not conflict (it will *not* detect conflicts automatically.)  Read the list of changes carefully before answering.  If successful, you can then run:
 * `./manage.py migrate && ./manage.py test`
 * `git add */migrations/ && git commit`
As with any pull request, have someone else review your changes before merging the result back into `dev`.

#### Rebasing migrations

If the migration behavior interacts with other changes that have been applied to dev in the meantime, the migration scripts will need to be rewritten.
 * Either rebase the feature branch onto origin/dev, or merge origin/dev into the feature branch.
 * Roll back migrations by running `rm */migrations/*.py; git checkout origin/dev */migrations`
 * Generate new migrations by running `./manage.py makemigrations`
 * `./manage.py migrate && ./manage.py test`
 * `git add */migrations/ && git commit`

#### Theming instructions

The theme of the deployed website can be configured by changing the following environment variables:

  * DARK
  * PRIMARY
  * SECONDARY
  * SUCCESS
  * INFO
  * WARNING
  * DANGER
  * LIGHT
  

  The management command "compilestatic" generates a theme.scss file and compiles the following CSS files.
  
   *  static/custom/css/home.css
   *  static/bootstrap/css/bootstrap.css

**Note:** The css files above are not tracked by git and are generated only when you run compilestatic command.


#### Setting Up Cronjobs

If you want to setup cronjobs, you can do that by adding a new file or update the existing cronjobs file based on your requirements.

Here are the loations where you might want to add your cronjobs.

1. `deploy/common/etc/cron.d/`

2. `deploy/staging/etc/cron.d/` (For cronjobs that should run on staging environment)

3. `deploy/production/etc/cron.d/` (For cronjobs that should run on production environment)

Here is an example of existing cronjob from `deploy/production/etc/cron.d/physionet`:

```sh
31 23 * * *  www-data  env DJANGO_SETTINGS_MODULE=physionet.settings.production /physionet/python-env/physionet/bin/python3 /physionet/physionet-build/physionet-django/manage.py clearsessions
```

## Package management

`pyproject.toml` is the primary record of dependencies. This file is typically [used by pip](https://pip.pypa.io/en/stable/reference/build-system/pyproject-toml/) for package management. Dependencies are also tracked in [`pyproject.toml`](https://python-poetry.org/docs/pyproject/) and [`requirements.txt`](https://pip.pypa.io/en/stable/reference/requirements-file-format/).

The process for updating packages is:

1. Add the dependency to `pyproject.toml`
2. Generate a new `poetry.lock` file with: `poetry lock --no-update`
3. Generate a new requirements.txt with: `poetry export -f requirements.txt --output requirements.txt --with dev`
