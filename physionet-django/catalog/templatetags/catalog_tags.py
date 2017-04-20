from django import template

register = template.Library()

# The dictionary item filter
@register.filter
def dict_item(dictionary, key):
    return dictionary.get(key)

# Return appropriate button html for access
@register.filter
def access_button(accesscode):

    if accesscode == 0:
        buttonhtml = "<button type=\"button\" class=\"btn btn-danger\">Protected Access</button>"
    elif accesscode == 1:
        buttonhtml = "<button type=\"button\" class=\"btn btn-success\">Open Access</button>"

    return buttonhtml

# Return the html string list of contributors
@register.filter
def contributorstring(contributors):

    #cnames = [c.name for c in contributors]
    #cinstitutions = [c.institution for c in contributors]

    contributorstring = ''

    for i in range(0, contributors.count()):
        #contributorstring = constributorstring+"<span title=\""+cinstitutions[i]+"\">hover me</span>"
        contributorstring = contributorstring+"<span title=\""+contributors[i].institution+"\">"+contributors[i].name+"</span>, "

    contributorstring = contributorstring[:-2]

    return contributorstring