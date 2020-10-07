from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/full.xml':
            self.send_response(HTTPStatus.OK)

            self.send_header('Content-type', 'text/xml')
            self.end_headers()

            self.wfile.write(open('full.xml', 'rb').read())

if __name__=="__main__":
    server_address = ('', 8080)
    httpd = ThreadingHTTPServer(server_address, Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        exit(0)