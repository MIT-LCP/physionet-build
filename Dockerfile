FROM python:3.7-slim-buster

RUN apt-get update -y \
    && apt-get upgrade -y \
    && apt-get install build-essential libseccomp-dev libpq-dev libpcre3-dev postgresql-client wget zip -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://github.com/bemoody/wfdb/archive/10.6.2.tar.gz -O wfdb.tar.gz \
    && tar -xf wfdb.tar.gz \
    && (cd wfdb-* && ./configure --without-netfiles && make -C lib install && make -C data install) \
    && ldconfig \
    && rm -rf wfdb*

RUN wget https://github.com/bemoody/lightwave/archive/bfe908a7f53434df61fd2444bf8c235e3e6226fc.tar.gz -O lightwave.tar.gz \
    && tar -xf lightwave.tar.gz \
    && (cd lightwave-* && make sandboxed-lightwave && mkdir -p /usr/local/bin && install -m 4755 sandboxed-lightwave /usr/local/bin) \
    && rm -rf lightwave*

RUN pip install poetry \
    && rm -rf /root/.cache/pip

WORKDIR /code
COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-root \
    && rm -rf /root/.cache/pypoetry /root/.cache/pip

COPY docker/uwsgi-json-logging-plugin docker/uwsgi-json-logging-plugin
RUN cd docker/uwsgi-json-logging-plugin \
    && ./build_plugin.sh

COPY . .
RUN chmod +x /code/docker/wait-for-it.sh /code/docker/dev-entrypoint.sh
