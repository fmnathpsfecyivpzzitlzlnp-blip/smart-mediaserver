from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Позволяет в шаблоне писать: dictionary|get_item:key
    Нужно, чтобы достать прогресс конкретного файла по его ID.
    """
    return dictionary.get(key)