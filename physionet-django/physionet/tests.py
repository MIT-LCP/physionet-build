import doctest

from physionet import utility

# Automatically run documentation tests in these modules.
DOCTEST_MODULES = [
    utility,
]

DOCTEST_FLAGS = doctest.REPORT_NDIFF


def load_tests(loader, tests, ignore):
    for module in DOCTEST_MODULES:
        tests.addTests(doctest.DocTestSuite(module, optionflags=DOCTEST_FLAGS))
    return tests
