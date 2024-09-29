from decimal import Decimal

from hummingbot.client.config.config_validators import (
    validate_bool,
    validate_connector,
    validate_decimal,
    validate_int,
    validate_market_trading_pair,
)
from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.settings import AllConnectorSettings, required_exchanges, requried_connector_trading_pairs


def exchange_on_validated(value: str) -> None:
    required_exchanges.add(value)


def market_1_validator(value: str) -> None:
    exchange = boost_volume_config_map["connector_1"].value
    return validate_market_trading_pair(exchange, value)


def market_1_on_validated(value: str) -> None:
    requried_connector_trading_pairs[boost_volume_config_map["connector_1"].value] = [value]


def market_1_prompt() -> str:
    connector = boost_volume_config_map.get("connector_1").value
    example = AllConnectorSettings.get_example_pairs().get(connector)
    return "Enter the token trading pair you would like to trade on %s%s >>> " \
           % (connector, f" (e.g. {example})" if example else "")


def order_amount_from_prompt() -> str:
    trading_pair = boost_volume_config_map["market_1"].value
    base_asset, quote_asset = trading_pair.split("-")
    return f"What is the minimum amount of {base_asset} per order? >>> "


def order_amount_to_prompt() -> str:
    trading_pair = boost_volume_config_map["market_1"].value
    base_asset, quote_asset = trading_pair.split("-")
    return f"What is the maximum amount of {base_asset} per order? >>> "


boost_volume_config_map = {
    "strategy": ConfigVar(
        key="strategy",
        prompt="",
        default="boost_volume"),
    "connector_1": ConfigVar(
        key="connector_1",
        prompt="Enter your first connector (Exchange/AMM/CLOB) >>> ",
        prompt_on_new=True,
        validator=validate_connector,
        on_validated=exchange_on_validated),
    "market_1": ConfigVar(
        key="market_1",
        prompt=market_1_prompt,
        prompt_on_new=True,
        validator=market_1_validator,
        on_validated=market_1_on_validated),
    "order_amount_from": ConfigVar(
        key="order_amount_from",
        prompt=order_amount_from_prompt,
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0")),
        prompt_on_new=True),
    "order_amount_to": ConfigVar(
        key="order_amount_to",
        prompt=order_amount_to_prompt,
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0")),
        prompt_on_new=True),
    "delay_from": ConfigVar(
        key="delay_from",
        prompt="What is the minimum delay between orders? (Enter time in seconds) >>> ",
        default=0,
        validator=lambda v: validate_int(v, min_value=0, inclusive=True),
        type_str="int",
        prompt_on_new=True),
    "delay_range": ConfigVar(
        key="delay_range",
        prompt="What is the range of delay? (Enter time in seconds) >>> ",
        default=0,
        validator=lambda v: validate_int(v, min_value=0, inclusive=True),
        type_str="int",
        prompt_on_new=True),
    "market_1_slippage_buffer": ConfigVar(
        key="market_1_slippage_buffer",
        prompt="How much buffer do you want to add to the price to account for slippage for orders on the first market "
               "(Enter 1 for 1%)? >>> ",
        prompt_on_new=True,
        default=lambda: Decimal(1) if boost_volume_config_map["connector_1"].value in sorted(
            AllConnectorSettings.get_gateway_amm_connector_names().union(
                AllConnectorSettings.get_gateway_clob_connector_names()
            )
        ) else Decimal(0),
        validator=lambda v: validate_decimal(v),
        type_str="decimal"),
    "number_of_orders": ConfigVar(
        key="number_of_orders",
        prompt="How many orders do you want to place? >>> ",
        prompt_on_new=True,
        default=1,
        validator=lambda v: validate_int(v, min_value=1, inclusive=True),
        type_str="int"
    ),
    "debug_price_shim": ConfigVar(
        key="debug_price_shim",
        prompt="Do you want to enable the debug price shim for integration tests? If you don't know what this does "
               "you should keep it disabled. >>> ",
        default=False,
        validator=validate_bool,
        type_str="bool"),
    "gateway_transaction_cancel_interval": ConfigVar(
        key="gateway_transaction_cancel_interval",
        prompt="After what time should blockchain transactions be cancelled if they are not included in a block? "
               "(this only affects decentralized exchanges) (Enter time in seconds) >>> ",
        default=600,
        validator=lambda v: validate_int(v, min_value=1, inclusive=True),
        type_str="int"),
    "rate_oracle_enabled": ConfigVar(
        key="rate_oracle_enabled",
        prompt="Do you want to use the rate oracle? (Yes/No) >>> ",
        default=True,
        validator=validate_bool,
        type_str="bool"),
    "quote_conversion_rate": ConfigVar(
        key="quote_conversion_rate",
        prompt="What is the fixed_rate used to convert quote assets? >>> ",
        default=Decimal("1"),
        validator=lambda v: validate_decimal(v),
        type_str="decimal"),
}
