"""ZENIC-AGENTS - Channel Formatter: Email"""

from __future__ import annotations

def format_email_html(message: ChannelMessage) -> str:
    """Format a ChannelMessage into an HTML email body.

    Builds a styled HTML email with optional title, body,
    field table, and footer.
    """
    parts: List[str] = []

    # Title
    if message.title:
        parts.append(f'<h2 style="color:#1a1a1a;margin:0 0 12px 0;">{html_module.escape(message.title)}</h2>')

    # Subtitle
    if message.subtitle:
        parts.append(f'<p style="color:#666;margin:0 0 8px 0;font-size:14px;">{html_module.escape(message.subtitle)}</p>')

    # Body
    if message.html:
        parts.append(f'<div style="margin:0 0 12px 0;">{sanitize_html(message.html)}</div>')
    elif message.text:
        escaped = html_module.escape(message.text).replace("\n", "<br>")
        parts.append(f'<div style="margin:0 0 12px 0;">{escaped}</div>')

    # Fields table
    if message.fields:
        rows = []
        for f in message.fields[:20]:
            key = html_module.escape(f.get("title", f.get("name", "")))
            val = html_module.escape(str(f.get("value", "")))
            rows.append(f'<tr><td style="padding:6px 12px;font-weight:bold;border-bottom:1px solid #eee;">{key}</td>'
                       f'<td style="padding:6px 12px;border-bottom:1px solid #eee;">{val}</td></tr>')
        parts.append(
            f'<table style="border-collapse:collapse;width:100%;margin:0 0 12px 0;">'
            f'{"".join(rows)}</table>'
        )

    # Image
    if message.image_url:
        alt_text = html_module.escape(message.title or "Image")
        safe_url = html_module.escape(message.image_url, quote=True)
        parts.append(f'<img src="{safe_url}" alt="{alt_text}" style="max-width:100%;margin:0 0 12px 0;" />')

    # Footer
    if message.footer:
        parts.append(f'<p style="color:#999;font-size:12px;margin:12px 0 0 0;">{html_module.escape(message.footer)}</p>')

    body = "\n".join(parts)
    return (
        f'<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">'
        f'{body}</div>'
    )


def format_email_confirmation_html(request: ConfirmationRequest) -> str:
    """Format a confirmation request as an HTML email with action buttons.

    Returns styled HTML with YES/NO/MORE_INFO links.
    """
    button_colors = {
        "yes": "#28a745",
        "no": "#dc3545",
        "more_info": "#6c757d",
    }
    button_labels = {
        "yes": "✅ Confirm",
        "no": "❌ Deny",
        "more_info": "ℹ️ More Info",
    }

    buttons = []
    for option in request.options:
        color = button_colors.get(option, "#007bff")
        label = button_labels.get(option, option.replace("_", " ").title())
        buttons.append(
            f'<a href="#action-{option}" style="display:inline-block;padding:10px 20px;'
            f'background-color:{color};color:white;text-decoration:none;border-radius:4px;'
            f'margin-right:8px;font-weight:bold;">{label}</a>'
        )

    return (
        f'<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">'
        f'<h2 style="color:#1a1a1a;">{html_module.escape(request.title)}</h2>'
        f'<p style="color:#333;">{html_module.escape(request.message)}</p>'
        f'<div style="margin:20px 0;">{"".join(buttons)}</div>'
        f'<p style="color:#999;font-size:12px;">Action ID: {html_module.escape(request.action_id)} | '
        f'Expires in {request.timeout_seconds // 60} minutes</p>'
        f'</div>'
    )


# ──────────────────────────────────────────────────────────────
#  PUSH NOTIFICATION FORMATTING
# ──────────────────────────────────────────────────────────────
