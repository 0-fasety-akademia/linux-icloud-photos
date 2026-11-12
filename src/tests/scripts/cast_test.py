import os
import sys, threading
sys.path.insert(0, os.environ["PROJECT_ROOT"])
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import cast, re
calls=[]
DESC='''<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device><friendlyName>[LG] webOS TV OLED55</friendlyName>
<serviceList><service><serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType><controlURL>/rc</controlURL></service>
<service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType><controlURL>/AVT/ctl</controlURL></service></serviceList></device></root>'''
class H(BaseHTTPRequestHandler):
    def log_message(s,*a): pass
    def do_GET(s):
        b=DESC.encode(); s.send_response(200); s.send_header("Content-Length",str(len(b))); s.end_headers(); s.wfile.write(b)
    def do_POST(s):
        body=s.rfile.read(int(s.headers["Content-Length"])).decode()
        calls.append((s.path, s.headers["SOAPACTION"], body))
        s.send_response(200); s.send_header("Content-Length","0"); s.end_headers()
srv=ThreadingHTTPServer(("127.0.0.1",0),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
loc=f"http://127.0.0.1:{srv.server_address[1]}/desc.xml"
r=cast.from_location(loc); print("renderer:", r, "| control:", r.control_url)
print("ssdp parse:", cast.parse_ssdp_location(b"HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=1800\r\nLOCATION: http://10.0.0.5:1234/d.xml\r\nST: x\r\n\r\n"))
r.play_uri("http://192.168.1.10:5555/tok/photo.jpg?a=1&b=2", "Zdjęcie <test> & co", "image/jpeg", False)
r.stop()
for path, act, body in calls: print(path, act)
print("SetURI zawiera URI (escaped):", "photo.jpg?a=1&amp;b=2" in calls[1][2])
print("DIDL w metadanych (escaped):", "&lt;upnp:class&gt;object.item.imageItem.photo" in calls[1][2], "| protocolInfo:", "http-get:*:image/jpeg:DLNA.ORG_OP" in calls[1][2])
print("tytuł escaped:", "Zdjęcie &amp;lt;test&amp;gt; &amp;amp; co" in calls[1][2])
print("Play: Speed=1:", "<Speed>1</Speed>" in calls[2][2])
import xml.dom.minidom as md
[md.parseString(c[2]) for c in calls]; print("koperty SOAP to poprawny XML")
print("nie-renderer ->", cast.from_location("http://127.0.0.1:9/x"))
