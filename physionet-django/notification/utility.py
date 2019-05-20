"""
Module for generating notifications
"""
from urllib import parse

from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.template import loader


RESPONSE_ACTIONS = {0:'rejected', 1:'accepted'}


def send_contact_message(contact_form):
    """
    Send a message to the contact email
    """
    body = 'From: {} {}\n\nMessage:\n{}'.format(
        contact_form.cleaned_data['name'],
        contact_form.cleaned_data['email'],
        contact_form.cleaned_data['message'])
    send_mail(contact_form.cleaned_data['subject'], body, settings.CONTACT_EMAIL,
        [settings.CONTACT_EMAIL], fail_silently=False)


# ---------- Project App ---------- #

def email_signature():
    """
    Gets the signature for the emails
    """
    signature = ("Regards,\n\n"
        "The PhysioNet Team,\n"
        "MIT Laboratory for Computational Physiology,\n"
        "Institute for Medical Engineering and Science,\n"
        "45 Carleton St, Cambridge, MA 02142"
        )

    return signature

def email_project_info(project):
    """
    Header for the email. e.g. Project ID, Project title, Submitting Author.
    """
    header = ("Project title: {}\n"
        "Submission ID: {}\n"
        "Submitting author: {}"
        ).format(project.title, project.slug, project.submitting_author())

    return header

def email_footer():
    """
    Footer for the email. e.g. for privacy policy, link to update profile, etc.
    """
    footer = ""

    return footer

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
                     'domain':get_current_site(request),
                     'signature':email_signature(),
                     'project_info':email_project_info(project),
                     'footer':email_footer(),
                     'target_email':target_email}

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
        'response':response, 'signature':email_signature(),
        'project_info':email_project_info(project),'footer':email_footer()}

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
    email_context = {'project':project, 'signature':email_signature(),
        'project_info':email_project_info(project),'footer':email_footer()}

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
    email_context = {'project':project, 'signature':email_signature(),
        'project_info':email_project_info(project),'footer':email_footer()}

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
             'editor':project.editor,
             'signature':email_signature(),
             'project_info':email_project_info(project),
             'footer':email_footer()})

        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)

def editor_notify_new_project(project, assignee):
    """
    Notify authors when an editor is assigned
    """
    subject = 'Assigned new project to review as editor ({0})'.format(
        project.title)

    body = loader.render_to_string(
        'notification/email/editor_notify_new_project.html',
        {'project':project, 'editor':project.editor,
         'signature':email_signature(),
         'user':assignee.get_full_name(),
         'project_info':email_project_info(project),
         'footer':email_footer()})

    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [project.editor.email], fail_silently=False)

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
             'domain':get_current_site(request),
             'signature':email_signature(),
             'project_info':email_project_info(project),
             'footer':email_footer()})

        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def copyedit_complete_notify(request, project, copyedit_log):
    """
    Notify authors when the editor has finished copyediting
    """
    subject = 'Your approval needed to publish: {0}'.format(project.title)

    for email, name in project.author_contact_info():
        body = loader.render_to_string(
            'notification/email/copyedit_complete_notify.html',
            {'name':name, 'project':project, 'copyedit_log':copyedit_log,
             'domain':get_current_site(request),
             'signature':email_signature(),
             'project_info':email_project_info(project),
             'footer':email_footer()})

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
             'domain':get_current_site(request),
             'signature':email_signature(),
             'project_info':email_project_info(project),
             'footer':email_footer()})

        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)

def authors_approved_notify(request, project):
    """
    Notify ...
    """
    subject = 'All authors approved publication of project: {0}'.format(
        project.title)

    for email, name in project.author_contact_info():
        body = loader.render_to_string(
            'notification/email/authors_approved_notify.html',
            {'name':name, 'project':project,
             'domain':get_current_site(request),
             'signature':email_signature(),
             'project_info':email_project_info(project),
             'footer':email_footer()})

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
             'domain':get_current_site(request),
             'signature':email_signature(),
             'project_info':email_project_info(published_project),
             'footer':email_footer()})

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
         'response_message':storage_request.response_message,
         'signature':email_signature(),
         'project_info':email_project_info(project),
         'footer':email_footer()})

    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [email], fail_silently=False)

def contact_reference(request, application):
    """
    Request verification from a credentialing applicant's reference
    """
    applicant_name = ' '.join([application.first_names, application.last_name])
    subject = 'Please verify {} for PhysioNet credentialing'.format(
        applicant_name)
    body = loader.render_to_string('notification/email/contact_reference.html',
        {'application':application, 'applicant_name':applicant_name,
         'domain':get_current_site(request),
         'signature':email_signature(),
         'footer':email_footer()})

    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [application.reference_email], fail_silently=False)

def contact_supervisor(request, application):
    """
    Request verification from a credentialing applicant's reference
    """
    applicant_name = ' '.join([application.first_names, application.last_name])
    subject = 'Please verify {} for PhysioNet credentialing'.format(
        applicant_name)
    body = loader.render_to_string('notification/email/contact_supervisor.html',
        {'application':application, 'applicant_name':applicant_name,
         'domain':get_current_site(request),
         'signature':email_signature(),
         'footer':email_footer()})

    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [application.reference_email], fail_silently=False)

def mailto_reference(request, application):
    """
    Request verification from a credentialing applicant's reference
    """
    applicant_name = application.get_full_name()
    subject = '{} -- PhysioNet clinical database access request'.format(
        applicant_name)
    body = loader.render_to_string('notification/email/mailto_contact_reference.html',
        {'application':application, 'applicant_name':applicant_name,
         'domain':get_current_site(request),
         'signature':email_signature(),
         'footer':email_footer()})

    mailto = "mailto:{3}%3C{0}%3E?subject={1}&bcc=credential-reference+{4}@alpha.physionet.org&body={2}".format(application.reference_email,
      parse.quote(subject), parse.quote(body), parse.quote('"'+application.reference_name+'"'), application.id)
    return mailto

def mailto_supervisor(request, application):
    """
    Request verification from a credentialing applicant's reference
    """
    applicant_name = application.get_full_name()
    subject = '{} -- PhysioNet clinical database access request'.format(
        applicant_name)
    body = loader.render_to_string('notification/email/mailto_contact_supervisor.html',
        {'application':application, 'applicant_name':applicant_name,
         'domain':get_current_site(request),
         'signature':email_signature(),
         'footer':email_footer()})

    mailto = "mailto:{3}%3C{0}%3E?subject={1}&bcc=credential-reference+{4}@alpha.physionet.org&body={2}".format(application.reference_email,
      parse.quote(subject), parse.quote(body), parse.quote('"'+application.reference_name+'"'), application.id)
    return mailto


def mailto_process_credential_complete(request, application, comments=True):
    """
    Notify user of credentialing decision
    """
    applicant_name = application.get_full_name()
    subject = 'PhysioNet clinical database access request for {}'.format(applicant_name)
    body = loader.render_to_string('notification/email/mailto_contact_applicant.html',
        {'application':application, 'applicant_name':applicant_name,
         'domain':get_current_site(request),
         'signature':email_signature()}).replace('\n','\n> ')

    if comments:
        body = 'Dear {0},\n\n{1}\n\n{2}'.format(application.first_names, 
          application.responder_comments, body)
    else:
        body = 'Dear {0},\n\n{1}'.format(application.first_names, body)
    mailto = "mailto:{3}%3C{0}%3E?subject={1}&bcc=credential-reference+{4}@alpha.physionet.org&body={2}".format(application.reference_email,
      parse.quote(subject), parse.quote(body), parse.quote('"'+application.get_full_name()+'"'), application.id)
    return mailto

def mailto_administrators(project, error):
    """
    Request verification from a credentialing applicant's reference
    """
    subject = 'Error sending files to GCP for {}'.format(project.slug)
    body = loader.render_to_string('notification/email/contact_administrators.html',
        {'project':project, 'error':error,
         'signature':email_signature(),
         'footer':email_footer()})

    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [settings.CONTACT_EMAIL], fail_silently=False)

def process_credential_complete(request, application, comments=True):
    """
    Notify user of credentialing decision
    """
    applicant_name = application.get_full_name()
    response = 'rejected' if application.status == 1 else 'accepted'
    subject = 'Your application for PhysioNet credentialing'
    body = loader.render_to_string('notification/email/process_credential_complete.html',
        {'application':application, 'applicant_name':applicant_name,
         'domain':get_current_site(request), 'comments':comments,
         'signature':email_signature(),
         'footer':email_footer()})

    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [application.user.email], fail_silently=False)

def credential_application_request(request, application):
    """
    Notify user of credentialing decision
    """
    applicant_name = application.get_full_name()
    subject = 'PhysioNet credentialing application notification'
    body = loader.render_to_string('notification/email/notify_credential_request.html',
        {'application':application, 'applicant_name':applicant_name,
         'domain':get_current_site(request),
         'signature':email_signature(),
         'footer':email_footer()})

    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [application.user.email], fail_silently=False)
