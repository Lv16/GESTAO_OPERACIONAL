from django import template

register = template.Library()


@register.simple_tag
def paginate_range(page_obj):
    """Return a compact page range list with '...' where pages are omitted.

    Behavior:
    - If total pages <= 5: return full range.
    - If current page is 1..3: show 1,2,3,'...',last
    - If current page is within last 3 pages: show 1,'...',last-2,last-1,last
    - Otherwise (middle): show 1,'...', current-1,current,current+1,'...',last

    Usage in template: {% paginate_range servicos as pages %}
    """
    try:
        num = page_obj.paginator.num_pages
        current = page_obj.number
    except Exception:
        return []

    # If very small number of pages, return full range (<=4)
    # We intentionally compress sequences of length 5+ to show the '...' after 3
    if num <= 4:
        return list(range(1, num + 1))

    pages = []

    # If current is near the left (1..3): show 1,2,3,...,last
    if current <= 3:
        pages.extend([1, 2, 3, '...', num])
        return pages

    # If current is near the right (last-2 .. last): show 1, ..., last-2, last-1, last
    if current >= num - 2:
        pages.extend([1, '...', num - 2, num - 1, num])
        return pages

    # Middle case: show 1, ..., current-1, current, current+1, ..., last
    pages.append(1)
    pages.append('...')
    pages.extend([current - 1, current, current + 1])
    pages.append('...')
    pages.append(num)
    return pages
