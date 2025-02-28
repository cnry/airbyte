#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#
import logging
import re
from abc import ABC
from base64 import b64encode
from datetime import datetime, timezone
from parser import ParserError
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple, Union

import requests
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream
from airbyte_cdk.sources.streams.http.requests_native_auth import TokenAuthenticator
from dateutil.parser import parse

from source_dcl_logistics.models.order import Order

DEFAULT_CURSOR = "updated_at"
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


logger = logging.getLogger("airbyte")


# Basic full refresh stream
class DclLogisticsStream(HttpStream, ABC):
    url_base = "https://api.dclcorp.com/api/v1/"
    page_size = 100

    def __init__(self, **args):
        super(DclLogisticsStream, self).__init__(**args)

        self.next_page = 1
        self.has_more_pages = True
        self.importing_cancelled_orders = False

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        """
        Returns the next page from DCL

        :return: The token for the next page from the input response object. Returning `None` means there are no more pages.
        """
        if self.has_more_pages:
            self.next_page += 1
            return {"page": self.next_page}
        else:
            if not self.importing_cancelled_orders:
                self.next_page = 0
                self.has_more_pages = True
                self.importing_cancelled_orders = True

                return self.next_page_token(response=response)
            else:
                return None

    @staticmethod
    def parse_string_to_utc_timestamp(date_time_str: str, default: datetime) -> datetime:
        """
        Parses the given string to `datetime` in UTC timezone. If parsing failed in case of `None` is passed or the date is not valid,
        it returns the given default value

        :param date_time_str: The datetime string
        :param default: The default `datetime` value to be returned in case of exception thrown
        """
        try:
            date_time = parse(date_time_str)
        except (ParserError, TypeError):
            date_time = default

        return date_time.astimezone(timezone.utc)


# Basic incremental stream
class IncrementalDclLogisticsStream(DclLogisticsStream, ABC):
    @property
    def cursor_field(self) -> Union[str, List[str]]:
        return DEFAULT_CURSOR

    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]) -> Mapping[str, Any]:
        current_updated_at_str = (current_stream_state or {}).get(self.cursor_field)
        current_updated_at = self.parse_string_to_utc_timestamp(date_time_str=current_updated_at_str, default=datetime(1970, 1, 1))

        latest_record_updated_at_str = latest_record.get(self.cursor_field)
        latest_record_updated_at = self.parse_string_to_utc_timestamp(date_time_str=latest_record_updated_at_str, default=datetime.utcnow())

        return {self.cursor_field: max(latest_record_updated_at, current_updated_at).replace(tzinfo=None).isoformat(timespec="seconds")}


class Orders(IncrementalDclLogisticsStream):
    primary_key = ["account_number", "order_number", "item_number", "serial_number"]

    def __init__(self, modified_from: str = None, modified_to: str = None, **args):
        super(Orders, self).__init__(**args)

        self.modified_from = modified_from
        self.modified_to = modified_to

    def path(self, **kwargs) -> str:
        return "orders"

    def get_json_schema(self) -> Mapping[str, Any]:
        return Order.schema()

    def request_params(
        self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        page = next_page_token.get("page", 1) if next_page_token else 1

        params = {"page": page, "page_size": self.page_size, "extended_date": True}

        if self.importing_cancelled_orders:
            params.update({"status": 2}) # Cancelled orders https://api.dclcorp.com/Help/ResourceModel?modelName=status

        self.modified_from = (stream_state and stream_state[self.cursor_field]) or self.modified_from

        if self.modified_from:
            params.update({"modified_from": self.modified_from})

        if self.modified_to:
            params.update({"modified_to": self.modified_to})

        logger.info(f"Sending request with params: {params}")

        return params

    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        orders_json = response.json().get("orders")
        if orders_json:
            for order_json in orders_json:
                order = Order(
                    account_number=order_json.get("account_number"),
                    order_number=order_json.get("order_number"),
                    customer_number=order_json.get("customer_number"),
                    item_number="",
                    serial_number="",
                    order_type=order_json.get("order_type"),
                    updated_at=self.parse_string_to_utc_timestamp(order_json.get("modified_at"), default=datetime.utcnow())
                )

                shipping_address_json = order_json.get("shipping_address")

                if shipping_address_json:
                    order.country = shipping_address_json.get("country")
                    order.state_province = shipping_address_json.get("state_province")
                    order.city = shipping_address_json.get("city")
                    order.postal_code = shipping_address_json.get("postal_code")
                    order.company = shipping_address_json.get("company")
                    order.attention = shipping_address_json.get("attention")
                    order.email = shipping_address_json.get("email")

                orders_by_item_number = dict()
                for order_line_json in order_json.get("order_lines") or []:
                    sub_order = order.copy(deep=True)

                    sub_order.quantity = order_line_json.get("quantity")
                    sub_order.description = order_line_json.get("description")
                    sub_order.item_number = order_line_json.get("item_number")
                    sub_order.ship_date = order_line_json.get("ship_by")

                    orders_by_item_number[sub_order.item_number] = sub_order

                for shipment_json in order_json.get("shipments") or []:
                    for package_json in shipment_json.get("packages") or []:
                        for shipped_item_json in package_json.get("shipped_items") or []:
                            shipped_item_order = order.copy(deep=True)

                            shipped_item_order.carton_id = package_json.get("carton_id")
                            shipped_item_order.tracking_number = package_json.get("tracking_number")

                            ship_date = re.search(DATE_PATTERN, (shipment_json.get("ship_date") or ""))

                            shipped_item_order.quantity = shipped_item_json.get("quantity")
                            shipped_item_order.description = shipped_item_json.get("description")
                            shipped_item_order.item_number = shipped_item_json.get("item_number")
                            if ship_date:
                                shipped_item_order.ship_date = ship_date.group()
                            else:
                                shipped_item_order.ship_date = orders_by_item_number[shipped_item_order.item_number].ship_date

                            orders_by_item_number.pop(shipped_item_order.item_number, None)

                            if shipped_item_json.get("serial_numbers"):
                                for serial_number in shipped_item_json.get("serial_numbers"):
                                    order_with_serial_number = shipped_item_order.copy(deep=True)
                                    order_with_serial_number.serial_number = serial_number.upper()

                                    yield order_with_serial_number.__dict__
                            else:
                                shipped_item_order.serial_number = ""

                                yield shipped_item_order.__dict__

                for item_number, order in orders_by_item_number.items():
                    yield order.__dict__
        else:
            self.has_more_pages = False


# Source
class SourceDclLogistics(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        try:
            authenticator = self.authenticator(config=config)
            orders = Orders(authenticator=authenticator)

            test_url = f"{orders.url_base}{orders.path()}"
            response = requests.request("GET", url=test_url, headers=authenticator.get_auth_header())

            if response.ok:
                return True, None
            else:
                response.raise_for_status()
        except Exception as exception:
            return False, exception

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        modified_from = config.get("modified_from")
        modified_to = config.get("modified_to")

        return [Orders(authenticator=self.authenticator(config=config), modified_from=modified_from, modified_to=modified_to)]

    @staticmethod
    def authenticator(config: Mapping[str, Any]) -> TokenAuthenticator:
        """
        Returns the Basic Authentication Base64 encoded token

        :param config: the user-input config object conforming to the connector's spec.json

        :return TokenAuthenticator: The TokenAuthenticator
        """
        token = b64encode(f"{config['username']}:{config['password']}".encode()).decode()
        return TokenAuthenticator(token=token, auth_method="Basic")
