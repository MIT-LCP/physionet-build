from django.forms.widgets import ClearableFileInput

class ProfilePhotoInput(ClearableFileInput):
    """
    The widget for uploading the profile photo
    """
    initial_text = 'Current'
    input_text = 'Update'
    clear_checkbox_label = 'Clear'
    template_name = 'user/profile_photo_input.html'
