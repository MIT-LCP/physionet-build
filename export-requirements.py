#!/usr/bin/env python3
"""
Generate requirements.txt from uv.lock.

The staging and production servers install packages with
`pip install -r requirements.txt --require-hashes` (see deploy/update).

`uv export` writes each package without the extras that other packages
request, e.g. `google-api-core==2.25.1` rather than
`google-api-core[grpc]==2.25.1`. Older versions of pip (such as the one
bundled with Debian 12's virtualenv) then reject the file in hash-checking
mode, because `google-api-core[grpc]` is not pinned. This script adds those
extras back.

Usage (from the repository root):

    ./export-requirements.py           # write requirements.txt
    ./export-requirements.py --check   # fail if requirements.txt is out of date
"""

import argparse
import collections
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'requirements.txt'
HEADER = (
    '# This file is generated from uv.lock by export-requirements.py.\n'
    '# Do not edit it by hand.\n'
)


def requested_extras():
    """Return {package name: set of extras} requested anywhere in uv.lock."""
    with open(ROOT / 'uv.lock', 'rb') as f:
        lock = tomllib.load(f)

    extras = collections.defaultdict(set)
    for package in lock['package']:
        deps = list(package.get('dependencies', []))
        for group in ('optional-dependencies', 'dev-dependencies'):
            for group_deps in package.get(group, {}).values():
                deps.extend(group_deps)
        for dep in deps:
            extras[dep['name']].update(dep.get('extra', []))
    return extras


def export():
    result = subprocess.run(
        ['uv', 'export', '--format', 'requirements-txt', '--frozen',
         '--no-emit-project', '--no-header'],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    extras = requested_extras()

    def add_extras(match):
        name = match.group(1)
        if extras.get(name):
            return '{}[{}]=='.format(name, ','.join(sorted(extras[name])))
        return match.group(0)

    body = re.sub(r'^([a-z0-9][a-z0-9._-]*)==', add_extras, result.stdout,
                  flags=re.MULTILINE)
    return HEADER + body


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--check', action='store_true',
                        help='exit with an error if requirements.txt is out of date')
    args = parser.parse_args()

    content = export()
    if args.check:
        if OUTPUT.read_text() != content:
            print('requirements.txt is out of date. '
                  'Regenerate it with: ./export-requirements.py', file=sys.stderr)
            sys.exit(1)
        print('requirements.txt is up to date.')
    else:
        OUTPUT.write_text(content)


if __name__ == '__main__':
    main()
