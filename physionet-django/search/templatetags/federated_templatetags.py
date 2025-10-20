from django import template

register = template.Library()


@register.filter(name='site_badge')
def site_badge(site_display_name):
    """Display badge for federated site"""
    return f'<span class="badge badge-info"><i class="fas fa-globe"></i> {site_display_name}</span>'
