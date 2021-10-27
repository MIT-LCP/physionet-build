/*
  uWSGI plugin that creates custom json-escaped logging variables.

  build plugin with `uwsgi --build-plugin <filename.c>`
  and use it with `uwsgi --plugin <filename_plugin.so> ...`
*/
#include <uwsgi.h>


static ssize_t uwsgi_lf_json_uri(struct wsgi_request *wsgi_req, char **buf) {
    long pos = offsetof(struct wsgi_request, uri);
    long pos_len = offsetof(struct wsgi_request, uri_len);
    char **var = (char **) (((char *) wsgi_req) + pos);
    uint16_t *varlen = (uint16_t *) (((char *) wsgi_req) + pos_len);

    char *e_json = uwsgi_malloc((*varlen * 2) + 1);
    escape_json(*var, *varlen, e_json);
    *buf = e_json;
    return strlen(*buf);
}

static ssize_t uwsgi_lf_json_host(struct wsgi_request *wsgi_req, char **buf) {
    long pos = offsetof(struct wsgi_request, host);
    long pos_len = offsetof(struct wsgi_request, host_len);
    char **var = (char **) (((char *) wsgi_req) + pos);
    uint16_t *varlen = (uint16_t *) (((char *) wsgi_req) + pos_len);

    char *e_json = uwsgi_malloc((*varlen * 2) + 1);
    escape_json(*var, *varlen, e_json);
    *buf = e_json;
    return strlen(*buf);
}

static void register_logchunks() {
        uwsgi_register_logchunk("json_uri", uwsgi_lf_json_uri, 1);
        uwsgi_register_logchunk("json_host", uwsgi_lf_json_host, 1);
}

struct uwsgi_plugin escape_json_plugin = {
        .name = "escape_json",
        .on_load = register_logchunks,
};
