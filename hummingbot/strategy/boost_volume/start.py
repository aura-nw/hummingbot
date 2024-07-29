from decimal import Decimal

# from hummingbot.connector.gateway.amm.gateway_evm_amm import GatewayEVMAMM
# from hummingbot.connector.gateway.amm.gateway_tezos_amm import GatewayTezosAMM
# from hummingbot.connector.gateway.common_types import Chain
from hummingbot.core.rate_oracle.rate_oracle import RateOracle
from hummingbot.core.utils.fixed_rate_source import FixedRateSource
from hummingbot.strategy.boost_volume.boost_volume import BoostVolumeStrategy
from hummingbot.strategy.boost_volume.boost_volume_config_map import boost_volume_config_map
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple


# from typing import cast
def start(self):
    connector_1 = boost_volume_config_map.get("connector_1").value.lower()
    market_1 = boost_volume_config_map.get("market_1").value
    order_amount = boost_volume_config_map.get("order_amount").value
    market_1_slippage_buffer = boost_volume_config_map.get("market_1_slippage_buffer").value / Decimal("100")
    # debug_price_shim = boost_volume_config_map.get("debug_price_shim").value
    gateway_transaction_cancel_interval = boost_volume_config_map.get("gateway_transaction_cancel_interval").value
    rate_oracle_enabled = boost_volume_config_map.get("rate_oracle_enabled").value
    quote_conversion_rate = boost_volume_config_map.get("quote_conversion_rate").value

    self._initialize_markets([(connector_1, [market_1])])
    base_1, quote_1 = market_1.split("-")

    market_info_1 = MarketTradingPairTuple(self.markets[connector_1], market_1, base_1, quote_1)
    self.market_trading_pair_tuples = [market_info_1]

    # if debug_price_shim:
    #     amm_market_info: MarketTradingPairTuple = market_info_1
    #     if Chain.ETHEREUM.chain == amm_market_info.market.chain:
    #         amm_connector: GatewayEVMAMM = cast(GatewayEVMAMM, amm_market_info.market)
    #     elif Chain.TEZOS.chain == amm_market_info.market.chain:
    #         amm_connector: GatewayTezosAMM = cast(GatewayTezosAMM, amm_market_info.market)
    #     else:
    #         raise ValueError(f"Unsupported chain: {amm_market_info.market.chain}")

    if rate_oracle_enabled:
        rate_source = RateOracle.get_instance()
    else:
        rate_source = FixedRateSource()
        rate_source.add_rate(f"{quote_1}-{quote_1}", Decimal(str(quote_conversion_rate)))   # reverse rate is already handled in FixedRateSource find_rate method.

    self.strategy = BoostVolumeStrategy()
    self.strategy.init_params(market_info_1=market_info_1,
                              order_amount=order_amount,
                              market_1_slippage_buffer=market_1_slippage_buffer,
                              gateway_transaction_cancel_interval=gateway_transaction_cancel_interval,
                              rate_source=rate_source,
                              )
