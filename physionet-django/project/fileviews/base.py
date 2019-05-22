from django.shortcuts import render, redirect


def render_raw(request, infile, context):
    return redirect(context['file_raw_url'])


def render_unknown(request, infile, context, show_plain=False):
    context['show_plain'] = show_plain
    return render(request, 'project/file_view.html', context)


def render_empty(request, infile, context):
    return render(request, 'project/file_view_empty.html', context)
