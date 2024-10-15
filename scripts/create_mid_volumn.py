
from typing import Dict
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.core.data_type.common import OrderType
from decimal import Decimal
from datetime import datetime, timezone
import croniter
from hummingbot.strategy.strategy_py_base import (
    BuyOrderCompletedEvent,
    SellOrderCompletedEvent,
)
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.client.config.config_data_types import BaseClientModel, ClientFieldData
from pydantic import Field
import random
import os

class CreateMidVolumnConfig(BaseClientModel):
    script_file_name: str = Field(default_factory=lambda: os.path.basename(__file__))

    exchange: str = Field("gate_io_paper_trade", client_data=ClientFieldData(prompt_on_new=True, prompt=lambda mi: "Exchange where the bot will trade"))

    trading_pair: str = Field("AURA-USDT", client_data=ClientFieldData(
        prompt_on_new=True, prompt=lambda mi: "Trading pair in which the bot will place orders"))

    minimum_amount_limit : int = Field(400, client_data=ClientFieldData(prompt_on_new=True, prompt=lambda mi: "Minimum amount limit to random"))

    maximum_amount_limit : int = Field(400, client_data=ClientFieldData(prompt_on_new=True, prompt=lambda mi: "Maximum amount limit to random"))

    cron_expression: str = Field("* * * * *", client_data=ClientFieldData(prompt_on_new=True, prompt=lambda mi: "Cron expression to run"))
class CreateMidVolumn(ScriptStrategyBase):  
    numberBuyOrder = 0
    numberSellOrder = 0
    next_time = None

    def __init__(self, connectors: Dict[str, ConnectorBase], config: CreateMidVolumnConfig):
        super().__init__(connectors)
        self.config = config

    @classmethod
    def init_markets(cls, config: CreateMidVolumnConfig):
        cls.markets = {config.exchange: {config.trading_pair}}
    def on_tick(self):
        for connector_name, connector in self.connectors.items():
            current_time = datetime.now(tz=timezone.utc).timestamp()
            self.logger().debug(f"Current time: {current_time}, Next time: ${self.next_time}")
            if (self.next_time == None or current_time >= self.next_time):
                self.logger().debug('Satisfiy cron')

                # Cancel all active orders
                self.cancel_all_orders()
                mid_price = Decimal(connector.get_mid_price(self.config.trading_pair))
                self.logger().info(f"Mid price: {mid_price}")
                if (self.numberBuyOrder == 0 & self.numberSellOrder == 0):
                    amount = Decimal(random.randint(self.config.minimum_amount_limit, self.config.maximum_amount_limit))
                    self.buy(connector_name=connector_name,
                                amount=amount,
                                trading_pair=self.config.trading_pair,
                                order_type=OrderType.LIMIT,
                                price=mid_price,
                                )
                    self.numberBuyOrder += 1
                    self.sell(connector_name=connector_name,
                                amount=amount,
                                trading_pair=self.config.trading_pair,
                                order_type=OrderType.LIMIT,
                                price=mid_price)
                    self.numberSellOrder += 1

                cron = croniter.croniter(self.config.cron_expression, current_time)
                self.next_time = cron.get_next()
                self.logger().debug(f"Next time is {self.next_time}")
            else:
                self.logger().debug('Not satisfy cron')
    
    def did_complete_buy_order(self, event: BuyOrderCompletedEvent):
        self.numberBuyOrder -= 1

    def did_complete_sell_order(self, event: SellOrderCompletedEvent):
        self.numberSellOrder -=1
    
    def cancel_all_orders(self):
        for order in self.get_active_orders(connector_name=self.config.exchange):
            self.cancel(self.config.exchange, order.trading_pair, order.client_order_id)

    def on_stop(self):
        self.cancel_all_orders()