# Remove database and all migrations. Recreate migrations and database, and fill with demo data.

# Remove all migrations
./rmmigrations.sh

# Delete database file
rm db.sqlite3

# Make migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Fill in the demo data
python manage.py shell < insertdemocontent.py
