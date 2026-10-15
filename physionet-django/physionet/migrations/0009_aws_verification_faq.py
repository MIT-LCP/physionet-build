from django.db import migrations


AWS_FAQ = '''
<h3 id="aws-verification">Amazon Web Services (AWS)</h3>
<p><strong>Q1: Why do I see "Invalid verification code (incorrect signature)"
when verifying my AWS identity?</strong></p>
<p><strong>A:</strong> This can happen when your AWS account blocks signed S3 requests.
To check, run these commands using the same AWS credentials you used for verification:</p>
<pre><code>aws s3 ls s3://physionet-open/
aws s3 ls s3://physionet-open/ --no-sign-request</code></pre>
<p>If the first command returns <code>AccessDenied</code> and the second one works,
signed requests may be blocked by your account's permissions or organization policies.
Accounts created through the &ldquo;Sign up for AWS (new)&rdquo; flow can be subject
to organization policies managed by AWS that restrict S3 access.
If this applies to your account, you may consider creating a new AWS account through the
&ldquo;Sign up for AWS (advanced)&rdquo; flow.
Please review the
<a href="https://docs.aws.amazon.com/accounts/latest/reference/sign-up-for-aws.html">
differences between the sign-up options</a>
in the AWS documentation.</p>
<p>Once the first command works, generate a new verification command
on the verification page, run it exactly as shown,
and submit the complete output (the full URL, without line breaks) again.</p>
'''


def add_aws_faq(apps, schema_editor):
    Section = apps.get_model('physionet', 'Section')
    sections = Section.objects.using(schema_editor.connection.alias).filter(
        static_page__url='/about/faqs/', title__iexact='Cloud',
    )
    for section in sections:
        if 'id="aws-verification"' not in section.content:
            section.content += AWS_FAQ
            section.save(update_fields=['content'])


def remove_aws_faq(apps, schema_editor):
    Section = apps.get_model('physionet', 'Section')
    sections = Section.objects.using(schema_editor.connection.alias).filter(
        static_page__url='/about/faqs/', title__iexact='Cloud',
    )
    for section in sections:
        if AWS_FAQ in section.content:
            section.content = section.content.replace(AWS_FAQ, '', 1)
            section.save(update_fields=['content'])


class Migration(migrations.Migration):
    dependencies = [
        ('physionet', '0008_frontpagebutton_associated_image_path_and_more'),
    ]

    operations = [migrations.RunPython(add_aws_faq, remove_aws_faq)]
