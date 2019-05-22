from django.shortcuts import render


def render_image(request, infile, context):
    return render(request, 'project/file_view_image.html', context)
