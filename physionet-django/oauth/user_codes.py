"""
User codes for the device flow.

A user code is the short code that a script (such as the Python
package) shows, and that the user types in at /oauth/device/ to approve
the sign-in. Following RFC 8628 section 6.1, codes use consonants only,
so they are easy to read and type and cannot spell words. Eight
characters from 20 give about 34 bits, which is enough because codes
expire after a few minutes and failed attempts are rate limited.

This module has no Django imports, so settings can refer to it.
"""

import secrets

ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"
LENGTH = 8


def generate_user_code():
    """Return a new user code, such as "WDJB-MJHT"."""
    code = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return format_user_code(code)


def format_user_code(value):
    """
    Return a user code as stored, so that it can be typed in any case,
    with or without the hyphen or spaces.
    """
    code = "".join(char for char in value.upper() if char.isalpha())
    return f"{code[:4]}-{code[4:]}"
