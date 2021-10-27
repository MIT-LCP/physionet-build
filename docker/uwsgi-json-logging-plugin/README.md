# uWSGI JSON logging plugin

uWSGI plugin that defines custom JSON-escaped logchunks `json_uri` and `json_host`. These logchunks can be used to configure JSON logging of requests. Problem with uWSGI [JSON encoder](https://uwsgi-docs.readthedocs.io/en/latest/LogEncoders.html) is that logchunks can't be encoded as separate JSON fields. You can define custom text output that looks like JSON, but the problem is that string fields are not JSON escaped. This plugin solves that problem and escapes problematic logchunks.

Example of a uwsgi log format (ini file):
```ini
[uwsgi]
plugin = escape_json_plugin.so

logger-req = stdio
; json_uri and json_host are json-escaped fields defined in `escape_json_plugin.so`
log-format = "address":"%(addr)", "host":"%(json_host)", "method":"%(method)", "uri":"%(json_uri)", "protocol":"%(proto)", "resp_size":%(size), "req_body_size":%(cl), "resp_status":%(status), "resp_time":%(secs)
log-req-encoder = format {"time":"${micros}", "source":"uwsgi-req", ${msg}}
log-req-encoder = nl
```

And a resulting log record:
```json
{"time": 1580765438.767256, "source": "uwsgi-req", "address": "10.132.0.10", "host": "api.velebit.ai", "method": "GET", "uri": "/authorize", "protocol": "HTTP/1.0", "resp_size": 120, "req_body_size": 0, "resp_status": 200, "resp_time": 0.000524}
```

Very short official documentation on registering new logchunks, used as a starting point for this code: https://uwsgi-docs.readthedocs.io/en/latest/LogFormat.html

Tested with uWSGI version 2.0.18.

## Usage example
You must have uWSGI installed to build and use this plugin: https://uwsgi-docs.readthedocs.io/en/latest/Install.html
### Build plugin
```sh
uwsgi --build-plugin escape_json.c
```
or use bash script:
```sh
./build_plugin.sh
```
### Run uWSGI with plugin
```sh
uwsgi --plugin escape_json_plugin.so ...
```
Or you can reference plugin in your ini config file:
```ini
[uwsgi]
plugin = escape_json_plugin.so
```

---
Ivan Borko, [Velebit AI](https://www.velebit.ai)
