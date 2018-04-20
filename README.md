# PhysioNet Build

Rebuilding PhysioNet using Django.

Dev branch: [![Run Status](https://api.shippable.com/projects/59e7d1baaf0a170700d5b5b0/badge?branch=dev)](https://app.shippable.com/github/MIT-LCP/physionet-build) [![Coverage Badge](https://api.shippable.com/projects/59e7d1baaf0a170700d5b5b0/coverageBadge?branch=dev)](https://app.shippable.com/github/MIT-LCP/physionet-build)

## Running Local Instance Using Django Server

- Create python environment with python 3.6.
- Install python packages in `requirements.txt`.
- Install sqlite3: `sudo apt-get install sqlite3`.
- Activate virtual python environment.
- Within the `physionet-django` directory:
  - Run: `python manage.py resetdb` to reset the database.
  - Run: `python manage.py loaddemo` to load the demo fixtures set up example files.
  - Run: `python manage.py runserver` to run the server.

## Contribution Guidelines

- Familiarise yourself with the PEP8 style guidelines: https://www.python.org/dev/peps/pep-0008/
- Create a branch originating from the `dev` branch, titled after the new feature/change to be implemented.
- Write tests for your code where possible (see "Testing" section below). Confirm that all tests pass before making a pull request.
- Make a pull request to the `dev` branch with a clear title and description of the changes. Tips for a good pull request: http://blog.ploeh.dk/2015/01/15/10-tips-for-better-pull-requests/

## Testing

- Unit tests for each app are kept in their `test*.py` files.
- To run the unit tests, change to the `physionet-django` directory and run `python manage.py test`.
- To check test coverage, change to the `physionet-django` directory and run `coverage run --source='.' manage.py test`. Next run `coverage html` to generate an html output of the coverage results. You may need to `pip install coverage` beforehand.

## Database Content During Development

During development, the following workflow is applied for convenience:
- The database engine is sqlite3. The db.sqlite3 file will not be tracked by git, and hence will not be uploaded and shared between developers
- Database migration files will not be tracked by git. Sequential migrations are not applied. Instead, every time a batch of content is to be changed or added, the database file and migration history are deleted, and the demo data is reimported
- Demo model instances will be specified in json files in the `fixtures` subdirectory of each app. Example file: `<BASE_DIR>/<appname>/fixtures/demo-<appname>.json`

To conveniently obtain a clean database with the latest applied migrations, run:`python manage.py resetdb`. This does not populate the database with any data.

There will be a vastly different workflow during actual deployment, when migrations are to be sequentially applied and tracked, and data is to be kept.
