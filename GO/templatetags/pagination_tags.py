from django import template

register = template.Library()

@register.simple_tag
def paginate_range(page_obj):
    try:
        num = page_obj.paginator.num_pages
        current = page_obj.number
    except Exception:
        return []

    if num <= 4:
        return list(range(1, num + 1))

    pages = []

    if current <= 3:
        pages.extend([1, 2, 3, '...', num])
        return pages

    if current >= num - 2:
        pages.extend([1, '...', num - 2, num - 1, num])
        return pages

    pages.append(1)
    pages.append('...')
    pages.extend([current - 1, current, current + 1])
    pages.append('...')
    pages.append(num)
    return pages