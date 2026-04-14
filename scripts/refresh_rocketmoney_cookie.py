"""Refresh Rocket Money cookies from credentials in .env.

The browser's captured login request contains short-lived Auth0 state and
anti-bot cookies. This script avoids storing those as primary inputs: it starts
from Rocket Money's app URL, follows redirects to the current Auth0 login page,
parses the fresh login form, posts credentials from .env, follows redirects, and
stores the resulting cookie header for future GraphQL requests.
"""

from __future__ import annotations

import argparse
import html.parser
import http.cookiejar
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib import parse, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.local_env import load_env_file, update_env_file


DEFAULT_OUTPUT = Path("data/private/rocketmoney_refreshed_cookies.txt")
DEFAULT_LOGIN_START_URL = "https://app.rocketmoney.com/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)


@dataclass
class LoginForm:
    action: str | None = None
    method: str = "post"
    fields: dict[str, str] = field(default_factory=dict)


class LoginFormParser(html.parser.HTMLParser):
    """Extract the first username/password login form and its input fields."""

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[LoginForm] = []
        self._current: LoginForm | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "form":
            self._current = LoginForm(
                action=attributes.get("action"),
                method=attributes.get("method", "post").lower(),
            )
            return

        if tag.lower() == "input" and self._current is not None:
            name = attributes.get("name")
            if name:
                self._current.fields[name] = attributes.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self._current is not None:
            self.forms.append(self._current)
            self._current = None

    def close(self) -> None:
        if self._current is not None:
            self.forms.append(self._current)
            self._current = None
        super().close()


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required in .env")
    return value


def state_from_login_url(login_url: str) -> str | None:
    query = parse.parse_qs(parse.urlparse(login_url).query)
    values = query.get("state")
    return values[0] if values else None


def cookie_header_from_jar(cookie_jar: http.cookiejar.CookieJar) -> str:
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in cookie_jar)


def find_login_form(html: str) -> LoginForm:
    parser = LoginFormParser()
    parser.feed(html)
    parser.close()

    for form in parser.forms:
        field_names = set(form.fields)
        if {"username", "password"}.issubset(field_names):
            return form

    if parser.forms:
        return parser.forms[0]
    return LoginForm()


def headers_for_page(referer: str | None = None) -> dict[str, str]:
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "user-agent": os.environ.get("ROCKETMONEY_USER_AGENT", DEFAULT_USER_AGENT),
    }
    if referer:
        headers["referer"] = referer
    auth_cookie = os.environ.get("ROCKETMONEY_AUTH_COOKIE")
    if auth_cookie:
        headers["cookie"] = auth_cookie
    return headers


def discover_login_page(opener: request.OpenerDirector, start_url: str) -> tuple[str, str]:
    start_request = request.Request(start_url, headers=headers_for_page())
    response = opener.open(start_request, timeout=60)  # noqa: S310
    login_url = response.geturl()
    html = response.read().decode("utf-8", errors="replace")
    return login_url, html


def build_login_body(login_url: str, form: LoginForm) -> bytes:
    fields = dict(form.fields)
    state = fields.get("state") or os.environ.get("ROCKETMONEY_AUTH_STATE") or state_from_login_url(login_url)
    if state:
        fields["state"] = state

    fields["username"] = require_env("ROCKETMONEY_USERNAME")
    fields["password"] = require_env("ROCKETMONEY_PASSWORD")
    fields.setdefault("ulp-anonymous-id", os.environ.get("ROCKETMONEY_ULP_ANONYMOUS_ID", ""))
    fields.setdefault("ulp-affiliate-referrer", "")
    fields.setdefault("acul-sdk", os.environ.get("ROCKETMONEY_ACUL_SDK", "@auth0/auth0-acul-js@0.1.0-beta.6"))
    return parse.urlencode(fields).encode("utf-8")


def login_action_url(login_url: str, form: LoginForm) -> str:
    if form.action:
        return parse.urljoin(login_url, form.action)
    return os.environ.get("ROCKETMONEY_AUTH_LOGIN_URL") or login_url


def refresh_cookie(output_path: Path, env_path: Path, start_url: str | None = None) -> tuple[str, str, int]:
    start_url = start_url or os.environ.get("ROCKETMONEY_LOGIN_START_URL") or DEFAULT_LOGIN_START_URL
    cookie_jar = http.cookiejar.CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(cookie_jar))

    captured_login_url = os.environ.get("ROCKETMONEY_AUTH_LOGIN_URL")
    if captured_login_url:
        login_url = captured_login_url
        login_request = request.Request(login_url, headers=headers_for_page(referer=start_url))
        login_response = opener.open(login_request, timeout=60)  # noqa: S310
        login_html = login_response.read().decode("utf-8", errors="replace")
    else:
        login_url, login_html = discover_login_page(opener, start_url)
    form = find_login_form(login_html)
    body = build_login_body(login_url, form)
    action_url = login_action_url(login_url, form)

    headers = {
        **headers_for_page(referer=login_url),
        "content-type": "application/x-www-form-urlencoded",
        "origin": f"{parse.urlparse(action_url).scheme}://{parse.urlparse(action_url).netloc}",
    }
    login_request = request.Request(action_url, data=body, headers=headers, method="POST")
    response = opener.open(login_request, timeout=60)  # noqa: S310
    final_url = response.geturl()

    cookie_header = cookie_header_from_jar(cookie_jar)
    if not cookie_header:
        raise RuntimeError("Login flow completed without any cookies")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(cookie_header + "\n", encoding="utf-8")
    update_env_file(env_path, {"ROCKETMONEY_COOKIE": cookie_header})
    return final_url, cookie_header, len(cookie_jar)


def main() -> int:
    env_path = ROOT / ".env"
    load_env_file(env_path)

    parser = argparse.ArgumentParser(description="Refresh Rocket Money cookies from .env credentials.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-url", default=None)
    args = parser.parse_args()

    final_url, _cookie_header, cookie_count = refresh_cookie(args.output, env_path, args.start_url)
    print(f"Wrote {cookie_count} cookies to {args.output}")
    print("Updated ROCKETMONEY_COOKIE in .env")
    print(f"Final URL: {final_url}")
    if "auth.rocketaccount.com/u/login" in final_url:
        print("Login still appears to be on the Auth0 login page. MFA, CAPTCHA, or anti-bot handling may be required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
