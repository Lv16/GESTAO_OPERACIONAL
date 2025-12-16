from django import template

register = template.Library()


@register.simple_tag
def paginate_range(page_obj, left_edge=2, left_current=1, right_current=1, right_edge=2):
    """Return a compact page range list with '...' where pages are omitted.

    Usage in template: {% paginate_range servicos as pages %}
    """
    try:
        num = page_obj.paginator.num_pages
        current = page_obj.number
    except Exception:
        return []

    left_edge = int(left_edge)
    left_current = int(left_current)
    right_current = int(right_current)
    right_edge = int(right_edge)

    # If small number of pages, return full range
    if num <= (left_edge + left_current + right_current + right_edge + 3):
        return list(range(1, num + 1))

    result = []

    def add_range(a, b):
        for i in range(a, b + 1):
            result.append(i)

    # left edge
    add_range(1, left_edge)

    # left ellipsis
    if current - left_current - 1 > left_edge:
        result.append('...')

    # middle range around current
    start = max(left_edge + 1, current - left_current)
    end = min(num - right_edge, current + right_current)
    add_range(start, end)

    # right ellipsis
    if num - right_edge - end > 0:
        result.append('...')

    # right edge
    add_range(num - right_edge + 1, num)

    return result
