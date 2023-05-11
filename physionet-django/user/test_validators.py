from unittest import TestCase

from django.core.exceptions import ValidationError

from user.validators import validate_organization, validate_reference_response, validate_research_summary


class TestValidators(TestCase):

    def test_organization_with_newline_is_invalid(self):
        self.assertRaises(ValidationError, validate_organization, 'Johnson\nJohnson')

    def test_organization_with_special_character_is_valid(self):
        self.assertIsNone(validate_organization('Johnson & Johnson'))

    def test_organization_with_number_as_first_character_is_valid(self):
        self.assertIsNone(validate_organization('21st century fox'))

    def test_organization_with_special_character_as_first_character_is_invalid(self):
        self.assertRaises(ValidationError, validate_organization, '&Johnson')
