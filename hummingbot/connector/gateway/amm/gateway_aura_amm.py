import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.gateway.amm.gateway_evm_amm import GatewayEVMAMM
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.trade_fee import TokenAmount
from hummingbot.core.event.events import TradeType
from hummingbot.core.gateway import check_transaction_exceptions
from hummingbot.core.utils.async_utils import safe_ensure_future
if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class GatewayAuraAMM(GatewayEVMAMM):
    """
    Defines basic functions common to connectors that interact with Gateway.
    """
    UPDATE_BALANCE_INTERVAL = 1.0
    API_CALL_TIMEOUT = 60.0
    POLL_INTERVAL = 15.0

    def __init__(self,
                 client_config_map: "ClientConfigAdapter",
                 connector_name: str,
                 chain: str,
                 network: str,
                 address: str,
                 trading_pairs: List[str] = [],
                 additional_spenders: List[str] = [],  # not implemented
                 trading_required: bool = True
                 ):
        """
        :param connector_name: name of connector on gateway
        :param chain: refers to a block chain, e.g. ethereum or avalanche
        :param network: refers to a network of a particular blockchain e.g. mainnet or kovan
        :param address: the address of the eth wallet which has been added on gateway
        :param trading_pairs: a list of trading pairs
        :param trading_required: Whether actual trading is needed. Useful for some functionalities or commands like the balance command
        """
        super().__init__(client_config_map=client_config_map,
                         connector_name=connector_name,
                         chain=chain,
                         network=network,
                         address=address,
                         trading_pairs=trading_pairs,
                         additional_spenders=additional_spenders,
                         trading_required=trading_required)

    async def start_network(self):
        if self._trading_required:
            self._status_polling_task = safe_ensure_future(self._status_polling_loop())
            # self._update_allowances = safe_ensure_future(self.update_allowances())
            self._get_gas_estimate_task = safe_ensure_future(self.get_gas_estimate())
        self._get_chain_info_task = safe_ensure_future(self.get_chain_info())

    async def stop_network(self):
        if self._status_polling_task is not None:
            self._status_polling_task.cancel()
            self._status_polling_task = None
        if self._get_chain_info_task is not None:
            self._get_chain_info_task.cancel()
            self._get_chain_info_task = None
        if self._get_gas_estimate_task is not None:
            self._get_gas_estimate_task.cancel()
            self._get_chain_info_task = None
    @property
    def ready(self):
        return all(self.status_dict.values())

    @property
    def status_dict(self) -> Dict[str, bool]:
        return {
            "account_balance": len(self._account_balances) > 0 if self._trading_required else True,
            "native_currency": self._native_currency is not None,
            # "network_transaction_fee": self.network_transaction_fee is not None if self._trading_required else True,
        }

    async def get_chain_info(self):
        """
        Calls the base endpoint of the connector on Gateway to know basic info about chain being used.
        """
        try:
            self._chain_info = await self._get_gateway_instance().get_network_status(
                chain=self.chain, network=self.network
            )
            if not isinstance(self._chain_info, list):
                self._native_currency = self._chain_info.get("nativeCurrency", "XTZ")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger().network(
                "Error fetching chain info",
                exc_info=True,
                app_warning_msg=str(e)
            )

    def parse_price_response(
        self,
        base: str,
        quote: str,
        amount: Decimal,
        side: TradeType,
        price_response: Dict[str, Any],
        process_exception: bool = True
    ) -> Optional[Decimal]:
        """
        Parses price response
        :param base: The base asset
        :param quote: The quote asset
        :param amount: amount
        :param side: trade side
        :param price_response: Price response from Gateway.
        :param process_exception: Flag to trigger error on exception
        """
        required_items = ["price", "gasLimit", "gasPrice", "gasCost", "gasPriceToken"]
        if any(item not in price_response.keys() for item in required_items):
            if "info" in price_response.keys():
                self.logger().info(f"Unable to get price. {price_response['info']}")
            else:
                self.logger().info(f"Missing data from price result. Incomplete return result for ({price_response.keys()})")
        else:
            gas_price_token: str = price_response["gasPriceToken"]
            gas_cost: Decimal = Decimal(price_response["gasCost"])
            price: Decimal = Decimal(price_response["price"])
            self.network_transaction_fee = TokenAmount(gas_price_token, gas_cost)
            if process_exception is True:
                gas_limit: int = int(price_response["gasLimit"])
                exceptions: List[str] = check_transaction_exceptions(
                    allowances=self._allowances,
                    balances=self._account_balances,
                    base_asset=base,
                    quote_asset=quote,
                    amount=amount,
                    side=side,
                    gas_limit=gas_limit,
                    gas_cost=gas_cost,
                    gas_asset=gas_price_token,
                    swaps_count=len(price_response.get("swaps", [])),
                    chain=self.chain
                )
                for index in range(len(exceptions)):
                    self.logger().warning(
                        f"Warning! [{index + 1}/{len(exceptions)}] {side} order - {exceptions[index]}"
                    )
                if len(exceptions) > 0:
                    return None
            return Decimal(str(price))
        return None

    async def cancel_all(self, timeout_seconds: float) -> List[CancellationResult]:
        """
        This is intentionally left blank, because cancellation is not supported for tezos blockchain.
        """
        return []

    async def _execute_cancel(self, order_id: str, cancel_age: int) -> Optional[str]:
        """
        This is intentionally left blank, because cancellation is not supported for tezos blockchain.
        """
        pass

    async def cancel_outdated_orders(self, cancel_age: int) -> List[CancellationResult]:
        """
        This is intentionally left blank, because cancellation is not supported for tezos blockchain.
        """
        return []

    async def update_allowances(self):
        pass

    async def get_allowances(self):
        pass

    async def all_trading_pairs(self):
        pass