#!/bin/bash
#
# Test live upgradability of the PhysioNet Django server.
#
# This script attempts to test that, if the production server is
# running the specified git revision (e.g. 'origin/production'), and
# we perform a live upgrade to the version currently in the working
# tree, the server should remain functional at all times.
#
# Note that these tests will run resetdb/loaddemo (multiple times) and
# thus will destroy the contents of your local development database.
# These tests only work because we use a "mirror" database for testing
# (in physionet.settings.development.sqlite and
# physionet.settings.development.pgsql), which is not the usual Django
# configuration.
#
# We assume that upgrade steps will be performed in the following
# order.  Some steps might not actually change anything, and the
# corresponding tests may be skipped.
#
# STEP 1: Upgrade dependencies according to requirements.txt.
#
#   At this point, the database has not been modified, and the old
#   server code is still running, but new Python libraries may have
#   been installed.  (Some of those might include database migrations
#   of their own, which will not have been applied.)  We simulate this
#   condition by loading the demo database (manage.py
#   resetdb/loaddemo) from OLD-REVISION, then using pip to upgrade the
#   dependencies.  The old server tests should still pass under these
#   circumstances.
#
# STEP 2: Apply "early" migrations from the new version.
#
#   Now, the old server code is still running, but the database has
#   been upgraded by applying some migrations.  We simulate this by
#   using the old demo database (kept from the previous test) and
#   using the new server code (manage.py migratetargets) to apply
#   early migrations to that database.  The old server tests should
#   still pass under these circumstances.
#
# STEP 3: Restart server processes using the new server code.
#
#   Now, the new server code is running, but the database has not yet
#   had "late" migrations applied.  We simulate this by loading the
#   new demo database (manage.py resetdb/loaddemo) and then
#   un-applying late migrations (manage.py migratetargets).  The new
#   server tests should pass under these circumstances.
#
# STEP 4: Apply "late" migrations from the new version.
#
#   Now, the new server code is running and the database has been
#   fully upgraded.  This should be equivalent to a clean installation
#   of the new server code, and the new server tests should pass under
#   these circumstances.
#
# There are a lot of caveats here - this doesn't test whether the
# server keeps working while migrations are happening, doesn't test
# whether the old server works with new static files installed, and of
# course doesn't test whether anything could go wrong due to
# desynchronization between server and client.  "In-place" upgrades
# are risky, too: there could be traps due to libraries, server code,
# or template files being partially installed.

set -e
set -o pipefail

################################################################
# Initialization

# Parse command line
verbose=
if [ "$1" = "-v" ]; then
    verbose=1
    shift
fi
if [ $# = 0 ]; then
    echo "Usage: $0 [-v] old-revision [test-args]" >&2
    exit 1
fi
oldrevname=$1
shift
test_args=("$@")
test_args+=("--keepdb")
if [ -n "$verbose" ]; then
    test_args+=("--verbosity=3")
fi

case ${DJANGO_SETTINGS_MODULE-none} in
    physionet.settings.development.*|none)
        ;;
    *)
        echo "Unsupported DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE" >&2
        exit 1
        ;;
esac

# Go to top level directory of the git repository
scriptname=$(command -v "$0")
topdir=$(dirname "$scriptname")
topdir=$(cd "$topdir" && pwd)
cd "$topdir"

# Identify the "old" revision to be upgraded from
oldrev=$(git rev-parse --verify "$oldrevname^{commit}")

# Generate a pretty name for the "current" revision
currevname=$(git describe --all --always --dirty)

################################################################
# Functions for reporting test results

# Show message that a test was skipped
msg_skip()
{
    echo "$*" >&3
}

# Show message that a test is running
msg_testing()
{
    current_test="$*"
    echo "$*" >&2
    echo "================================================================" >&2
    printf "%s" "$*..." >&3
}

# Show message that a test succeeded
msg_success()
{
    current_test=
    echo " OK" >&3
    echo "================================================================" >&2
}

# Show message that a test failed
msg_failure()
{
    echo " FAILED" >&3
    echo " *** FAILED: $current_test" >&2
    echo "================================================================" >&2
}

# Show message that a test failed, and exit immediately
msg_critical()
{
    msg_failure
    grep -F ' *** FAILED: ' "$topdir/$logfile" >&3
    exit 1
}

# Run a command and report success or failure
check_cmd()
{
    echo "$(pwd) \$ $*" | sed "s|$olddir|<OLD>|g" | sed "s|$topdir|<NEW>|g" >&2
    if env "$@"; then
        msg_success
    else
        echo " *** '$*' failed ($?)" >&2
        msg_failure
    fi
}

# Run a command and exit if it fails
prereq_cmd()
{
    echo "$(pwd) \$ $*" | sed "s|$olddir|<OLD>|g" | sed "s|$topdir|<NEW>|g" >&2
    if ! env "$@"; then
        echo " *** '$*' failed ($?)" >&2
        msg_critical
    fi
}

################################################################
# Set up logging

logfile=$(echo "test-upgrade_$(date +%Y%m%d%H%M)_${currevname}.log" | tr / ,)
if [ -n "$verbose" ]; then
    exec 3>/dev/null &> >(tee -a "$logfile")
else
    exec 3>&1 &>"$logfile"
    echo "Testing upgrade from $oldrevname to $currevname" >&3
    echo "  Log file: $logfile" >&3
fi

echo "================================================================"
echo "Testing upgrade:"
echo " * Old: $oldrevname ($oldrev)"
echo " * New: $currevname (HEAD=$(git rev-parse HEAD))"
echo " * DJANGO_SETTINGS_MODULE: ${DJANGO_SETTINGS_MODULE-unset}"
echo

# Show commits added/removed between old revision and HEAD
git log "$oldrev...HEAD" --reverse --topo-order \
    --pretty=format:' %m %h %an: %s'
echo
echo

# Show a summary of uncommitted changes
git status --short

echo "================================================================"

################################################################
# Set up working directory and useful variables

workdir=$topdir/test-upgrade.tmp
if [ -d "$workdir" ]; then
    find "$workdir" -type d -exec chmod u+w '{}' ';'
fi
rm -rf "$workdir"

olddir=$workdir/old
mkdir -p "$olddir"
git archive "$oldrev" | tar -x -C "$olddir"

venvdir=$workdir/VE

if [ -x "$(command -v md5sum)" ]; then
    venvcachedir=$topdir/test-upgrade.cache
    mkdir -p "$venvcachedir"
    old_reqs_hash=$(md5sum "$olddir/requirements.txt" | cut -d' ' -f1)
    new_reqs_hash=$(md5sum "$topdir/requirements.txt" | cut -d' ' -f1)
else
    venvcachedir=
fi

current_targets=$workdir/CURRENT-TARGETS
old_targets=$workdir/OLD-TARGETS
early_targets=$workdir/EARLY-TARGETS
late_targets=$workdir/LATE-TARGETS

ln -s "$topdir/.env" "$olddir/.env"

export PATH=$venvdir/bin:$PATH

################################################################
# Set up old virtualenv directory and demo database
(
    cd "$olddir/physionet-django"

    msg_testing "Installing old requirements"
    cachefile=$venvcachedir/$old_reqs_hash.tar.gz
    if [ -n "$venvcachedir" ] && [ -f "$cachefile" ]; then
        prereq_cmd mkdir "$venvdir"
        prereq_cmd tar -xzf "$cachefile" -C "$venvdir"
    else
        prereq_cmd virtualenv --quiet --quiet \
                   --no-download -ppython3 "$venvdir"
        prereq_cmd pip3 install --require-hashes \
                   -r "$olddir/requirements.txt"
        if [ -n "$venvcachedir" ]; then
            prereq_cmd tar -czf "$cachefile" -C "$venvdir" .
        fi
    fi
    msg_success

    msg_testing "Loading old demo database"
    prereq_cmd ./manage.py resetdb
    prereq_cmd ./manage.py loaddemo
    msg_success
)
################################################################
# Upgrade virtualenv directory
(
    cd "$topdir/physionet-django"

    msg_testing "Installing new requirements"
    if ! cmp -s "$olddir/requirements.txt" "$topdir/requirements.txt"; then
        cachefile=$venvcachedir/$old_reqs_hash-$new_reqs_hash.tar.gz
        if [ -n "$venvcachedir" ] && [ -f "$cachefile" ]; then
            prereq_cmd rm -rf "$venvdir"
            prereq_cmd mkdir "$venvdir"
            prereq_cmd tar -xzf "$cachefile" -C "$venvdir"
        else
            prereq_cmd pip3 install --require-hashes \
                       -r "$topdir/requirements.txt"
            if [ -n "$venvcachedir" ]; then
                prereq_cmd tar -czf "$cachefile" -C "$venvdir" .
            fi
        fi
    fi
    msg_success
)
################################################################
# Check migrations
(
    cd "$topdir/physionet-django"

    msg_testing "Checking migrations"
    prereq_cmd rm -f db.sqlite3
    prereq_cmd ln -s "$olddir/physionet-django/db.sqlite3" db.sqlite3
    prereq_cmd ./manage.py makemigrations --dry-run --no-input --check
    prereq_cmd ./manage.py getmigrationtargets --current > "$old_targets"
    prereq_cmd ./manage.py getmigrationtargets --early > "$early_targets"
    prereq_cmd ./manage.py getmigrationtargets > "$late_targets"
    msg_success
)
################################################################
# Run old tests, on old database, with new virtualenv
# (between upgrade steps 1 and 2)
(
    cd "$olddir/physionet-django"
    if cmp -s "$olddir/requirements.txt" "$topdir/requirements.txt"; then
        msg_skip "Skipping tests - requirements haven't changed."
    else
        msg_testing "Testing old server (with new libraries)"
        check_cmd ./manage.py test "${test_args[@]}"
    fi
)
################################################################
# Run old tests, on old database, after early migrations
# (between upgrade steps 2 and 3)
(
    cd "$topdir/physionet-django"
    msg_testing "Performing early migrations"
    prereq_cmd ./manage.py migratetargets --no-input "$early_targets"
    prereq_cmd ./manage.py getmigrationtargets --current > "$current_targets"
    check_cmd diff "$early_targets" "$current_targets"
)
(
    cd "$olddir/physionet-django"
    if cmp -s "$old_targets" "$early_targets"; then
        msg_skip "Skipping tests - no early migrations."
    else
        msg_testing "Testing old server (after early migrations)"
        check_cmd PHYSIONET_HYBRID_TEST=new-db \
                  ./manage.py test "${test_args[@]}"
    fi
)
################################################################
# Check that migrations can be applied to old database, forward and
# backward
(
    cd "$topdir/physionet-django"

    msg_testing "Performing late migrations"
    check_cmd ./manage.py migrate --no-input

    msg_testing "Undoing all migrations"
    check_cmd ./manage.py migratetargets --no-input \
              --reverse "$old_targets"

    msg_testing "Checking migrations were undone"
    prereq_cmd ./manage.py getmigrationtargets --current > "$current_targets"
    check_cmd diff "$old_targets" "$current_targets"
)
################################################################
# Run new tests, on new database
# (after upgrade step 4)
(
    cd "$topdir/physionet-django"

    msg_testing "Loading new demo database"
    prereq_cmd rm -f db.sqlite3
    prereq_cmd ./manage.py resetdb
    prereq_cmd ./manage.py loaddemo
    msg_success

    msg_testing "Testing new server"
    check_cmd ./manage.py test "${test_args[@]}"
)
################################################################
# Run new tests, on new database, before late migrations
# (between upgrade steps 3 and 4)
(
    cd "$topdir/physionet-django"

    msg_testing "Undoing late migrations"
    prereq_cmd ./manage.py migratetargets --no-input --reverse "$early_targets"
    prereq_cmd ./manage.py getmigrationtargets --current > "$current_targets"
    check_cmd diff "$early_targets" "$current_targets"

    if cmp -s "$early_targets" "$late_targets"; then
        msg_skip "Skipping tests - no late migrations."
    else
        msg_testing "Testing new server (before late migrations)"
        check_cmd PHYSIONET_HYBRID_TEST=old-db \
                  ./manage.py test "${test_args[@]}"
    fi
)
################################################################
# Check that migrations can be applied to new database, backward and
# forward
(
    cd "$topdir/physionet-django"

    msg_testing "Undoing early migrations"
    check_cmd ./manage.py migratetargets --no-input \
              --reverse "$old_targets"

    msg_testing "Checking migrations were undone"
    prereq_cmd ./manage.py getmigrationtargets --current > "$current_targets"
    check_cmd diff "$old_targets" "$current_targets"

    msg_testing "Redoing all migrations"
    check_cmd ./manage.py migrate --no-input
)

if grep -F ' *** FAILED: ' "$topdir/$logfile" >&3; then
    exit 1
else
    find "$workdir" -type d -exec chmod u+w '{}' ';'
    rm -rf "$workdir"

    echo "Success" >&3
    exit 0
fi
