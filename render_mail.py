from jinja2 import Template
from gktoday_fetch import SECTION_ORDER

TEMPLATE = Template("""
<html>
<body style="font-family: Arial, sans-serif; max-width: 640px; margin: auto; color:#222;">
  <h1 style="color:#1a3c6e; margin-bottom:0;">SSC CGL Current Affairs</h1>
  <p style="color:#666; margin-top:4px;">{{ today }} &middot; Source: GKToday</p>

  {% for key, heading in sections %}
    {% if grouped.get(key) %}
      <h2 style="border-bottom:2px solid #1a3c6e; padding-bottom:4px; margin-top:28px;">{{ heading }}</h2>
      <ul style="padding-left:18px;">
        {% for item in grouped[key] %}
          <li style="margin-bottom:12px;">
            <a href="{{ item.url }}" style="color:#1a3c6e; font-weight:bold; text-decoration:none;">{{ item.title }}</a>
            <br>
            <span style="color:#444; font-size:14px;">{{ item.excerpt }}</span>
          </li>
        {% endfor %}
      </ul>
    {% endif %}
  {% endfor %}

  <p style="color:#999; font-size:12px; margin-top:32px; border-top:1px solid #eee; padding-top:12px;">
    Auto-generated from GKToday's current affairs section. This is Phase 0 (raw digest,
    no dedup or AI filtering yet) — one-liners and MCQs come in a later phase.
  </p>
</body>
</html>
""")


def build_html(items: list[dict], today: str) -> str:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        grouped.setdefault(item["category"], []).append(item)
    return TEMPLATE.render(sections=SECTION_ORDER, grouped=grouped, today=today)