# -*- coding: utf-8 -*-

from .exchange_rate import ExchangeRate


class PriceCalculator():
  def __init__(self, price_rules=None, target_currency='USD', min_profit_amount=10, default_qty=50):
    self.rules = {
      'roi': 0.75,
      'ad_cost': 3,
      'transfer_cost': 0,
      'product_cost_rate': 0.5,
      'margin': 0.5,
      'tax_rate': 0.09
    }

    if price_rules:
      self.rules.update(price_rules)

    self.min_profit_amount = min_profit_amount
    self.default_qty = default_qty
    self.target_currency = target_currency
    self.exchange_rate = ExchangeRate.get_exchange_rate('USD', target_currency)

  def calc_offer(self, src_offer):
    if isinstance(src_offer, bool) and not src_offer:
      offer = False
    elif src_offer is None or src_offer.get('price', 0) == 0:
        offer = {
            'price': 0, 'quantity': 0, 'currency': self.target_currency,
            'src_price': 0, 'src_currency': self.target_currency
        }
    else:
      src_currency = src_offer.get('currency', 'USD')
      src_price_in_usd = src_offer['price']
      if src_currency != 'USD':
        exchange_rate = ExchangeRate.get_exchange_rate('USD', src_currency)
        src_price_in_usd = src_offer['price'] / exchange_rate
      src_price = src_price_in_usd * self.exchange_rate

      price_in_usd_amount = src_price_in_usd + self.rules['transfer_cost'] + self.min_profit_amount

      price_in_usd_margin = (self.rules['ad_cost'] + self.rules['transfer_cost'] + src_price_in_usd * (1 + self.rules['tax_rate'])) / (1 - self.rules['margin'])
      price_in_usd = max(price_in_usd_amount, price_in_usd_margin)
      price_by_margin = price_in_usd * self.exchange_rate

      cost = self.calc_cost(src_offer)
      price_by_product_cost = cost / self.rules['product_cost_rate'] + self.rules['ad_cost'] + self.rules['transfer_cost']
      price_by_product_cost = max(price_in_usd_amount * self.exchange_rate, price_by_product_cost)

      if price_by_margin > price_by_product_cost:
        price = price_by_product_cost
      else:
        price = price_by_margin

      src_quantity = src_offer.get('quantity', None)
      if src_quantity:
        quantity = src_quantity
      else:
        availability_type = src_offer.get('shipping_time', {}).get('availability_type', None)
        fba = src_offer.get('fba', False)
        if availability_type and availability_type.lower().find('now') == -1 and not fba:
          quantity = 0
        else:
          quantity = self.default_qty

      offer = {
          'price': round(price, 2), 'quantity': quantity, 'currency': self.target_currency,
          'src_price': src_price, 'src_currency': self.target_currency
      }

    return offer

  def calc_cost_usd(self, src_offer):
    if not src_offer or not src_offer.get('price', 0):
      return 0

    src_currency = src_offer.get('currency', 'USD')
    src_price_in_usd = src_offer['price']
    if src_currency != 'USD':
      exchange_rate = ExchangeRate.get_exchange_rate('USD', src_currency)
      src_price_in_usd = src_offer['price'] / exchange_rate

    return round(src_price_in_usd * (1 + self.rules['tax_rate']), 2)

  def calc_cost(self, src_offer):
    return round(self.calc_cost_usd(src_offer) * self.exchange_rate, 2)
