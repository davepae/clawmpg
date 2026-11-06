# shop

Tiny demo shop library (OER MVP seed repository).

## Modules

- `shop.pricing` - totals and discounts
- `shop.tax` - tax calculation
- `shop.orders` - order placement
- `shop.coupons` - coupon codes
- `shop.reports` - summaries
- `shop.config` - settings

## Coupons

`place_order(items, coupon="SAVE10")` applies a coupon after any percentage
discount and before tax. Codes are case-insensitive: `SAVE10` is 10% off,
`FLAT5` is 5 off (never below 0). Unknown codes raise
`shop.coupons.InvalidCoupon`. The result includes `net` and, when used, `coupon`.

## Tests

```
pytest -q
```
