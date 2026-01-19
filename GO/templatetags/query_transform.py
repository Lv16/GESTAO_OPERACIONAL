from django import template

register = template.Library()

def query_transform(request_get, exclude_keys=None):
    if exclude_keys is None:
        exclude_keys = []
    query = request_get.copy()
    for key in list(query.keys()):
        if not query[key] or key in exclude_keys:
            query.pop(key)
    return query.urlencode()

register.filter('query_transform', query_transform)