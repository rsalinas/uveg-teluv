#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
import argparse
import getpass
import html
from http.cookiejar import MozillaCookieJar
import json
import os
import re
import sys
from typing import Any, Dict
from urllib.parse import urlparse

import requests

try:
    import argcomplete
except ImportError:
    argcomplete = None


DEFAULT_BASE_URL = "https://pubburjs1.tel.uv.es"
LDAP_SECRETS_PATH = os.path.expanduser("~/.uv_ldap_secrets")
COOKIE_DIR = os.path.expanduser("~/.cache/teluv")
RECENTS_PATH = os.path.join(COOKIE_DIR, "recent_destinations.json")
RECENTS_MAX = 10


def load_recents() -> list:
    try:
        with open(RECENTS_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_recent(destination: str) -> None:
    if not destination:
        return
    recents = [d for d in load_recents() if d != destination]
    recents.insert(0, destination)
    del recents[RECENTS_MAX:]
    os.makedirs(COOKIE_DIR, exist_ok=True)
    with open(RECENTS_PATH, "w") as f:
        json.dump(recents, f)


class AuthenticationError(Exception):
    pass


def load_ldap_secrets() -> Dict[str, str]:
    """Carrega les credencials de ~/.uv_ldap_secrets (JSON)."""
    try:
        with open(LDAP_SECRETS_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def cmd_init(base_url: str, timeout: int) -> int:
    """Demana usuari i contrasenya, els verifica i els guarda amb permisos 600."""
    if not sys.stdin.isatty():
        print("'teluv init' requereix un terminal interactiu.", file=sys.stderr)
        return 1

    print("Configuracio de teluv")
    username = input("Usuari UV: ").strip()
    password = getpass.getpass("Contrasenya: ")
    if not username or not password:
        print("Usuari i contrasenya son obligatoris.", file=sys.stderr)
        return 1

    # Verifica les credencials contra el servidor abans de guardar-les.
    print("Verificant credencials...")
    try:
        login(requests.Session(), base_url, username, password, timeout)
    except requests.HTTPError:
        print("Credencials incorrectes.", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"No s'han pogut verificar (xarxa): {exc}", file=sys.stderr)
        return 3

    default_destination = input("Numero de desviament per defecte (opcional): ").strip()

    secrets = load_ldap_secrets()
    secrets.update({"username": username, "password": password})
    if default_destination:
        secrets["default_destination"] = default_destination

    # O_CREAT amb mode 0600 perque el fitxer mai existisca amb permisos amples.
    fd = os.open(LDAP_SECRETS_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(secrets, f, indent=2)
    print(f"Credencials verificades i guardades a {LDAP_SECRETS_PATH} (permisos 600).")
    return 0


def build_fwd_payload(destination: str) -> Dict[str, Any]:
    return {
        "callForwardAllDestination": {
            "sendToCustomDestination": destination,
            "sendToVoiceMailPilotNumber": "false",
        },
        "forwardBusyInternalCallDestination": {},
        "forwardNoAnswerInternalCallDestination": {},
        "forwardBusyExternalCallDestination": {},
        "forwardNoAnswerExternalCallDestination": {},
    }


def build_unfwd_payload(no_answer_destination: str) -> Dict[str, Any]:
    return {
        "callForwardAllDestination": {
            "sendToCustomDestination": "",
            "sendToVoiceMailPilotNumber": "false",
        },
        "forwardBusyInternalCallDestination": {
            "sendToVoiceMailPilotNumber": "false",
            "sendToCustomDestination": "",
        },
        "forwardNoAnswerInternalCallDestination": {
            "sendToCustomDestination": no_answer_destination,
            "sendToVoiceMailPilotNumber": "false",
        },
        "forwardBusyExternalCallDestination": {
            "sendToVoiceMailPilotNumber": "false",
            "sendToCustomDestination": "",
        },
        "forwardNoAnswerExternalCallDestination": {
            "sendToCustomDestination": no_answer_destination,
            "sendToVoiceMailPilotNumber": "false",
        },
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="teluv",
        description="Gestiona els desviaments del telefon Cisco via UCM-UDS.",
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="URL base del portal (per defecte: %(default)s)",
    )
    parser.add_argument(
        "--extension-id",
        default=None,
        help="ID de l'extensio (per defecte: es descobreix automaticament)",
    )
    parser.add_argument(
        "--timeout",
        default=20,
        type=int,
        help="Timeout de la peticio HTTP en segons (per defecte: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra URL, capcaleres i JSON pero no envia la peticio.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Mostra tambe el JSON cru en els comandos de forwarding.",
    )

    subparsers = parser.add_subparsers(dest="command")

    p_forward = subparsers.add_parser(
        "forward",
        aliases=["f"],
        help="Activa el desviament general",
    )
    p_forward.add_argument(
        "destination",
        nargs="?",
        default=None,
        help=(
            "Numero de desti del desviament "
            "(per defecte: 'default_destination' del fitxer de credencials)"
        ),
    )

    p_unforward = subparsers.add_parser(
        "unforward",
        aliases=["uf"],
        help="Desactiva el desviament general",
    )
    p_unforward.add_argument(
        "--no-answer-destination",
        default="",
        help="Valor per a no-answer intern/extern en unforward (per defecte: buit)",
    )

    subparsers.add_parser(
        "forwarding-status",
        aliases=["check", "fs"],
        help="Consulta l'estat actual del desviament",
    )
    subparsers.add_parser("info", help="Mostra tota la informacio JSON de l'usuari")
    subparsers.add_parser(
        "init",
        help="Configura usuari i contrasenya (els guarda en ~/.uv_ldap_secrets)",
    )

    return parser


def normalize_command(command: str) -> str:
    if command in ("forward", "f"):
        return "forward"
    if command in ("unforward", "uf"):
        return "unforward"
    if command in (None, "forwarding-status", "check", "fs"):
        return "forwarding-status"
    return command


def build_payload(command: str, args: argparse.Namespace) -> Dict[str, Any]:
    if command == "forward":
        return build_fwd_payload(destination=args.destination)
    if command == "unforward":
        return build_unfwd_payload(no_answer_destination=args.no_answer_destination)
    raise ValueError(f"Comanda sense payload: {command}")


def clean_html_text(text: str) -> str:
    # Elimina primer els blocs script/style per evitar soroll en l'eixida.
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def format_response_body(response: requests.Response) -> str:
    body = response.text.strip()
    if not body:
        return ""

    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            return json.dumps(response.json(), indent=2, ensure_ascii=False)
        except ValueError:
            return clean_html_text(body)

    return clean_html_text(body)


def build_headers(base_url: str) -> Dict[str, str]:
    headers = {
        "User-Agent": "teluv/0.1",
        "Accept": "*/*",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": base_url,
        "Referer": f"{base_url}/ucmuser/main",
    }
    return headers


def endpoint_url(base_url: str, username: str, extension_id: str) -> str:
    return (
        f"{base_url}/cucm-uds/private/user/{username}/extension/{extension_id}"
    )


def extensions_url(base_url: str, username: str) -> str:
    return f"{base_url}/cucm-uds/private/user/{username}/extensions"


def user_url(base_url: str, username: str) -> str:
    return f"{base_url}/cucm-uds/private/user/{username}"


def cookie_path(base_url: str, username: str) -> str:
    host = urlparse(base_url).netloc.replace(":", "_")
    return os.path.join(COOKIE_DIR, f"cookies_{host}_{username}.txt")


def attach_cookie_jar(session: requests.Session, path: str) -> None:
    jar = MozillaCookieJar(path)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except OSError:
        pass
    session.cookies = jar


def persist_cookies(session: requests.Session) -> None:
    if not isinstance(session.cookies, MozillaCookieJar):
        return
    os.makedirs(COOKIE_DIR, exist_ok=True)
    session.cookies.save(ignore_discard=True, ignore_expires=True)


def clear_session_cookies(session: requests.Session, base_url: str) -> None:
    host = urlparse(base_url).hostname
    if not host:
        return

    for cookie in list(session.cookies):
        if host not in cookie.domain:
            continue
        if cookie.name not in ("JSESSIONID", "JSESSIONIDSSO"):
            continue
        session.cookies.clear(domain=cookie.domain, path=cookie.path, name=cookie.name)


def is_auth_failure(response: requests.Response) -> bool:
    if response.status_code in (401, 403, 404):
        return True

    content_type = response.headers.get("Content-Type", "")
    body_lower = response.text.lower()
    if "text/html" in content_type and "j_security_check" in body_lower:
        return True
    return False


def request_with_reauth(
    session: requests.Session,
    method: str,
    url: str,
    *,
    base_url: str,
    username: str,
    password: str,
    timeout: int,
    **kwargs: Any,
) -> requests.Response:
    response = session.request(method, url, timeout=timeout, **kwargs)
    if not is_auth_failure(response):
        persist_cookies(session)
        return response

    if not password:
        raise AuthenticationError(
            "Sessio caducada i no hi ha contrasenya disponible per reautenticar."
        )

    print("Logging in")
    login(
        session=session,
        base_url=base_url,
        username=username,
        password=password,
        timeout=timeout,
    )
    persist_cookies(session)
    response = session.request(method, url, timeout=timeout, **kwargs)
    persist_cookies(session)
    return response


def print_status_summary(ext_data: Dict[str, Any], detail_data: Dict[str, Any]) -> None:
    number = ext_data.get("directoryNumber", "?")

    fwd = ext_data.get("callForwardAllDestination", {})
    fwd_dest = fwd.get("sendToCustomDestination", "")

    def dest(d: Dict[str, Any]) -> str:
        vm = d.get("sendToVoiceMailPilotNumber", "false") == "true"
        custom = d.get("sendToCustomDestination", "")
        if vm:
            return "Voicemail"
        return custom if custom else "(desactivat)"

    busy_int  = dest(detail_data.get("forwardBusyInternalCallDestination", {}))
    busy_ext  = dest(detail_data.get("forwardBusyExternalCallDestination", {}))
    noan_int  = dest(detail_data.get("forwardNoAnswerInternalCallDestination", {}))
    noan_ext  = dest(detail_data.get("forwardNoAnswerExternalCallDestination", {}))

    print()
    print(f"  Extension           : {number}")
    print(f"  Forward all calls   : {fwd_dest if fwd_dest else '(disabled)'}" + ("  [ACTIVE]" if fwd_dest else ""))
    if fwd_dest:
        return

    print(f"  Busy  (internal)    : {busy_int}")
    print(f"  Busy  (external)    : {busy_ext}")
    print(f"  No answer (internal): {noan_int}")
    print(f"  No answer (external): {noan_ext}")


def fetch_primary_extension(
    session: requests.Session,
    base_url: str,
    username: str,
    headers: Dict[str, str],
    timeout: int,
    password: str,
) -> Dict[str, Any]:
    """Torna l'extensio primaria de l'usuari (inclou el seu id)."""
    r = request_with_reauth(
        session,
        "GET",
        extensions_url(base_url, username),
        base_url=base_url,
        username=username,
        password=password,
        headers={**headers, "Accept": "application/json"},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("extension", {})


def fetch_and_print_status(
    session: requests.Session,
    base_url: str,
    username: str,
    extension_id: str,
    headers: Dict[str, str],
    timeout: int,
    show_json: bool,
    password: str,
) -> None:
    status_headers = {**headers, "Accept": "application/json"}

    r_list = request_with_reauth(
        session,
        "GET",
        extensions_url(base_url, username),
        base_url=base_url,
        username=username,
        password=password,
        headers=status_headers,
        timeout=timeout,
    )
    r_list.raise_for_status()
    list_data = r_list.json()

    ext_data = list_data.get("extension", {})
    fwd_dest = ext_data.get("callForwardAllDestination", {}).get("sendToCustomDestination", "")
    ext_id = extension_id or ext_data.get("id")

    detail_data: Dict[str, Any] = {}
    if not fwd_dest and ext_id:
        r_detail = request_with_reauth(
            session,
            "GET",
            endpoint_url(base_url, username, ext_id),
            base_url=base_url,
            username=username,
            password=password,
            headers=status_headers,
            timeout=timeout,
        )
        r_detail.raise_for_status()
        detail_data = r_detail.json()

    if show_json:
        print(json.dumps(list_data, indent=2, ensure_ascii=False))
    print_status_summary(ext_data, detail_data)

    recents = load_recents()
    if recents:
        print()
        print("  Recent destinations :", ", ".join(recents))


def fetch_and_print_user_info(
    session: requests.Session,
    base_url: str,
    username: str,
    headers: Dict[str, str],
    timeout: int,
    password: str,
) -> None:
    info_headers = {**headers, "Accept": "application/json"}
    response = request_with_reauth(
        session,
        "GET",
        user_url(base_url, username),
        base_url=base_url,
        username=username,
        password=password,
        headers=info_headers,
        timeout=timeout,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))


def login(session: requests.Session, base_url: str, username: str, password: str, timeout: int) -> None:
    clear_session_cookies(session, base_url)
    bootstrap_url = extensions_url(base_url, username)
    response = session.get(
        bootstrap_url,
        headers={"Accept": "application/json", "User-Agent": "teluv/0.1"},
        auth=(username, password),
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise requests.HTTPError(
            f"login HTTP {response.status_code}",
            response=response,
        )


def main() -> int:
    parser = make_parser()
    if argcomplete is not None:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()
    command = normalize_command(args.command)

    if command == "init":
        return cmd_init(args.base_url, args.timeout)

    secrets = load_ldap_secrets()
    username = os.getenv("TELUV_USER") or secrets.get("username", "")
    password = os.getenv("TELUV_PASSWORD") or secrets.get("password", "")
    if not username:
        print("No hi ha credencials configurades.", file=sys.stderr)
        print("Executa: teluv init", file=sys.stderr)
        return 2

    if command == "forward" and not args.destination:
        args.destination = secrets.get("default_destination", "")
        if not args.destination:
            print("Cal indicar un numero de desti: teluv f <numero>", file=sys.stderr)
            print(
                "(o configura 'default_destination' en ~/.uv_ldap_secrets)",
                file=sys.stderr,
            )
            return 1

    payload = None if command in ("forwarding-status", "info") else build_payload(command, args)
    headers = build_headers(args.base_url)

    if args.dry_run:
        if command == "info":
            print("[dry-run] URL:", user_url(args.base_url, username))
        elif command == "forwarding-status":
            print("[dry-run] URL:", extensions_url(args.base_url, username))
        else:
            ext_id = args.extension_id or "<auto-descobert>"
            print("[dry-run] URL:", endpoint_url(args.base_url, username, ext_id))
        print("[dry-run] Headers:")
        print(json.dumps(headers, indent=2, ensure_ascii=False))
        if payload is not None:
            print("[dry-run] Payload:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("[dry-run] Request: GET (sense payload)")
        if command != "info":
            print("[dry-run] Status URL:", extensions_url(args.base_url, username))
        return 0

    try:
        session = requests.Session()
        session.verify = True
        attach_cookie_jar(session, cookie_path(args.base_url, username))
        if command == "forwarding-status":
            fetch_and_print_status(
                session,
                args.base_url,
                username,
                args.extension_id,
                headers,
                args.timeout,
                args.json,
                password,
            )
            return 0
        if command == "info":
            fetch_and_print_user_info(
                session,
                args.base_url,
                username,
                headers,
                args.timeout,
                password,
            )
            return 0
        else:
            ext_id = args.extension_id
            if not ext_id:
                ext = fetch_primary_extension(
                    session, args.base_url, username, headers, args.timeout, password
                )
                ext_id = ext.get("id")
                if not ext_id:
                    print("No s'ha pogut descobrir l'extensio.", file=sys.stderr)
                    return 1
            url = endpoint_url(args.base_url, username, ext_id)
            response = request_with_reauth(
                session,
                "PUT",
                url,
                base_url=args.base_url,
                username=username,
                password=password,
                headers=headers,
                json=payload,
                timeout=args.timeout,
            )
            if not response.ok:
                print(f"HTTP {response.status_code}", file=sys.stderr)
                text = format_response_body(response)
                if text:
                    print(text, file=sys.stderr)
                return 1
            if command == "forward":
                save_recent(args.destination)
            fetch_and_print_status(
                session,
                args.base_url,
                username,
                args.extension_id,
                headers,
                args.timeout,
                args.json,
                password,
            )
            return 0
    except AuthenticationError as exc:
        print(f"Error d'autenticacio: {exc}", file=sys.stderr)
        print("Executa 'teluv init' o aporta TELUV_PASSWORD.", file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        print(f"Error de xarxa: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
