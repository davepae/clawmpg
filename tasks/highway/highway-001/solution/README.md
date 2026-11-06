# shop

Tiny demo shop library (OER MVP seed repository).

## Modules

- `shop.pricing` - totals, discounts and bulk discounts
- `shop.tax` - tax calculation
- `shop.orders` - order placement
- `shop.reports` - summaries
- `shop.config` - settings

## Bulk discount

`bulk_discount(items, min_qty=10, percent=5)` reduces an order's total by
`percent` percent once the total quantity reaches `min_qty`.
`place_order(items, bulk=True)` applies it to the subtotal.

## Tests

```
pytest -q
```
