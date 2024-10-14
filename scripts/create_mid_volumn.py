
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.core.data_type.common import OrderType
from decimal import Decimal
from datetime import datetime, timezone
import croniter
from hummingbot.strategy.strategy_py_base import (
    BuyOrderCompletedEvent,
    SellOrderCompletedEvent,
)
class CreateMidVolumn(ScriptStrategyBase):
    base = 'AURA'
    quote = 'USDT'
    trading_pair = f"{base}-{quote}"
    markets = {
        "gate_io": {f"{base}-{quote}"}
        # "mexc": {f"{base}-{quote}"}
    }
    
    numberBuyOrder = 0
    numberSellOrder = 0

    # minimum limit = 3 USDT
    miminumLimit = 3
    amount = Decimal(400)
    cron_expression = "* * * * *"
    cron = croniter.croniter(cron_expression)
    next_time = None

    def on_tick(self):
        for connector_name, connector in self.connectors.items():
            # self.logger().info(f"Connector: {connector_name}")
            # self.logger().info(f"Best ask: {connector.get_price(self.trading_pair, True)}")
            # self.logger().info(f"Best bid: {connector.get_price(self.trading_pair, False)}")
            current_time = datetime.now(tz=timezone.utc).timestamp()
            # previous_time = self.cron.get_prev(datetime)
            # next_time = self.cron.get_next(datetime)
            self.logger().debug(f"Current time: {current_time}, Next time: ${self.next_time}")
            if (self.next_time == None or current_time >= self.next_time):
                self.logger().debug('Satisfiy cron')

                active_orders = self.get_active_orders(
                    connector_name=connector_name,
                )
                for order in active_orders:
                    self.cancel(connector_name=connector_name,
                                trading_pair=self.trading_pair,
                                order_id=order)
                mid_price = Decimal(connector.get_mid_price(self.trading_pair))
                self.logger().info(f"Mid price: {mid_price}")

                if (self.numberBuyOrder == 0 & self.numberSellOrder == 0):
                    buyId = self.buy(connector_name=connector_name,
                                amount=self.amount,
                                trading_pair=self.trading_pair,
                                order_type=OrderType.LIMIT,
                                price=mid_price,
                                )
                    self.numberBuyOrder += 1
                    sellId = self.sell(connector_name=connector_name,
                                amount=self.amount,
                                trading_pair=self.trading_pair,
                                order_type=OrderType.LIMIT,
                                price=mid_price)
                    self.numberSellOrder += 1

                    # await asyncio.sleep(2)
                    # self.numberBuyOrder -=1
                    # self.numberSellOrder -=1

                cron = croniter.croniter(self.cron_expression, current_time)
                self.next_time = cron.get_next()
                self.logger().debug(f"Next time is {self.next_time}")
            else:
                self.logger().debug('Not satisfy cron')
    
    def did_complete_buy_order(self, event: BuyOrderCompletedEvent):
        self.numberBuyOrder -= 1

    def did_complete_sell_order(self, event: SellOrderCompletedEvent):
        self.numberSellOrder -=1