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

    def test_reference_response_with_special_character_is_valid(self):
        self.assertIsNone(validate_reference_response('An excellent researcher. I worked with them directly '
                                                      '& they were very helpful. This person is 100% awesome!'))

    def test_reference_response_with_newline_is_valid(self):
        self.assertIsNone(validate_reference_response('An excellent researcher.  \nI worked with them directly'))

    def test_reference_response_with_number_as_first_character_is_valid(self):
        self.assertIsNone(validate_reference_response('1. An excellent researcher. I worked with them directly'))

    def test_reference_response_with_special_character_as_first_character_is_invalid(self):
        self.assertRaises(ValidationError, validate_reference_response, '. An excellent researcher. '
                                                                        'I worked with them directly')

    def test_research_summary_with_special_character_is_valid(self):
        self.assertIsNone(validate_research_summary('I have done lots of research. 100% awesome!'))

    def test_research_summary_with_newline_is_valid(self):
        self.assertIsNone(validate_research_summary('An excellent researcher.  \n200 publications and counting.'))

    def test_research_summary_with_number_as_first_character_is_valid(self):
        self.assertIsNone(validate_research_summary('200 publications and counting. An excellent researcher.'))

    def test_research_summary_with_special_character_as_first_character_is_invalid(self):
        self.assertRaises(ValidationError, validate_research_summary, '. 200 publications and counting.')
