"""
Module for generating notifications
"""
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.template import loader


RESPONSE_ACTIONS = {0:'rejected', 1:'accepted'}


# ---------- Project App ---------- #

def invitation_notify(request, invite_author_form, target_email):
    """
    Notify someone when they are invited to author a project
    """
    inviter = invite_author_form.inviter
    project = invite_author_form.project
    subject = 'Invitation to author project: {}'.format(project.title)
    email_context = {'inviter_name':inviter.get_full_name(),
                     'inviter_email':inviter.email,
                     'project':project,
                     'domain':get_current_site(request)}
    body = loader.render_to_string('notification/email/invite_author.html',
                                    email_context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [target_email], fail_silently=False)


def invitation_response_notify(invitation, affected_emails):
    """
    Notify the submitting author when an invitation to join a project
    is processed.
    """
    response = RESPONSE_ACTIONS[invitation.response]
    project = invitation.project

    subject = 'Authorship invitation {} for project: {}'.format(response,
                                                                project.title)
    email, name = project.author_contact_info(only_submitting=True)
    email_context = {'name':name, 'project':project,
        'response':response}
    # Send an email for each email belonging to the accepting user
    for author_email in affected_emails:
        email_context['author_email'] = author_email
        body = loader.render_to_string(
            'notification/email/author_response.html', email_context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def submit_notify(project):
    """
    Notify authors when a project is submitted
    """
    subject = 'Submission of project: {}'.format(project.title)
    email_context = {'project':project}
    for email, name in project.author_contact_info():
        email_context['name'] = name
        body = loader.render_to_string(
            'notification/email/submit_notify.html', email_context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def resubmit_notify(project):
    """
    Notify authors and the editor when a project is resubmitted
    """
    subject = 'Resubmission of project: {}'.format(project.title)
    email_context = {'project':project}
    for email, name in project.author_contact_info():
        email_context['name'] = name
        body = loader.render_to_string(
            'notification/email/resubmit_notify.html', email_context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                          [email], fail_silently=False)

    email_context['name'] = project.editor.get_full_name()
    body = loader.render_to_string(
        'notification/email/resubmit_notify_editor.html', email_context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [project.editor.email], fail_silently=False)

# ---------- Console App ---------- #

def assign_editor_notify(project):
    """
    Notify authors when an editor is assigned
    """
    subject = 'Editor assigned to submission of project: {0}'.format(
        project.title)
    for email, name in project.author_contact_info():
        body = loader.render_to_string(
            'notification/email/assign_editor_notify.html',
            {'name':name, 'project':project,
             'editor':project.editor})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)

def edit_decision_notify(request, project, edit_log):
    """
    Notify authors when an editor makes a decision
    """
    # Reject
    if edit_log.decision == 0:
        subject = 'Submission rejected for project {}'.format(project.title)
        template = 'notification/email/reject_submission_notify.html'
    # Resubmit with revisions
    elif edit_log.decision == 1:
        subject = 'Revisions requested for project {}'.format(project.title)
        template = 'notification/email/revise_submission_notify.html'
    # Accept
    else:
        subject = 'Submission accepted for project: {}'.format(project.title)
        template = 'notification/email/accept_submission_notify.html'

    for email, name in project.author_contact_info():
        body = loader.render_to_string(template,
            {'name':name, 'project':project, 'edit_log':edit_log,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def copyedit_complete_notify(request, project, copyedit_log):
    """
    Notify authors when the editor has finished copyediting
    """
    subject = 'Copyedit complete for project: {0}'.format(project.title)
    for email, name in project.author_contact_info():
        body = loader.render_to_string(
            'notification/email/copyedit_complete_notify.html',
            {'name':name, 'project':project, 'copyedit_log':copyedit_log,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def reopen_copyedit_notify(request, project):
    """
    Notify authors when an editor reopens a project for copyediting
    """
    subject = 'Project reopened for copyediting: {0}'.format(project.title)
    for email, name in project.author_contact_info():
        body = loader.render_to_string(
            'notification/email/reopen_copyedit_notify.html',
            {'name':name, 'project':project,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)

def authors_approved_notify(request, project):
    subject = 'All authors approved publication of project: {0}'.format(
        project.title)
    for email, name in project.author_contact_info():
        body = loader.render_to_string(
            'notification/email/authors_approved_notify.html',
            {'name':name, 'project':project,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def publish_notify(request, published_project):
    """
    Notify authors when a project is published
    """
    subject = 'Your project has been published: {0}'.format(
        published_project.title)
    for email, name in published_project.author_contact_info():
        body = loader.render_to_string(
            'notification/email/publish_notify.html',
            {'name':name, 'published_project':published_project,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def storage_response_notify(storage_request):
    """
    Notify submitting author when storage request is processed
    """
    project = storage_request.project
    response = RESPONSE_ACTIONS[storage_request.response]
    subject = 'Storage request {0} for project: {1}'.format(response,
        project.title)
    email, name = project.author_contact_info(only_submitting=True)
    body = loader.render_to_string('notification/email/storage_response_notify.html',
        {'name':name, 'project':project, 'response':response,
         'allowance':storage_request.request_allowance,
         'response_message':storage_request.response_message})
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [email], fail_silently=False)

