import json
import socketserver
import threading


class FakeHook:
    def __init__(self, responder):
        self.requests = []
        self.responder = responder
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for line in self.rfile:
                    request = json.loads(line)
                    owner.requests.append(request)
                    self.wfile.write(json.dumps(owner.responder(request)).encode() + b"\n")

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
