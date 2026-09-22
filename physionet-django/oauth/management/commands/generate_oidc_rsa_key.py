import os
import sys

from django.core.management.base import BaseCommand
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


class Command(BaseCommand):
    help = 'Generate an RSA private key for signing OIDC ID tokens'

    def add_arguments(self, parser):
        parser.add_argument(
            '--bits',
            type=int,
            default=2048,
            help='Key size in bits (minimum 2048, default 2048)',
        )
        parser.add_argument(
            '--output',
            type=str,
            default=None,
            help='Write key to file (with 0600 permissions) instead of stdout',
        )

    def handle(self, *args, **options):
        bits = options['bits']
        if bits < 2048:
            self.stderr.write(self.style.ERROR('Key size must be at least 2048 bits'))
            return

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=bits,
        )
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        output_file = options['output']
        if output_file:
            fd = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(pem)
            self.stderr.write(self.style.SUCCESS(f'RSA key written to {output_file}'))
        else:
            if sys.stdout.isatty():
                self.stderr.write(self.style.WARNING(
                    'WARNING: Writing private key to terminal. '
                    'Use --output <file> or redirect to a file instead.'
                ))
            self.stdout.write(pem)
