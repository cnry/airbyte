#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#


import json
import logging
from datetime import datetime
from typing import Generator, Any, MutableMapping, Mapping

from airbyte_cdk.logger import AirbyteLogger
from airbyte_cdk.models import (
    AirbyteCatalog,
    AirbyteConnectionStatus,
    AirbyteMessage,
    AirbyteRecordMessage,
    AirbyteStream,
    ConfiguredAirbyteCatalog,
    Status,
    Type, SyncMode, AirbyteStateMessage,
)
from airbyte_cdk.sources import Source
from google.analytics.data_v1beta import BetaAnalyticsDataClient, Dimension, RunReportResponse, OrderBy
from google.analytics.data_v1beta.types import DateRange
from google.analytics.data_v1beta.types import Metric
from google.analytics.data_v1beta.types import RunReportRequest
from google.oauth2 import service_account

DEFAULT_CURSOR_FIELD = "date"


class SourceGoogleAnalyticsDataApi(Source):
    def check(self, logger: AirbyteLogger, config: Mapping[str, Any]) -> AirbyteConnectionStatus:
        """
        Tests if the input configuration can be used to successfully connect to the integration
            e.g: if a provided Stripe API token can be used to connect to the Stripe API.

        :param logger: Logging object to display debug/info/error to the logs
            (logs will not be accessible via airbyte UI if they are not passed to this logger)
        :param config: Json object containing the configuration of this source, content of this json is as specified in
        the properties of the spec.json/spec.yaml file

        :return: AirbyteConnectionStatus indicating a Success or Failure
        """
        try:
            config["metrics"] = "activeUsers"
            config["date_ranges_start_date"] = "yesterday"
            config["date_ranges_end_date"] = "today"

            self._run_report(config)

            return AirbyteConnectionStatus(status=Status.SUCCEEDED)
        except Exception as e:
            return AirbyteConnectionStatus(status=Status.FAILED, message=f"An exception occurred: {str(e)}")

    def discover(self, logger: AirbyteLogger, config: Mapping[str, Any]) -> AirbyteCatalog:
        """
        Returns an AirbyteCatalog representing the available streams and fields in this integration.
        For example, given valid credentials to a Postgres database,
        returns an Airbyte catalog where each postgres table is a stream, and each table column is a field.

        :param logger: Logging object to display debug/info/error to the logs
            (logs will not be accessible via airbyte UI if they are not passed to this logger)
        :param config: Json object containing the configuration of this source, content of this json is as specified in
        the properties of the spec.json/spec.yaml file

        :return: AirbyteCatalog is an object describing a list of all available streams in this source.
            A stream is an AirbyteStream object that includes:
            - its stream name (or table name in the case of Postgres)
            - json_schema providing the specifications of expected schema for this stream (a list of columns described
            by their names and types)
        """
        report_name = config.get("report_name")

        response = SourceGoogleAnalyticsDataApi._run_report(config)

        properties = {DEFAULT_CURSOR_FIELD: {"type": "string"}}

        for dimension in response.dimension_headers:
            properties[dimension.name] = {"type": "string"}

        for metric in response.metric_headers:
            properties[metric.name] = {"type": "number"}

        json_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": properties,
        }

        primary_key = list(map(lambda h: [h.name], response.dimension_headers))

        stream = AirbyteStream(
            name=report_name,
            json_schema=json_schema,
            supported_sync_modes=[SyncMode.full_refresh, SyncMode.incremental],
            source_defined_primary_key=primary_key,
            default_cursor_field=[DEFAULT_CURSOR_FIELD]
        )
        return AirbyteCatalog(streams=[stream])

    def read(
        self, logger: logging.Logger, config: Mapping[str, Any], catalog: ConfiguredAirbyteCatalog, state: MutableMapping[str, Any] = None
    ) -> Generator[AirbyteMessage, None, None]:
        """
        Returns a generator of the AirbyteMessages generated by reading the source with the given configuration,
        catalog, and state.

        :param logger: Logging object to display debug/info/error to the logs
            (logs will not be accessible via airbyte UI if they are not passed to this logger)
        :param config: Json object containing the configuration of this source, content of this json is as specified in
            the properties of the spec.json/spec.yaml file
        :param catalog: The input catalog is a ConfiguredAirbyteCatalog which is almost the same as AirbyteCatalog
            returned by discover(), but
        in addition, it's been configured in the UI! For each particular stream and field, there may have been provided
        with extra modifications such as: filtering streams and/or columns out, renaming some entities, etc
        :param state: When a Airbyte reads data from a source, it might need to keep a checkpoint cursor to resume
            replication in the future from that saved checkpoint.
            This is the object that is provided with state from previous runs and avoid replicating the entire set of
            data everytime.

        :return: A generator that produces a stream of AirbyteRecordMessage contained in AirbyteMessage object.
        """
        report_name = config.get("report_name")

        response = self._run_report(config)

        dimensions = list(map(lambda h: h.name, response.dimension_headers))
        metrics = list(map(lambda h: h.name, response.metric_headers))

        last_cursor_value = state.get(report_name, {}).get(DEFAULT_CURSOR_FIELD, "")

        for row in response.rows:
            data = dict(zip(dimensions, list(map(lambda v: v.value, row.dimension_values))))
            data.update(dict(zip(metrics, list(map(lambda v: float(v.value), row.metric_values)))))

            if last_cursor_value <= data[DEFAULT_CURSOR_FIELD]:
                yield AirbyteMessage(
                    type=Type.RECORD,
                    record=AirbyteRecordMessage(stream=report_name, data=data, emitted_at=int(datetime.now().timestamp()) * 1000),
                )

                last_cursor_value = data[DEFAULT_CURSOR_FIELD]

        yield AirbyteMessage(type=Type.STATE, state=AirbyteStateMessage(data={report_name: {DEFAULT_CURSOR_FIELD: last_cursor_value}}))

    @staticmethod
    def _client(json_credentials: Mapping[str, str]) -> BetaAnalyticsDataClient:
        credentials = service_account.Credentials.from_service_account_info(json_credentials)
        return BetaAnalyticsDataClient(credentials=credentials)

    @staticmethod
    def _run_report(config: Mapping[str, Any]) -> RunReportResponse:
        property_id = config.get("property_id")

        dimensions = [Dimension(name=dim) for dim in config.get("dimensions", "").split(", ") if dim != DEFAULT_CURSOR_FIELD]
        dimensions.append(Dimension(name=DEFAULT_CURSOR_FIELD))

        metrics = [Metric(name=metric) for metric in config.get("metrics", "").split(", ")]

        date_ranges_start_date = config.get("date_ranges_start_date")
        date_ranges_end_date = config.get("date_ranges_end_date")

        client = SourceGoogleAnalyticsDataApi._client(json.loads(config.get("json_credentials")))

        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=dimensions,
            metrics=metrics,
            date_ranges=[DateRange(start_date=date_ranges_start_date, end_date=date_ranges_end_date)],
            order_bys=[
                OrderBy(
                    dimension=OrderBy.DimensionOrderBy(
                        dimension_name=DEFAULT_CURSOR_FIELD,
                        order_type=OrderBy.DimensionOrderBy.OrderType.ALPHANUMERIC
                    )
                )
            ]
        )
        return client.run_report(request)
