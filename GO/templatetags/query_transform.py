from django import template

register = template.Library()

def query_transform(request_get, exclude_keys=None):
    """
    Retorna a query string apenas com os parâmetros preenchidos e sem os campos em exclude_keys.
    """
    if exclude_keys is None:
        exclude_keys = []
    query = request_get.copy()
    for key in list(query.keys()):
        if not query[key] or key in exclude_keys:
            query.pop(key)
    return query.urlencode()

register.filter('query_transform', query_transform)
