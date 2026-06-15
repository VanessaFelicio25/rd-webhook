import json
import os
import re
import urllib.request
from http.server import BaseHTTPRequestHandler

RD_TOKEN = os.environ["RD_TOKEN"]


def format_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def pick_phone(payload: dict) -> str:
    mobile = payload.get("mobile_phone") or ""
    personal = payload.get("personal_phone") or ""
    return mobile if mobile else personal


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


def update_rd_contact(email: str, data: dict):
    url = f"https://api.rd.services/platform/contacts/email:{email}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        method="PATCH",
        headers={
            "Authorization": f"Bearer {RD_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req):
        pass


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            payload = body.get("payload", body)

            email = payload.get("email", "")
            if not email:
                self._respond(400, {"error": "email ausente"})
                return

            phone_raw = pick_phone(payload)

            first_name = payload.get("first_name") or ""
            last_name = payload.get("last_name") or ""
            if not first_name:
                parts = payload.get("name", "").split(None, 1)
                first_name = parts[0] if parts else ""
                last_name = parts[1] if len(parts) > 1 else ""

            first_name, last_name, full_name = process_names(first_name, last_name)

            update_data = {"name": full_name}
            if phone_raw:
                update_data["mobile_phone"] = format_phone(phone_raw)

            update_rd_contact(email, update_data)
            self._respond(200, {
                "status": "ok",
                "name": full_name,
                "phone": update_data.get("mobile_phone"),
            })

        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *args):
        pass
