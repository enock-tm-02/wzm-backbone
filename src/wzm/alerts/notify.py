"""Outbound alerts: DMS, 511, email. Placeholders until endpoints are set in .env."""
from wzm.config import get_settings


def send_queue_warning(zone_id: str, queue_miles: float, message: str) -> list[str]:
    s = get_settings()
    sent = []
    if s.dms_api_url and s.dms_api_key:
        # TODO: POST message to the DMS control system for signs upstream of zone_id
        sent.append("dms")
    if s.alert_511_url:
        # TODO: publish to 511
        sent.append("511")
    if s.smtp_url and s.alert_email_to:
        # TODO: send email
        sent.append("email")
    return sent
