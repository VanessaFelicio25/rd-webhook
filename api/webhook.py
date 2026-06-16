import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

RD_CLIENT_ID = os.environ["RD_CLIENT_ID"]
RD_CLIENT_SECRET = os.environ["RD_CLIENT_SECRET"]
RD_REFRESH_TOKEN = os.environ["RD_REFRESH_TOKEN"]


def get_access_token() -> str:
    url = "https://api.rd.services/auth/token"
    body = {
        "client_id": RD_CLIENT_ID,
        "client_secret": RD_CLIENT_SECRET,
        "refresh_token": RD_REFRESH_TOKEN,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data["access_token"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise Exception(f"Erro ao renovar token: {e.code} — {detail}")


def format_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def pick_phone(contact: dict):
    for field in ("mobile_phone", "personal_phone", "phone"):
        val = contact.get(field) or ""
        if val:
            return val, field
    return "", "mobile_phone"


def clean_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\s\-]", "", name)
    cleaned = re.sub(r"[\d_]", "", cleaned)
    return " ".join(cleaned.split())


def process_names(first_name: str, last_name: str):
    first_name = clean_name(first_name or "").strip()
    last_name = clean_name(last_name or "").strip()

    if not last_name and first_name:
        parts = first_name.split()
        if len(parts) > 1:
            last_name = parts[-1]
            first_name = " ".join(parts[:-1])
        else:
            last_name = first_name

    full_name = first_name if last_name == first_name else f"{first_name} {last_name}".strip()
    return first_name, last_name, full_name


def extract_contact(body) -> dict:
    if isinstance(body, list) and body:
        body = body[0]
    if "leads" in body and body["leads"]:
        return body["leads"][0]
    if "payload" in body:
        return body["payload"]
    return body


def update_rd_contact(email: str, data: dict, access_token: str):
    url = f"https://api.rd.services/platform/contacts/email:{email}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        method="PATCH",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise Exception(f"RD API {e.code}: {detail}")


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [""])[0]

        if not code:
            self._html("Parâmetro <b>code</b> não encontrado na URL.")
            return

        url = "https://api.rd.services/auth/token"
        body = {
            "client_id": RD_CLIENT_ID,
            "client_secret": RD_CLIENT_SECRET,
            "code": code,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                tokens = json.loads(resp.read())
                refresh = tokens.get("refresh_token", "NÃO ENCONTRADO")
                self._html(
                    f"<h2>Pronto! Copie o Refresh Token abaixo e cole no Vercel como <code>RD_REFRESH_TOKEN</code>:</h2>"
                    f"<p style='background:#f0f0f0;padding:12px;word-break:break-all;font-size:14px'>{refresh}</p>"
                    f"<p>Após salvar no Vercel, faça o Redeploy.</p>"
                )
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            self._html(f"Erro ao trocar o código: {e.code} — {detail}")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))

            print(f"[PAYLOAD] {json.dumps(body)}", file=sys.stderr)

            contact = extract_contact(body)
            email = contact.get("email", "")

            if not email:
                print(f"[ERRO] email ausente. campos: {list(contact.keys())}", file=sys.stderr)
                self._respond(400, {"error": "email ausente"})
                return

            phone_raw, phone_field = pick_phone(contact)

            first_name = contact.get("name") or ""
            custom_fields = contact.get("custom_fields") or {}
            last_name = (
                contact.get("last_name") or
                custom_fields.get("Sobrenome") or
                custom_fields.get("sobrenome") or
                ""
            )

            first_name, last_name, full_name = process_names(first_name, last_name)

            update_data = {"name": full_name}
            if phone_raw:
                update_data[phone_field] = format_phone(phone_raw)

            access_token = get_access_token()
            rd_status = update_rd_contact(email, update_data, access_token)
            print(f"[OK] {email} | nome: {full_name} | {phone_field}: {update_data.get(phone_field)} | status: {rd_status}", file=sys.stderr)

            self._respond(200, {"status": "ok", "name": full_name, "phone": update_data.get(phone_field)})

        except Exception as e:
            print(f"[EXCEPTION] {e}", file=sys.stderr)
            self._respond(500, {"error": str(e)})

    def _respond(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def _html(self, content: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<html><body style='font-family:sans-serif;max-width:700px;margin:40px auto'>{content}</body></html>".encode())

    def log_message(self, *args):
        pass
