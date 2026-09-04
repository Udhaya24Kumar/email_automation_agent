from datetime import datetime

from gktoday_fetch import fetch_today_digest
from render_mail import build_html
from send_mail import send_email


def main() -> None:
    items = fetch_today_digest()
    today = datetime.now().strftime("%d %B %Y")

    if not items:
        print("No items fetched — GKToday's page structure may have changed. "
              "Inspect https://www.gktoday.in/current-affairs/ and adjust "
              "the selectors in gktoday_fetch.py.")
        return

    html = build_html(items, today)
    send_email(f"SSC Current Affairs — {today}", html)
    print(f"Sent digest with {len(items)} items.")


if __name__ == "__main__":
    main()