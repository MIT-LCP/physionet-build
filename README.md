# PhysioNet Build

Rebuilding PhysioNet using django.

Project URL: https://github.com/MIT-LCP/physionet-build

## Running Local Instance Using Django Server

- Create python environment with python 3.5.
- Install python packages in `requirements.txt`.
- Install sqlite3: `sudo apt-get install sqlite3`
- Activate virtual environment
- Within the `physionet-django` directory, run: `python manage.py resetdb` to reset the database
- Within the `physionet-django` directory, run: `python manage.py runserver`

## Contribution Guidelines

- Create a branch originating from the `dev` branch, titled after the new feature/change to be implemented.
- Submit a pull request to the `dev` branch.
- Follow PEP8 style guidelines: https://www.python.org/dev/peps/pep-0008/

## Database Content During Development

During development, before the database contains any real data, the following setup/workflow is applied for convenience and flexibility:
- The database engine will be sqlite3. The db.sqlite3 file will not be tracked by git, and hence will not be uploaded and shared between developers.
- The database migrations files will not be tracked by git. Sequential migrations are not applied. Instead, every time a batch of content is to be changed or added, the database file and migration history are deleted, and the demo data is reimported.
- Demo model instances will be specified in json files in the `fixtures` subdirectory of each app. Example file: `<BASE_DIR>/<appname>/fixtures/<appname>.json`

To conveniently obtain a clean database populated with demo data, run:`python manage.py shell < resetdbs.py`

There will be a vastly different workflow during actual deployment, when migrations are to be sequentially applied and tracked, and data is to be kept.