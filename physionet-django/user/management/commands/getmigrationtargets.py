import collections
import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections, migrations

from django.db.migrations.executor import MigrationExecutor


def is_late_migration(migration):
    """
    Check whether a Migration is marked as a "late" migration.

    This means that the migration should not be applied until after
    all database clients have been upgraded to support the new schema.
    The default expectation is that the migration should be applied
    before upgrading clients.

    A "late" migration is one that has the MIGRATE_AFTER_INSTALL
    attribute set to True.  An "early" migration has
    MIGRATE_AFTER_INSTALL absent, or set to False.

    For example, a migration that creates a new table or column should
    typically be an early migration (since old clients will ignore the
    column but new clients expect it to be present):

        class Migration(migrations.Migration):
            dependencies = [
                ('foo', '0100_asdfghjk'),
            ]
            operations = [
                migrations.AddField(
                    model_name='mywidget',
                    name='myproperty',
                    field=models.DateTimeField(blank=True, null=True),
                )
            ]

    but one that removes an existing column should typically be a late
    migration (since old clients will expect it to be present but new
    clients will ignore it):

        class Migration(migrations.Migration):
            dependencies = [
                ('foo', '0100_asdfghjk'),
            ]
            operations = [
                migrations.RemoveField(
                    model_name='mywidget',
                    name='myproperty',
                )
            ]
            MIGRATE_AFTER_INSTALL = True
    """
    if not isinstance(migration, migrations.Migration):
        raise TypeError('expected a Migration, not {!r}'.format(migration))
    return getattr(migration, 'MIGRATE_AFTER_INSTALL', False)


class Command(BaseCommand):
    """
    Management command to display current migration targets.

    This command outputs a sequence of lines, each line containing an
    app name followed by a migration name (suitable for passing to the
    'migrate' command.)  The lines are in "forward" order, i.e. each
    line may have dependencies on the lines before it, but not the
    lines after it.

    Running this command with no arguments displays the latest
    migration for each app.

    Running this command with the --early option displays the latest
    migration that is *not* marked as MIGRATE_AFTER_INSTALL.

    Running this command with the --current option displays the latest
    migrations that are currently applied.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '--database', default=DEFAULT_DB_ALIAS,
            help='Name of database')
        parser.add_argument(
            '--current', action='store_true',
            help='List currently-applied migrations')
        parser.add_argument(
            '--early', action='store_true',
            help='Only consider "early" (pre-install) migrations')

    def handle(self, *args, **options):
        db = options['database']
        connection = connections[db]

        executor = MigrationExecutor(connection)

        # Get a list of all migrations that would be applied, in
        # order, starting from zero.
        default_targets = executor.loader.graph.leaf_nodes()
        default_plan = executor.migration_plan(default_targets,
                                               clean_start=True)

        applied = executor.loader.applied_migrations
        desired = []
        all_migration_apps = set()

        if options['verbosity'] >= 2:
            sys.stderr.write('Default migration plan:\n')
            self._print_migration_plan(default_plan, applied)
            sys.stderr.write('\n')

        for migration, _ in default_plan:
            app = migration.app_label
            name = migration.name
            all_migration_apps.add(app)
            if options['current']:
                # If --current is set, only list migrations that have
                # already been applied.
                if (app, name) in applied:
                    desired.append((app, name))
            elif options['early']:
                # If --early is set, only list migrations that have
                # already been applied OR that are considered "early"
                # migrations.
                if ((app, name) in applied
                        or not is_late_migration(migration)):
                    desired.append((app, name))
            else:
                # If neither --current nor --early is set, list all
                # migrations.
                desired.append((app, name))

        # Check if there are conflicts (multiple leaf nodes in same app.)
        conflicts = executor.loader.detect_conflicts()
        if conflicts:
            raise CommandError("Conflicting migrations detected; "
                               "multiple leaf nodes in the migration "
                               "graph ({})".format(conflicts))

        # Check if there are any migrations applied that we don't know
        # about.
        ghosts = applied.keys() - set(desired)
        if ghosts:
            mlist = ', '.join('{}.{}'.format(app, name)
                              for app, name in sorted(ghosts))
            raise CommandError("Some migrations that have already been "
                               "applied ({}) are not present in the "
                               "source tree.".format(mlist))

        # Determine the last desired migration for each individual
        # app, in the order that they would have been applied by
        # default.  (This should ensure that the migrations *can* be
        # applied by calling 'manage.py migrate APP NAME' separately
        # for each app, in the given order, without going backwards.)
        # For installed apps that contain migrations, but no
        # migrations are currently selected, set the target to None.
        targets = collections.OrderedDict()
        for app in sorted(all_migration_apps):
            targets[app] = None
        for (app, name) in desired:
            targets[app] = name
            targets.move_to_end(app)

        # Now make a plan for applying only the target migrations,
        # starting from the current state.
        current_plan = executor.migration_plan(list(targets.items()))

        if options['verbosity'] >= 2:
            sys.stderr.write('Chosen migration plan:\n')
            self._print_migration_plan(current_plan, applied)
            sys.stderr.write('\n')

        # Check that the new plan contains only "desired" migrations.
        selected = set(applied)
        for migration, _ in current_plan:
            app = migration.app_label
            name = migration.name
            selected.add((app, name))
            if options['early'] and is_late_migration(migration):
                # This can happen if the current migration is 0100,
                # 0101 is a late migration that depends on 0100, and
                # 0102 is an early migration that depends on 0101.
                #
                # That's not allowed - it means that 0101 depends on
                # application changes being installed first, but the
                # application changes depend on 0102 being applied
                # first.
                #
                # Instead, such a change must be deployed in stages:
                # the application code that 0101 depends on must be
                # installed first; then 0101 and 0102 can be applied;
                # and then the new application code that depends on
                # 0102 can be installed.
                raise CommandError("Applying early migrations would "
                                   "require first applying {}.{}, which "
                                   "is a late migration".format(app, name))
            elif (app, name) not in desired:
                # This shouldn't be possible.
                raise CommandError("Wait a minute, what is {}.{}?  That "
                                   "wasn't in the list!".format(app, name))

        # Check that all of the "desired" migrations have already been
        # applied or will be applied by the new plan.
        missing = set(desired) - selected
        if missing:
            # This can happen if there are multiple independent early
            # migrations for the same app, and the merge migration is
            # a late migration.  That's not allowed since there isn't
            # a unique target to specify.
            mlist = ', '.join('{}.{}'.format(app, name)
                              for app, name in sorted(missing))
            raise CommandError("Applying chosen migrations would "
                               "skip some desired migrations ({}). "
                               "Missing merge?".format(mlist))

        # Print target migrations in the order that they should be
        # applied.
        for (app, name) in targets.items():
            # The name "zero" is recognized by the migrate command as
            # signifying the state where no migrations are applied.
            if name is None:
                name = 'zero'
            sys.stdout.write('{} {}\n'.format(app, name))

    def _print_migration_plan(self, plan, applied_migrations):
        for migration, _ in plan:
            app = migration.app_label
            name = migration.name
            if (app, name) in applied_migrations:
                sys.stderr.write('[X]')
            else:
                sys.stderr.write('[ ]')
            if is_late_migration(migration):
                sys.stderr.write(' @')
            else:
                sys.stderr.write(' -')
            sys.stderr.write(' {}.{}\n'.format(app, name))
