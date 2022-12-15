from django.db.models.sql import compiler
from django.db.models.expressions import OrderBy
try:
    from django.db.models.expressions import Random
except ImportError:
    from django.db.models.functions import Random


class SQLCompiler(compiler.SQLCompiler):
    """
    SQL compiler class that shuffles results by default.

    When compiling a query, 'RANDOM()' is always included as the final
    ordering criterion.  Thus, if the caller does not specify an
    explicit order for the query, the results will be returned in a
    random order.

    If the caller specifies a partial order - e.g. objects are to be
    sorted by timestamp, but two existing objects have identical
    timestamps - then only the ambiguous cases will be shuffled.

    (The actual implementation of the RANDOM function is up to the
    database engine itself.)
    """
    def get_order_by(self):
        result = super().get_order_by()
        result.append((OrderBy(Random()), ('RANDOM()', [], False)))
        return result


class SQLInsertCompiler(compiler.SQLInsertCompiler):
    pass


class SQLDeleteCompiler(compiler.SQLDeleteCompiler):
    pass


class SQLUpdateCompiler(compiler.SQLUpdateCompiler):
    pass


class SQLAggregateCompiler(compiler.SQLAggregateCompiler):
    pass
