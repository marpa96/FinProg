import unittest

from scripts.import_rocketmoney_curls import collect_updates


class ImportRocketMoneyCurlsTests(unittest.TestCase):
    def test_imports_auth_login_curl_values(self) -> None:
        curl = r'''
curl.exe ^"https://auth.rocketaccount.com/u/login?state=abc123^" ^
  -X POST ^
  -H ^"User-Agent: Test Browser^" ^
  -H ^"Cookie: did=one; auth0=two^" ^
  --data-raw ^"username=user%40example.com^&password=secret^&ulp-anonymous-id=anon-1^&state=abc123^&acul-sdk=%40auth0%2Fauth0-acul-js%400.1.0-beta.6^"
'''
        updates = collect_updates(curl)

        self.assertEqual(updates["ROCKETMONEY_AUTH_LOGIN_URL"], "https://auth.rocketaccount.com/u/login?state=abc123")
        self.assertEqual(updates["ROCKETMONEY_AUTH_COOKIE"], "did=one; auth0=two")
        self.assertEqual(updates["ROCKETMONEY_AUTH_STATE"], "abc123")
        self.assertEqual(updates["ROCKETMONEY_ULP_ANONYMOUS_ID"], "anon-1")
        self.assertEqual(updates["ROCKETMONEY_USERNAME"], "user@example.com")
        self.assertEqual(updates["ROCKETMONEY_PASSWORD"], "secret")

    def test_imports_graphql_cookie_values(self) -> None:
        curl = r'''
curl.exe ^"https://client-api.rocketmoney.com/graphql^" ^
  -H ^"User-Agent: Test Browser^" ^
  -H ^"Cookie: app=session; other=value^" ^
  -H ^"x-truebill-web-client-version: abc123^" ^
  -H ^"x-analytics-session: 1776134135006^"
'''
        updates = collect_updates(curl)

        self.assertEqual(updates["ROCKETMONEY_COOKIE"], "app=session; other=value")
        self.assertEqual(updates["ROCKETMONEY_TRUEBILL_WEB_CLIENT_VERSION"], "abc123")
        self.assertEqual(updates["ROCKETMONEY_ANALYTICS_SESSION"], "1776134135006")


if __name__ == "__main__":
    unittest.main()
