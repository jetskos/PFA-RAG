#!/usr/bin/env python3
"""Petit proxy HTTPS -> HTTP pour tester la PWA sur un vrai téléphone.

Le service worker et l'installation « écran d'accueil » exigent un contexte
sécurisé (HTTPS, ou localhost). En LAN sur `http://192.168.x.x:8000` ils sont
donc désactivés. Ce script place un HTTPS auto-signé devant `runserver` :

    Terminal 1 :  bash test_local.sh                 (Django sur :8000)
    Terminal 2 :  python serve_https.py              (HTTPS sur :8443)

Puis, sur le téléphone (même Wi-Fi) : https://<IP-du-PC>:8443/
Accepter l'avertissement de certificat (auto-signé) une fois.

Le certificat est généré au premier lancement dans ./.https_dev/ (git-ignoré).
Aucune dépendance en plus : `cryptography` est déjà requis par le projet.
"""
import datetime
import http.server
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request

BACKEND = os.getenv("HTTPS_BACKEND", "http://127.0.0.1:8000")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Laisse le navigateur suivre les 3xx (sinon l'URL affichée se désynchronise)."""
    def redirect_request(self, *a, **k):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)
PORT = int(os.getenv("HTTPS_PORT", "8443"))
CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".https_dev")
CERT = os.path.join(CERT_DIR, "cert.pem")
KEY = os.path.join(CERT_DIR, "key.pem")


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def ensure_cert():
    if os.path.exists(CERT) and os.path.exists(KEY):
        return
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    os.makedirs(CERT_DIR, exist_ok=True)
    ip = lan_ip()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EduTech dev")])
    alt = x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
        x509.IPAddress(__import__("ipaddress").ip_address(ip)),
    ])
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(alt, critical=False)
        .sign(key, hashes.SHA256())
    )
    with open(KEY, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.TraditionalOpenSSL,
                                 serialization.NoEncryption()))
    with open(CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("Certificat auto-signé généré dans", CERT_DIR)


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self):
        body = None
        if "Content-Length" in self.headers:
            body = self.rfile.read(int(self.headers["Content-Length"]))
        url = BACKEND + self.path
        req = urllib.request.Request(url, data=body, method=self.command)
        for k, v in self.headers.items():
            if k.lower() not in ("host", "connection"):
                req.add_header(k, v)
        req.add_header("X-Forwarded-Proto", "https")
        req.add_header("Host", self.headers.get("Host", ""))
        try:
            with _OPENER.open(req, timeout=60) as resp:
                data = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:  # backend down
            msg = ("502 — le backend Django ({}) ne répond pas.\n"
                   "Lance d'abord : bash test_local.sh\n{}".format(BACKEND, exc)).encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _proxy

    def log_message(self, fmt, *args):
        sys.stdout.write("  %s %s\n" % (self.command, self.path))


def main():
    ensure_cert()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, KEY)
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), ProxyHandler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    ip = lan_ip()
    print("\n" + "=" * 63)
    print("  HTTPS  ->  " + BACKEND)
    print("  Sur ce PC     : https://localhost:%d/" % PORT)
    print("  Sur téléphone : https://%s:%d/   (accepter le certificat)" % (ip, PORT))
    print("=" * 63 + "\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    main()
