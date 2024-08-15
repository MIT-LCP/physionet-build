import logging

from django.db import migrations

LOGGER = logging.getLogger(__name__)


def try_fix_refs(new_project, new_refs_list, old_project, old_refs_list):
    # We assume any reference with order=None must have been created
    # by a buggy version of NewProjectVersionForm.
    #
    # If
    # - all of the refs in old_refs_list are present in new_refs_list,
    # - and all of those old refs have distinct order,
    # - and all of those new refs have order = None,
    # - and all other refs in new_refs_list have order > len(old_refs_list),
    # then assume those references were meant to be copied without
    # changing the order.
    #
    # If any old refs were edited or removed after the new project was
    # created, then these criteria don't apply.

    old_ref_by_desc = {ref.description: ref for ref in old_refs_list}
    new_ref_by_desc = {ref.description: ref for ref in new_refs_list}

    old_ref_order = set()
    for old_ref in old_refs_list:
        old_ref_order.add(old_ref.order)
        new_ref = new_ref_by_desc.get(old_ref.description)
        if not new_ref or new_ref.order is not None:
            return

    if (None in old_ref_order
            or len(old_ref_order) != len(old_refs_list)
            or len(old_ref_by_desc) != len(old_refs_list)
            or len(new_ref_by_desc) != len(new_refs_list)):
        return

    new_refs_to_fix = []
    for new_ref in new_refs_list:
        if new_ref.order is None:
            if new_ref.description not in old_ref_by_desc:
                return
            new_refs_to_fix.append(new_ref)
        if new_ref.order is not None and new_ref.order <= len(old_refs_list):
            return

    n = len(new_refs_to_fix)
    if n == 0:
        return

    LOGGER.info("correcting %s references in %s-%s by copying from %s-%s",
                n, new_project.slug, new_project.version,
                old_project.slug, old_project.version)

    # Update 'description' (and 'url', if relevant) of existing
    # reference objects - don't just update the 'order'.  We want
    # 'order' to be monotonically increasing with 'id', because 'id'
    # is the sorting key used by formsets.  Also, set the new 'order'
    # to 'i + 1', rather than 'old_ref.order', because the old refs
    # might have gaps in the sequence.

    model = type(new_refs_to_fix[0])
    fields = ['description', 'order']
    if hasattr(model, 'url'):
        fields += ['url']

    for i, new_ref in enumerate(new_refs_to_fix):
        old_ref = old_refs_list[i]
        new_ref.description = old_ref.description
        new_ref.url = old_ref.url
        new_ref.order = i + 1

    model.objects.bulk_update(new_refs_to_fix, fields)


def migrate_forward(apps, schema_editor):
    ActiveProject = apps.get_model('project', 'ActiveProject')
    PublishedProject = apps.get_model('project', 'PublishedProject')
    Reference = apps.get_model('project', 'Reference')
    PublishedReference = apps.get_model('project', 'PublishedReference')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    ap_ct = ContentType.objects.get_for_model(ActiveProject)

    prev_pp = None
    for pp in PublishedProject.objects.order_by('slug', 'publish_datetime'):
        pr = list(PublishedReference.objects
                  .filter(project=pp)
                  .order_by('order', 'id'))

        if prev_pp and prev_pp.slug == pp.slug:
            # Try to repair published project based on the previous
            # published version.
            prev_pr = list(PublishedReference.objects
                           .filter(project=prev_pp)
                           .order_by('order', 'id'))
            try_fix_refs(pp, pr, prev_pp, prev_pr)

        if pp.is_latest_version:
            cp = pp.core_project
            # Try to repair all active projects based on the "latest"
            # published version.
            for ap in ActiveProject.objects.filter(core_project=cp):
                ar = list(Reference.objects
                          .filter(content_type=ap_ct, object_id=ap.id)
                          .order_by('id'))
                try_fix_refs(ap, ar, pp, pr)

        prev_pp = pp


def migrate_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("project", "0076_internalnote"),
    ]

    operations = [
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
