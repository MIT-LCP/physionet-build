
import requests


CLIENT_ID="rcKCw8TDUU5qwW7N4yUeWIj9tpzDJSQ3f35rxvfT"
CLIENT_SECRET="zr33KPGR1Ow8rQYKsgH2SPhTB0kEIdlcWrA8xpZJxhI464mfJXFdKsrg9y1vt5cLzqLmWU5Qdw8vGsJaqVdsrHwEIPSwpZa5kcFJVKzH394w0oiAphF2gC2cKmiCmW0K"
CODE_VERIFIER="1KWEQ511H8ND7DF7882WHV8OJFNG48EVM7TFR6ZVF6GGRPVDW5F7081SC1"
CODE_CHALLENGE="7hpFTQAPcpD7-bTQvXNgRaRXPz7mV5f7HwqCXSt36ck"
CODE="VuQPg3yRaSClNNCHiNvnCJ2HF6VEC7"


# Token endpoint
token_url = 'http://127.0.0.1:8000/o/token/'

# Data for token request
data = {
    "cache-control": "no-cache",
    "content-type": "application/x-www-form-urlencoded",
    "grant_type": "authorization_code",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": CODE,
    "code_verifier": CODE_VERIFIER,
    "redirect_uri": "http://127.0.0.1:8000/noexist/callback",
}

# Request the token
response = requests.post(token_url, data=data)

print(response.json())