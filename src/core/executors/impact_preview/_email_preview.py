"""ZENIC-AGENTS - Impact Preview Engine: Email Preview Logic

Simulates the effects of email operations WITHOUT sending them.
All operations are strictly READ-ONLY — this module never sends emails.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from ._types import (
    ImpactRiskLevel,
    EmailImpactPreview,
)


def preview_email(config: Dict[str, Any]) -> EmailImpactPreview:
    """Preview an email operation WITHOUT sending it.

    Shows recipients, subject, whether it would actually send.

    Args:
        config: Email config with keys like to, subject, body, html, cc, bcc, etc.

    Returns:
        An EmailImpactPreview with the estimated impact.
    """
    to_emails = config.get("to", [])
    cc = config.get("cc", [])
    bcc = config.get("bcc", [])
    subject = str(config.get("subject", "No Subject"))
    from_email = str(
        config.get("from_email", "")
        or os.environ.get("SMTP_USER", "noreply@zenic-agents.local")
    )
    html = config.get("html", "")
    attachments = config.get("attachments", [])
    host = config.get("host", os.environ.get("SMTP_HOST", ""))

    # Normalize to lists
    if isinstance(to_emails, str):
        to_emails = [to_emails]
    if isinstance(cc, str):
        cc = [cc]
    if isinstance(bcc, str):
        bcc = [bcc]
    if not isinstance(attachments, list):
        attachments = [attachments] if attachments else []

    # Validate email addresses
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    all_recipients = list(to_emails) + list(cc) + list(bcc)
    invalid = [e for e in all_recipients if not email_pattern.match(str(e))]

    would_send = bool(host) and len(invalid) == 0 and len(to_emails) > 0

    # Determine risk
    subject_lower = subject.lower()
    body_lower = str(config.get("body", "")).lower()
    combined = subject_lower + " " + body_lower
    financial_keywords = (
        "invoice", "factura", "payment", "pago",
        "refund", "reembolso", "charge", "cobro",
    )
    is_financial = any(kw in combined for kw in financial_keywords)

    risk_level = ImpactRiskLevel.LOW
    risk_score = 0.2
    if is_financial:
        risk_level = ImpactRiskLevel.HIGH
        risk_score = 0.7
    elif len(bcc) > 0:
        risk_level = ImpactRiskLevel.MEDIUM
        risk_score = 0.4

    summary_parts: List[str] = []
    if would_send:
        summary_parts.append(f"Would send email to {len(to_emails)} recipient(s)")
    else:
        summary_parts.append("Would NOT send (SMTP not configured or invalid recipients)")
    if cc:
        summary_parts.append(f"{len(cc)} CC")
    if bcc:
        summary_parts.append(f"{len(bcc)} BCC")
    summary = "; ".join(summary_parts)

    warnings: List[str] = []
    if invalid:
        warnings.append(f"Invalid email addresses: {invalid}")
    if not to_emails:
        warnings.append("No recipients specified")
    if is_financial:
        warnings.append("Email contains financial keywords — may require approval")

    preview = EmailImpactPreview(
        recipients=list(to_emails),
        cc=list(cc),
        bcc=list(bcc),
        subject=subject,
        from_email=from_email,
        has_html=bool(html),
        has_attachments=len(attachments) > 0,
        attachment_count=len(attachments),
        would_send=would_send,
        invalid_recipients=invalid,
        risk_level=risk_level,
        risk_score=risk_score,
        summary=summary,
        warnings=warnings,
    )
    return preview
