import os
import threading, re, types, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pyicloud.session import PyiCloudSession
DATA = bytes(range(256)) * 4000
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(s, *a): pass
    def do_GET(s):
        rng = s.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d+)-(\d*)", rng); a = int(m.group(1)); b = int(m.group(2) or len(DATA) - 1)
            body = DATA[a:b + 1]; s.send_response(206); s.send_header("Content-Range", f"bytes {a}-{a+len(body)-1}/{len(DATA)}")
        else:
            body = DATA; s.send_response(200)
        s.send_header("Content-Type", "video/mp4"); s.send_header("Content-Length", str(len(body))); s.end_headers(); s.wfile.write(body)
srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/v.mp4"
class Svc:
    account_name = "a@b.c"; data = {}; params = {}; client_id = "x"; session_data = {}
    def __getattr__(self, n):
        return {} if not n.startswith("_") else None
svc = Svc()
try:
    ses = PyiCloudSession(svc, "cid", os.path.join(os.environ["TEST_TMP"], "sess"))
except Exception as e:
    print("ctor failed:", type(e).__name__, e); raise SystemExit
for label, kw in (("pełne 200", {}), ("Range 206", {"headers": {"Range": "bytes=100-199"}})):
    t = time.time()
    try:
        r = ses.get(url, stream=True, **kw)
        n = sum(len(c) for c in r.iter_content(65536))
        print(f"{label}: status={r.status_code} bytes={n} ({time.time()-t:.2f}s)")
    except Exception as e:
        print(f"{label}: WYJĄTEK {type(e).__name__}: {str(e)[:160]}")
