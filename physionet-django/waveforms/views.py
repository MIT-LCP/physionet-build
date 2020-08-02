import os
from django.shortcuts import render
from physionet.settings import base


BASE_DIR = base.BASE_DIR
DEMO_FILE_ROOT = os.path.abspath(os.path.join(BASE_DIR, os.pardir))
FILE_LOCAL = os.path.join('demo-files', 'static', 'published-projects')

def waveform_published_home(request, project_slug, version):
    """
    Render waveform main page for published databases. Also pass in
    some initial values to create the dropdown options.

    Parameters
    ----------
    project_slug : str
        The slug of the current project.
    version : str
        The versions of the current project.

    Returns
    -------
    N/A : HTML page / template variable
        HTML webpage responsible for hosting the waveform plot. Also pass
        through the project slug and version as variables for use both in
        the template and the waveform app.

    """
    context = {
        'dash_context': {
            'target_id': {
                'value': {
                    'project_slug': project_slug,
                    'version': version
                }
            }
        }
    }

    return render(request, 'waveforms/home.html', context)
