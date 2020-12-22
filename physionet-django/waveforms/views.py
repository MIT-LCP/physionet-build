import os
from django.shortcuts import render
from physionet.settings import base


def waveform_published_home(request, project_slug, project_version):
    """
    Render waveform main page for published databases. Also pass in
    some initial values to create the dropdown options.

    Parameters
    ----------
    project_slug : str
        The slug of the current project.
    project_version : str
        The version of the current project.

    Returns
    -------
    N/A : HTML page / template variable
        HTML webpage responsible for hosting the waveform plot. Also pass
        through the project slug and version as variables for use both in
        the template and the waveform app.

    """
    dash_context = {
        'set_slug': {'value': project_slug},
        'set_version': {'value': project_version},
        'set_record': {'value': ''},
    }

    return render(request, 'waveforms/home.html',
        {'dash_context': dash_context})
