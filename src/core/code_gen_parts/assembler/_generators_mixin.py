"""CodeAssembler - Code Generation Mixin."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.code_gen_parts.assembler")


class AssemblerGeneratorsMixin:
    """Mixin providing code generation methods for _process()."""

    # ================================================================
    #  CODE GENERATION — REAL LOGIC, NOT STUBS
    # ================================================================

    def _build_crud_process(self, entity_name: str, table_name: str,
                            fields: List[Dict]) -> str:
        """Generate a REAL _process() method with CRUD operations.

        Uses sqlite3 directly (stdlib) instead of async DatabaseExecutor,
        so the generated code is standalone, synchronous, and actually runs.
        """
        field_names = [f.get("name", "field") for f in fields]
        param_str = ", ".join('"%s"' % f for f in field_names)
        search_col = field_names[0] if field_names else "name"

        # Validate table_name at generation time to prevent injection in generated SQL
        import re as _gen_re
        if not _gen_re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
            raise ValueError(f"Invalid table name for code generation: {table_name!r}")
        for fn in field_names:
            if not _gen_re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', fn):
                raise ValueError(f"Invalid field name for code generation: {fn!r}")

        # Use string formatting (not f-string) to avoid nested brace issues
        return '''
    def _process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """CRUD operations for {entity} — REAL logic using sqlite3."""
        import sqlite3
        import re as _sql_re
        _SAFE_ID = _sql_re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
        action = payload.get("action", "list")
        db_path = payload.get("db_path", "{table}.sqlite")

        if action == "create":
            data = payload.get("data", {{}})
            columns = [{params}]
            values = [data.get(col) for col in columns]
            placeholders = ", ".join(["?" for _ in columns])
            col_str = ", ".join(columns)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "INSERT INTO {table} (" + col_str + ") VALUES (" + placeholders + ")",
                    values
                )
                conn.commit()
                last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            finally:
                conn.close()
            return {{"success": True, "action": "create", "entity": "{entity}", "id": last_id}}

        elif action == "read":
            item_id = payload.get("id")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(
                    "SELECT * FROM {table} WHERE id = ?", (item_id,)
                )
                row = dict(cursor.fetchone()) if cursor.fetchone() else None
            finally:
                conn.close()
            return {{"success": True, "data": row, "entity": "{entity}"}}

        elif action == "update":
            item_id = payload.get("id")
            data = payload.get("data", {{}})
            if not data:
                return {{"success": False, "error": "No data provided for update"}}
            # SECURITY: Validate all column names from user input before SQL interpolation
            for k in data.keys():
                if not _SAFE_ID.match(str(k)):
                    return {{"success": False, "error": f"Invalid column name: {{k!r}}"}}
            set_parts = [str(k) + " = ?" for k in data.keys()]
            set_clause = ", ".join(set_parts)
            values = list(data.values()) + [item_id]
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "UPDATE {table} SET " + set_clause + " WHERE id = ?", values
                )
                conn.commit()
                affected = conn.execute("SELECT changes()").fetchone()[0]
            finally:
                conn.close()
            return {{"success": True, "action": "update", "entity": "{entity}", "affected": affected}}

        elif action == "delete":
            item_id = payload.get("id")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "DELETE FROM {table} WHERE id = ?", (item_id,)
                )
                conn.commit()
                affected = conn.execute("SELECT changes()").fetchone()[0]
            finally:
                conn.close()
            return {{"success": True, "action": "delete", "entity": "{entity}", "affected": affected}}

        elif action == "list":
            limit = payload.get("limit", 50)
            offset = payload.get("offset", 0)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(
                    "SELECT * FROM {table} LIMIT ? OFFSET ?", (limit, offset)
                )
                rows = [dict(r) for r in cursor.fetchall()]
            finally:
                conn.close()
            return {{"success": True, "data": rows, "entity": "{entity}", "count": len(rows)}}

        elif action == "search":
            query = payload.get("query", "")
            column = payload.get("search_column", "{search_col}")
            # SECURITY: Validate column name from user input before SQL interpolation
            if not _SAFE_ID.match(str(column)):
                return {{"success": False, "error": f"Invalid column name: {{column!r}}"}}
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(
                    "SELECT * FROM {table} WHERE " + column + " LIKE ?", ("%" + query + "%",)
                )
                rows = [dict(r) for r in cursor.fetchall()]
            finally:
                conn.close()
            return {{"success": True, "data": rows, "entity": "{entity}", "count": len(rows)}}

        elif action == "count":
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute("SELECT COUNT(*) as total FROM {table}")
                total = cursor.fetchone()[0]
            finally:
                conn.close()
            return {{"success": True, "total": total, "entity": "{entity}"}}

        return {{"success": False, "error": "Unknown action: " + str(action)}}
'''.format(entity=entity_name, table=table_name, params=param_str, search_col=search_col)

    def _build_analytics_process(self, entity_name: str, table_name: str,
                                  fields: List[Dict]) -> str:
        """Generate a REAL _process() method with analytics logic.

        Uses sqlite3 directly (stdlib) instead of async DatabaseExecutor,
        so the generated code is standalone, synchronous, and actually runs.
        """
        numeric_fields = [f for f in fields
                         if f.get("type", "").lower() in ("float", "int", "integer", "number", "decimal")]
        num_names = [f.get("name", "count") for f in numeric_fields] or ["count"]
        default_metric = num_names[0]

        # Validate table_name and metric at generation time to prevent injection
        import re as _gen_re
        if not _gen_re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
            raise ValueError(f"Invalid table name for code generation: {table_name!r}")
        if not _gen_re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', default_metric):
            raise ValueError(f"Invalid metric name for code generation: {default_metric!r}")

        # Use .format() to avoid nested f-string brace issues
        return '''
    def _process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Analytics for {entity} — REAL aggregation using sqlite3."""
        import sqlite3
        import re as _sql_re
        _SAFE_ID = _sql_re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
        action = payload.get("action", "summary")
        db_path = payload.get("db_path", "{table}.sqlite")

        if action == "summary":
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute("SELECT COUNT(*) as total, AVG({metric}) as avg_{metric} FROM {table}")
                row = dict(cursor.fetchone()) if cursor.fetchone() else {{}}
            finally:
                conn.close()
            return {{"success": True, "summary": row, "entity": "{entity}"}}

        elif action == "aggregate":
            metric = payload.get("metric", "{metric}")
            # SECURITY: Validate metric name from user input before SQL interpolation
            if not _SAFE_ID.match(str(metric)):
                return {{"success": False, "error": f"Invalid metric name: {{metric!r}}"}}
            period = payload.get("period", "daily")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(
                    "SELECT date(created_at) as period, " + metric + " FROM {table} GROUP BY period ORDER BY period"
                )
                rows = [dict(r) for r in cursor.fetchall()]
            finally:
                conn.close()
            return {{"success": True, "data": rows, "metric": metric, "entity": "{entity}"}}

        elif action == "distribution":
            column = payload.get("column", "status")
            # SECURITY: Validate column name from user input before SQL interpolation
            if not _SAFE_ID.match(str(column)):
                return {{"success": False, "error": f"Invalid column name: {{column!r}}"}}
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(
                    "SELECT " + column + ", COUNT(*) as count FROM {table} GROUP BY " + column
                )
                rows = [dict(r) for r in cursor.fetchall()]
            finally:
                conn.close()
            return {{"success": True, "distribution": rows, "entity": "{entity}"}}

        elif action == "trend":
            metric = payload.get("metric", "{metric}")
            # SECURITY: Validate metric name from user input before SQL interpolation
            if not _SAFE_ID.match(str(metric)):
                return {{"success": False, "error": f"Invalid metric name: {{metric!r}}"}}
            days = payload.get("days", 30)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(
                    "SELECT date(created_at) as day, SUM(" + metric + ") as total "
                    "FROM {table} WHERE created_at >= date('now', '-' || ? || ' days') "
                    "GROUP BY day ORDER BY day", (days,)
                )
                rows = [dict(r) for r in cursor.fetchall()]
            finally:
                conn.close()
            return {{"success": True, "trend": rows, "metric": metric, "entity": "{entity}"}}

        return {{"success": False, "error": "Unknown analytics action: " + str(action)}}
'''.format(entity=entity_name, table=table_name, metric=default_metric)

    def _build_notification_process(self, entity_name: str, fields: List[Dict]) -> str:
        """Generate a REAL _process() method for notifications.

        Uses smtplib directly (stdlib) instead of async NotificationExecutor,
        so the generated code is standalone, synchronous, and actually runs.
        """
        # Use .format() to avoid nested f-string brace issues
        return '''
    def _process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Notification for {entity} — REAL sending via smtplib."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        action = payload.get("action", "send")

        if action == "send":
            channel = payload.get("channel", "email")
            message = payload.get("message", "")
            recipient = payload.get("recipient", "")
            subject = payload.get("subject", "Notification from {entity}")
            smtp_host = payload.get("smtp_host", "localhost")
            smtp_port = payload.get("smtp_port", 587)
            smtp_user = payload.get("smtp_user", "")
            smtp_pass = payload.get("smtp_pass", "")

            if channel == "email" and recipient:
                msg = MIMEMultipart()
                msg["From"] = smtp_user or "noreply@{entity}.local"
                msg["To"] = recipient
                msg["Subject"] = subject
                msg.attach(MIMEText(message, "plain"))
                try:
                    server = smtplib.SMTP(smtp_host, smtp_port)
                    if smtp_user:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                    server.quit()
                    return {{"success": True, "channel": "email", "recipient": recipient, "entity": "{entity}"}}
                except Exception as e:
                    return {{"success": False, "error": str(e), "entity": "{entity}"}}
            return {{"success": True, "channel": channel, "message": "logged", "entity": "{entity}"}}

        elif action == "broadcast":
            recipients = payload.get("recipients", [])
            message = payload.get("message", "")
            subject = payload.get("subject", "Broadcast from {entity}")
            smtp_host = payload.get("smtp_host", "localhost")
            smtp_port = payload.get("smtp_port", 587)
            smtp_user = payload.get("smtp_user", "")
            smtp_pass = payload.get("smtp_pass", "")
            results = []
            for r in recipients:
                try:
                    msg = MIMEMultipart()
                    msg["From"] = smtp_user or "noreply@{entity}.local"
                    msg["To"] = r
                    msg["Subject"] = subject
                    msg.attach(MIMEText(message, "plain"))
                    server = smtplib.SMTP(smtp_host, smtp_port)
                    if smtp_user:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                    server.quit()
                    results.append({{"recipient": r, "success": True}})
                except Exception as e:
                    results.append({{"recipient": r, "success": False, "error": str(e)}})
            return {{"success": True, "results": results, "entity": "{entity}"}}

        elif action == "log":
            import logging
            _logger = logging.getLogger("{entity}")
            level = payload.get("level", "info")
            message = payload.get("message", "")
            getattr(_logger, level, _logger.info)(message)
            return {{"success": True, "action": "log", "entity": "{entity}"}}

        return {{"success": False, "error": "Unknown notification action: " + str(action)}}
'''.format(entity=entity_name)
