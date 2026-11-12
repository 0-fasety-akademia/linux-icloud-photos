import sys, os, threading, re, subprocess
sys.path.insert(0, os.environ["PROJECT_ROOT"])
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import requests
import backend

DATA = open(os.path.join(os.environ["TEST_TMP"], "test.ogv"),"rb").read()

class Apple(BaseHTTPRequestHandler):      # udaje CDN: obsługuje Range
    protocol_version="HTTP/1.1"
    def log_message(self,*a): pass
    def do_GET(self):
        rng=self.headers.get("Range")
        if rng:
            m=re.match(r"bytes=(\d+)-(\d*)",rng); a=int(m.group(1)); b=int(m.group(2) or len(DATA)-1); b=min(b,len(DATA)-1)
            body=DATA[a:b+1]; self.send_response(206); self.send_header("Content-Range",f"bytes {a}-{b}/{len(DATA)}")
        else:
            body=DATA; self.send_response(200)
        self.send_header("Content-Type","video/ogg"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
srv=ThreadingHTTPServer(("127.0.0.1",0),Apple); threading.Thread(target=srv.serve_forever,daemon=True).start()
base=f"http://127.0.0.1:{srv.server_address[1]}/v.ogv"

class Asset:
    def __init__(s, video, versions): s.id="x"; s.filename="a.MOV" if video else "a.HEIC"; s.item_type="movie" if video else "image"; s._v=versions
    @property
    def versions(s): return {k:{} for k in s._v}
    def download_url(s, v): return base if v in s._v else None
    def download(s, v): return b"JPEG-"+v.encode() if v in s._v else None

class Api: session=requests.Session()
ic=backend.ICloud(); ic.api=Api()

# 1) miniatury filmów: musi wybrać *_image, nie "thumb" (wideo)
mv=Asset(True,{"original":1,"medium":1,"thumb":1,"thumb_image":1,"medium_image":1})
print("film thumb ->", ic.fetch(mv,"thumb")); print("film medium ->", ic.fetch(mv,"medium"))
ph=Asset(False,{"original":1,"medium":1,"thumb":1})
print("zdjęcie thumb ->", ic.fetch(ph,"thumb")); print("zdjęcie medium ->", ic.fetch(ph,"medium"))
try: ic.fetch(Asset(True,{"original":1,"medium":1,"thumb":1}),"thumb"); print("BŁĄD: powinien rzucić")
except LookupError: print("film bez obrazków -> LookupError (OK, kafelek dostanie ikonę)")

# 2) proxy: Range + pełne
url=ic.stream_url(Asset(True,{"original":1,"medium":1}),"medium")
r=requests.get(url,headers={"Range":"bytes=0-99"}); print("range:",r.status_code,len(r.content),r.headers.get("Content-Range"))
r=requests.get(url); print("full:",r.status_code,len(r.content),"==",len(DATA),r.content==DATA)
r=requests.get(url.rsplit("/",1)[0]+"/zly"); print("zły token:",r.status_code)
# 3) GStreamer przez proxy (seek wymaga Range)
p=subprocess.run(["gst-launch-1.0","-q","playbin",f"uri={url}","video-sink=fakesink","audio-sink=fakesink"],capture_output=True,text=True,timeout=30)
print("gst playbin przez proxy rc=",p.returncode,p.stderr.strip()[:200])
print("log:", open(backend.DEBUG_LOG).read().strip().splitlines()[-2:])
