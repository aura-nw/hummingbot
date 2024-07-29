import asyncio
import logging
from decimal import Decimal
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple, cast

from hummingbot.client.settings import AllConnectorSettings, GatewayConnectionSetting
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.connector.gateway.amm.gateway_evm_amm import GatewayEVMAMM
from hummingbot.connector.gateway.gateway_price_shim import GatewayPriceShim
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.market_order import MarketOrder
from hummingbot.core.event.events import (
    BuyOrderCompletedEvent,
    MarketOrderFailureEvent,
    OrderCancelledEvent,
    OrderExpiredEvent,
    OrderType,
    SellOrderCompletedEvent,
)
from hummingbot.core.rate_oracle.rate_oracle import RateOracle
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.strategy_py_base import StrategyPyBase

NaN = float("nan")
s_decimal_zero = Decimal(0)
amm_logger = None


class BoostVolumeStrategy(StrategyPyBase):
    """
    This is a basic boosting strategy which can be used for most types of connectors (CEX, DEX or AMM).
    """

    _market_info_1: MarketTradingPairTuple
    _order_amount: Decimal
    _market_1_slippage_buffer: Decimal
    _number_of_orders: int
    _last_no_boost_reported: float
    _all_markets_ready: bool
    _ev_loop: asyncio.AbstractEventLoop
    _main_task: Optional[asyncio.Task]
    _last_timestamp: float
    _status_report_interval: float
    _quote_eth_rate_fetch_loop_task: Optional[asyncio.Task]
    _market_1_quote_eth_rate: None          # XXX (martin_kou): Why are these here?
    _rate_source: Optional[RateOracle]
    _cancel_outdated_orders_task: Optional[asyncio.Task]
    _gateway_transaction_cancel_interval: int

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global amm_logger
        if amm_logger is None:
            amm_logger = logging.getLogger(__name__)
        return amm_logger

    def init_params(self,
                    market_info_1: MarketTradingPairTuple,
                    order_amount: Decimal,
                    market_1_slippage_buffer: Decimal = Decimal("0"),
                    number_of_orders: int = 10,
                    status_report_interval: float = 900,
                    gateway_transaction_cancel_interval: int = 600,
                    rate_source: Optional[RateOracle] = RateOracle.get_instance(),
                    ):

        self._market_info_1 = market_info_1
        self._order_amount = order_amount
        self._market_1_slippage_buffer = market_1_slippage_buffer
        self._number_of_orders = number_of_orders
        self._last_no_boost_reported = 0
        self._all_boost_proposals = None
        self._all_markets_ready = False

        self._ev_loop = asyncio.get_event_loop()
        self._main_task = None

        self._last_timestamp = 0
        self._status_report_interval = status_report_interval
        self.add_markets([market_info_1.market])
        self._quote_eth_rate_fetch_loop_task = None

        self._rate_source = rate_source

        self._cancel_outdated_orders_task = None
        self._gateway_transaction_cancel_interval = gateway_transaction_cancel_interval

    @property
    def all_markets_ready(self) -> bool:
        return self._all_markets_ready

    @all_markets_ready.setter
    def all_markets_ready(self, value: bool):
        self._all_markets_ready = value

    @property
    def order_amount(self) -> Decimal:
        return self._order_amount

    @order_amount.setter
    def order_amount(self, value: Decimal):
        self._order_amount = value

    @property
    def rate_source(self) -> Optional[RateOracle]:
        return self._rate_source

    @rate_source.setter
    def rate_source(self, src: Optional[RateOracle]):
        self._rate_source = src

    @property
    def market_info_to_active_orders(self) -> Dict[MarketTradingPairTuple, List[LimitOrder]]:
        return self._sb_order_tracker.market_pair_to_active_orders

    @staticmethod
    @lru_cache(maxsize=10)
    def is_gateway_market(market_info: MarketTradingPairTuple) -> bool:
        return market_info.market.name in sorted(
            AllConnectorSettings.get_gateway_amm_connector_names()
        )

    @staticmethod
    @lru_cache(maxsize=10)
    def is_gateway_market_evm_compatible(market_info: MarketTradingPairTuple) -> bool:
        connector_spec: Dict[str, str] = GatewayConnectionSetting.get_connector_spec_from_market_name(market_info.market.name)
        return connector_spec["chain_type"] == "EVM"

    def tick(self, timestamp: float):
        """
        Clock tick entry point, is run every second (on normal tick setting).
        :param timestamp: current tick timestamp
        """
        if not self.all_markets_ready:
            self.all_markets_ready = all([market.ready for market in self.active_markets])
            if not self.all_markets_ready:
                if int(timestamp) % 10 == 0:  # prevent spamming by logging every 10 secs
                    unready_markets = [market for market in self.active_markets if market.ready is False]
                    for market in unready_markets:
                        msg = ', '.join([k for k, v in market.status_dict.items() if v is False])
                        self.logger().warning(f"{market.name} not ready: waiting for {msg}.")
                return
            else:
                self.logger().info("Markets are ready. Trading started.")

        if self.ready_for_new_boost_trades():
            if self._main_task is None or self._main_task.done():
                self._main_task = safe_ensure_future(self.main())
        # if self._cancel_outdated_orders_task is None or self._cancel_outdated_orders_task.done():
        #     self._cancel_outdated_orders_task = safe_ensure_future(self.apply_gateway_transaction_cancel_interval())

    async def main(self):
        # Get price of the first market
        market: GatewayEVMAMM = cast(GatewayEVMAMM, self._market_info_1.market)
        slippage_buffer: Decimal = self._market_1_slippage_buffer
        number_of_orders: int = self._number_of_orders
        """
        Execute a boost volume trade. If trade completes, it will place another trade. Until all trades are completed.
        """
        for i in range(number_of_orders):
            slippage_buffer_factor: Decimal = Decimal(1) + slippage_buffer
            # BUY
            price_1: Decimal = await market.get_order_price(self._market_info_1.trading_pair, True, self._order_amount, ignore_shim=True)
            price_1 = price_1.quantize(Decimal("0.000000001"))
            price_1 *= slippage_buffer_factor
            await self.place_boost_order(self._market_info_1, True, self._order_amount, price_1)
            await asyncio.sleep(2)
            # log done
            self.log_with_clock(logging.INFO, f"Placed buy order {i + 1}/{number_of_orders}")
            # SELL
            slippage_buffer_factor = Decimal(1) - slippage_buffer
            price_1: Decimal = await market.get_order_price(self._market_info_1.trading_pair, False, self._order_amount, ignore_shim=True)
            price_1 = price_1.quantize(Decimal("0.000000001"))
            price_1 *= slippage_buffer_factor
            await self.place_boost_order(self._market_info_1, False, self._order_amount, price_1)
            # Sleep for 5 seconds before placing another order
            await asyncio.sleep(2)
            # log done
            self.log_with_clock(logging.INFO, f"Placed sell order {i + 1}/{number_of_orders}")

    async def apply_gateway_transaction_cancel_interval(self):
        # XXX (martin_kou): Concurrent cancellations are not supported before the nonce architecture is fixed.
        # See: https://app.shortcut.com/coinalpha/story/24553/nonce-architecture-in-current-amm-trade-and-evm-approve-apis-is-incorrect-and-causes-trouble-with-concurrent-requests
        gateway_connectors = []
        if self.is_gateway_market(self._market_info_1) and self.is_gateway_market_evm_compatible(self._market_info_1):
            gateway_connectors.append(cast(GatewayEVMAMM, self._market_info_1.market))

        for gateway in gateway_connectors:
            await gateway.cancel_outdated_orders(self._gateway_transaction_cancel_interval)

    async def place_boost_order(
            self,
            market_info: MarketTradingPairTuple,
            is_buy: bool,
            amount: Decimal,
            order_price: Decimal) -> str:
        place_order_fn: Callable[[MarketTradingPairTuple, Decimal, OrderType, Decimal], str] = \
            cast(Callable, self.buy_with_specific_market if is_buy else self.sell_with_specific_market)

        # If I'm placing order under a gateway price shim, then the prices in the proposal are fake - I should fetch
        # the real prices before I make the order on the gateway side. Otherwise, the orders are gonna fail because
        # the limit price set for them will not match market prices.
        if self.is_gateway_market(market_info):
            slippage_buffer: Decimal = self._market_1_slippage_buffer
            slippage_buffer_factor: Decimal = Decimal(1) + slippage_buffer
            if not is_buy:
                slippage_buffer_factor = Decimal(1) - slippage_buffer
            market: GatewayEVMAMM = cast(GatewayEVMAMM, market_info.market)
            if GatewayPriceShim.get_instance().has_price_shim(
                    market.connector_name, market.chain, market.network, market_info.trading_pair):
                order_price = await market.get_order_price(market_info.trading_pair, is_buy, amount, ignore_shim=True)
                order_price *= slippage_buffer_factor

        return place_order_fn(market_info, amount, market_info.market.get_taker_order_type(), order_price)

    def ready_for_new_boost_trades(self) -> bool:
        """
        Returns True if there is no outstanding unfilled order.
        """
        # outstanding_orders = self.market_info_to_active_orders.get(self._market_info, [])
        for market_info in [self._market_info_1]:
            if len(self.market_info_to_active_orders.get(market_info, [])) > 0:
                return False
        return True

    def did_complete_buy_order(self, order_completed_event: BuyOrderCompletedEvent):
        self.set_order_completed(order_id=order_completed_event.order_id)

        market_info: MarketTradingPairTuple = self.order_tracker.get_market_pair_from_order_id(
            order_completed_event.order_id
        )
        log_msg: str = f"Buy order completed on {market_info.market.name}: {order_completed_event.order_id}."
        if self.is_gateway_market(market_info):
            log_msg += f" txHash: {order_completed_event.exchange_order_id}"
        self.log_with_clock(logging.INFO, log_msg)
        self.notify_hb_app_with_timestamp(f"Bought {order_completed_event.base_asset_amount:.8f} "
                                          f"{order_completed_event.base_asset}-{order_completed_event.quote_asset} "
                                          f"on {market_info.market.name}.")

    def did_complete_sell_order(self, order_completed_event: SellOrderCompletedEvent):
        self.set_order_completed(order_id=order_completed_event.order_id)

        market_info: MarketTradingPairTuple = self.order_tracker.get_market_pair_from_order_id(
            order_completed_event.order_id
        )
        log_msg: str = f"Sell order completed on {market_info.market.name}: {order_completed_event.order_id}."
        if self.is_gateway_market(market_info):
            log_msg += f" txHash: {order_completed_event.exchange_order_id}"
        self.log_with_clock(logging.INFO, log_msg)
        self.notify_hb_app_with_timestamp(f"Sold {order_completed_event.base_asset_amount:.8f} "
                                          f"{order_completed_event.base_asset}-{order_completed_event.quote_asset} "
                                          f"on {market_info.market.name}.")

    def did_fail_order(self, order_failed_event: MarketOrderFailureEvent):
        self.set_order_failed(order_id=order_failed_event.order_id)

    def did_cancel_order(self, cancelled_event: OrderCancelledEvent):
        self.set_order_completed(order_id=cancelled_event.order_id)

    def did_expire_order(self, expired_event: OrderExpiredEvent):
        self.set_order_completed(order_id=expired_event.order_id)

    @property
    def tracked_limit_orders(self) -> List[Tuple[ConnectorBase, LimitOrder]]:
        return self._sb_order_tracker.tracked_limit_orders

    @property
    def tracked_market_orders(self) -> List[Tuple[ConnectorBase, MarketOrder]]:
        return self._sb_order_tracker.tracked_market_orders

    def start(self, clock: Clock, timestamp: float):
        super().start(clock, timestamp)

    def stop(self, clock: Clock):
        if self._main_task is not None:
            self._main_task.cancel()
            self._main_task = None
        super().stop(clock)
