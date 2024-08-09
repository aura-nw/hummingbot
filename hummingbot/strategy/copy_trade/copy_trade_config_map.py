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
    exchange = copy_trade_config_map["connector_1"].value
    return validate_market_trading_pair(exchange, value)


def validate_ethereum_wallet_address(value: str) -> None:
    if not value.startswith("0x") or len(value) != 42:
        raise ValueError("Invalid Ethereum wallet address.")


def validate_type_of_copy(value: str) -> None:
    if value not in {"percentage", "fixed_amount"}:
        raise ValueError("Invalid type of copy.")


def market_1_on_validated(value: str) -> None:
    requried_connector_trading_pairs[copy_trade_config_map["connector_1"].value] = [value]


def market_1_prompt() -> str:
    connector = copy_trade_config_map.get("connector_1").value
    example = AllConnectorSettings.get_example_pairs().get(connector)
    return "Enter the token trading pair you would like to trade on %s%s >>> " \
           % (connector, f" (e.g. {example})" if example else "")


def order_amount_from_prompt() -> str:
    trading_pair = copy_trade_config_map["market_1"].value
    base_asset, quote_asset = trading_pair.split("-")
    return f"What is the minimum amount of {base_asset} per order? >>> "


def order_amount_to_prompt() -> str:
    trading_pair = copy_trade_config_map["market_1"].value
    base_asset, quote_asset = trading_pair.split("-")
    return f"What is the maximum amount of {base_asset} per order? >>> "


copy_trade_config_map = {
    "strategy": ConfigVar(
        key="strategy",
        prompt="",
        default="copy_trade"),
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
    "wallet_to_copy": ConfigVar(
        key="wallet_to_copy",
        prompt="Enter the wallet address to copy trades >>> ",
        prompt_on_new=True,
        validator=validate_ethereum_wallet_address,
        type_str="str"),
    "type_of_copy": ConfigVar(
        key="type_of_copy",
        prompt="Enter the type of copy (percentage/fixed_amount) >>> ",
        prompt_on_new=True,
        validator= validate_type_of_copy),
    "percentage": ConfigVar(
        key="percentage",
        prompt="Enter the percentage of the trade to copy (Enter 1 for 1%) >>> ",
        prompt_on_new=True,
        required_if=lambda: copy_trade_config_map.get("type_of_copy").value == "percentage",
        default=Decimal(0),
        validator=lambda v: validate_decimal(v),
        type_str="decimal"),
    "fixed_amount": ConfigVar(
        key="copy_fixed_amount",
        prompt="Enter the fixed amount of the trade to copy >>> ",
        prompt_on_new=True,
        required_if=lambda: copy_trade_config_map.get("type_of_copy").value == "fixed_amount",
        default=Decimal(0),
        validator=lambda v: validate_decimal(v),
        type_str="decimal"),
    "market_1_slippage_buffer": ConfigVar(
        key="market_1_slippage_buffer",
        prompt="How much buffer do you want to add to the price to account for slippage for orders on the first market "
               "(Enter 1 for 1%)? >>> ",
        prompt_on_new=True,
        default=lambda: Decimal(1) if copy_trade_config_map["connector_1"].value in sorted(
            AllConnectorSettings.get_gateway_amm_connector_names().union(
                AllConnectorSettings.get_gateway_clob_connector_names()
            )
        ) else Decimal(0),
        validator=lambda v: validate_decimal(v),
        type_str="decimal"),
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
        default=False,
        validator=validate_bool,
        type_str="bool"),
    "quote_conversion_rate": ConfigVar(
        key="quote_conversion_rate",
        prompt="What is the fixed_rate used to convert quote assets? >>> ",
        default=Decimal("1"),
        validator=lambda v: validate_decimal(v),
        type_str="decimal"),
}
