from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from .forms import ProjectCreationForm

import pdb

@login_required
def create_project(request):
    user = request.user
    form = ProjectCreationForm(initial={'owner':user})

    if request.method == 'POST':
        form = ProjectCreationForm(request.POST)
        pdb.set_trace()
        if form.is_valid():
            print('\n\nvalid!')
            project = form.save(owner=user)
            redirect('home')

            # Registration successful
            return render(request, 'home', {'user':user})

    return render(request, 'project/create_project.html', {'form':form})
