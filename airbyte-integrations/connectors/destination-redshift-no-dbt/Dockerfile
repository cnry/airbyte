FROM python:3.7.11-alpine3.14 as base

# build and load all requirements
FROM base as builder
WORKDIR /airbyte/integration_code

# upgrade pip to the latest version
RUN apk --no-cache upgrade \
    && pip install --upgrade pip \
    && apk --no-cache add tzdata build-base \
    && apk add --no-cache postgresql-dev gcc python3-dev musl-dev


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
RUN apk --no-cache add bash \
    && apk add --no-cache postgresql-dev gcc python3-dev musl-dev

# copy payload code only
COPY main.py ./
COPY destination_redshift_no_dbt ./destination_redshift_no_dbt

ENV AIRBYTE_ENTRYPOINT "python /airbyte/integration_code/main.py"
ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]

LABEL io.airbyte.version=0.1.10.9
LABEL io.airbyte.name=airbyte/destination-redshift-no-dbt
