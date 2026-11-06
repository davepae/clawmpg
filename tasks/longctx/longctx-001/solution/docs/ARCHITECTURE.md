# Architecture

The `shop` package prices orders.

- `shop.config` - settings. `TAX_RATE_PERCENT` is a percentage (8.0 means 8%).
- `shop.pricing` - `calc_total` sums price * qty; `apply_discount` applies a percentage discount.
- `shop.tax` - `apply_tax(amount, rate)` adds tax; `rate` is a fraction (0.08).
- `shop.orders` - `place_order` combines the above.
- `shop.reports` - summaries over lines and placed orders.

## Order total flow

1. `orders.place_order` computes the subtotal with `pricing.calc_total`.
2. An optional percentage discount is applied with `pricing.apply_discount`.
3. Tax is added with `tax.apply_tax`, passing `config.TAX_RATE_PERCENT / 100`
   because config stores a percentage but `apply_tax` expects a fraction.
4. `reports.daily_summary` sums the resulting `total` values.
