import unittest

from scripts.refresh_rocketmoney_cookie import find_login_form, login_action_url, state_from_login_url


class RefreshRocketMoneyCookieTests(unittest.TestCase):
    def test_state_from_login_url(self) -> None:
        self.assertEqual(
            state_from_login_url("https://auth.rocketaccount.com/u/login?state=abc123&x=1"),
            "abc123",
        )

    def test_state_from_login_url_missing(self) -> None:
        self.assertIsNone(state_from_login_url("https://auth.rocketaccount.com/u/login"))

    def test_find_login_form_extracts_action_and_fields(self) -> None:
        form = find_login_form(
            """
            <html><body>
              <form action="/u/login?state=fresh" method="post">
                <input type="hidden" name="state" value="fresh">
                <input type="text" name="username" value="">
                <input type="password" name="password" value="">
                <input type="hidden" name="acul-sdk" value="@auth0/auth0-acul-js@0.1.0-beta.6">
              </form>
            </body></html>
            """
        )

        self.assertEqual(form.action, "/u/login?state=fresh")
        self.assertEqual(form.fields["state"], "fresh")
        self.assertIn("username", form.fields)

    def test_login_action_url_resolves_relative_action(self) -> None:
        form = find_login_form('<form action="/u/login?state=fresh"><input name="username"><input name="password"></form>')

        self.assertEqual(
            login_action_url("https://auth.rocketaccount.com/u/login?state=fresh", form),
            "https://auth.rocketaccount.com/u/login?state=fresh",
        )


if __name__ == "__main__":
    unittest.main()
