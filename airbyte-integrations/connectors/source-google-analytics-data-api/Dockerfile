FROM python:3.9.11-alpine3.15 as base

# build and load all requirements
FROM base as builder
WORKDIR /airbyte/integration_code

# upgrade pip to the latest version
RUN apk --no-cache upgrade \
    && apk --no-cache add tzdata build-base g++ musl-dev libffi-dev curl bash git \
      linux-headers openssl openssl-dev readline-dev zlib-dev libstdc++ \
    && pip install --upgrade pip \
    && curl https://raw.githubusercontent.com/pyenv/pyenv-installer/master/bin/pyenv-installer | bash \
    && export PATH="/root/.pyenv/bin:$PATH" \
    && eval "$(pyenv init - --no-rehash)" \
    && eval "$(pyenv virtualenv-init -)" \
    && pyenv install 3.9.11

COPY setup.py ./
# install necessary packages to a temporary folder
RUN pip install --prefix=/install .

# build a clean environment
FROM base
WORKDIR /airbyte/integration_code

# copy all loaded and built libraries to a pure basic image
COPY --from=builder /install /usr/local
# add default timezone settings
COPY --from=builder /usr/share/zoneinfo/Etc/UTC /etc/localtime
RUN echo "Etc/UTC" > /etc/timezone

# bash is installed for more convenient debugging.
RUN apk --no-cache add bash libstdc++

# copy payload code only
COPY main.py ./
COPY source_google_analytics_data_api ./source_google_analytics_data_api

ENV AIRBYTE_ENTRYPOINT "python /airbyte/integration_code/main.py"
ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]

LABEL io.airbyte.version=0.1.0
LABEL io.airbyte.name=airbyte/source-google-analytics-data-api
