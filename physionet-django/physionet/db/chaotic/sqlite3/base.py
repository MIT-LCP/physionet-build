"""
Database backend for sqlite3, with results shuffled by default.

This module implements a database using sqlite3, but with the caveat
that, if a query returns multiple rows, and the order of those rows is
not fully specified, they will be returned in a random order.

(In contrast, the sqlite3 library itself, and thus the standard Django
sqlite3 backend, will always return rows in a predictable order -
typically, the same order that the rows were inserted.  This can hide
bugs during testing, since other database engines give no such
guarantees.)

This is done by implicitly adding 'RANDOM()' as the final ordering
criterion for every SELECT query.  Thus, if the caller does not
specify an order at all, the order of rows will be completely random.
If the caller specifies one or more columns to be used for ordering,
but two rows have identical values for those columns, the order of
those two rows will be random.

In all other respects, this module is intended to be a drop-in
replacement for django.db.backends.sqlite3.
"""

from django.db.backends.sqlite3 import base


class DatabaseOperations(base.DatabaseOperations):
    # override the base compiler_module
    # ("django.db.models.sql.compiler") with our custom module
    compiler_module = "physionet.db.chaotic.compiler"


class DatabaseWrapper(base.DatabaseWrapper):
    # override the base ops_class
    # (django.db.backends.sqlite3.base.DatabaseOperations)
    # with our custom class
    ops_class = DatabaseOperations
