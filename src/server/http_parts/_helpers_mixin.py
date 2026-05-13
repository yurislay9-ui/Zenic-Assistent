"""
CORS and JSON helpers mixin for ZenicHTTPHandler.
"""

from ._imports import json, _cors_origin, _get_cors_origin


class HelpersMixin:
    """CORS and JSON helper methods for ZenicHTTPHandler."""

    def log_message(self, format, *args):
        from ._imports import logger
        logger.info("HTTP: %s", format % args)

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _set_cors_headers(self):
        # Dynamic CORS: return the request's Origin if it matches Open Design
        request_origin = self.headers.get('Origin', '')
        origin = _get_cors_origin(request_origin) if request_origin else _cors_origin
        self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, PATCH, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-API-Key, X-Client')
        # Allow credentials when specific origin is returned (not wildcard)
        if origin != '*':
            self.send_header('Access-Control-Allow-Credentials', 'true')

    def _send_json(self, data, status=200):
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self._set_cors_headers()
            body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        except BrokenPipeError:
            # Client closed the connection before we could respond (e.g. timeout on their end).
            # This is normal and not an error we need to log loudly.
            pass
        except ConnectionResetError:
            # Similar to BrokenPipe — client reset the connection.
            pass
