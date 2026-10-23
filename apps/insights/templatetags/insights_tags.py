from django import template

register = template.Library()


@register.filter
def br_number(value):
    """Format numbers Brazilian style: 21.200 / 3,5."""
    if value is None or value == "":
        return "-"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{int(value):,}".replace(",", ".")


@register.filter
def br_delta(value):
    """Signed percentage change, e.g. +72,7% / -37,1%."""
    if value is None:
        return ""
    sign = "+" if value > 0 else ""
    return f"{sign}{br_number(float(value))}%"
