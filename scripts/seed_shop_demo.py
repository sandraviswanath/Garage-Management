"""Optional local-development fixture. Run with `odoo shell`; never on live business data."""
if not env['res.users'].search_count([('login', '=', 'customer@example.com')]):
    raise ValueError('This fixture is only for the seeded local demonstration database.')
warehouse = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
if not warehouse:
    raise ValueError('Configure a warehouse first.')
product = env['product.product'].search([('default_code', '=', 'SHOP-DEMO-FILTER')], limit=1)
if not product:
    product = env['product.product'].create({'name': 'Demo Shop Oil Filter', 'default_code': 'SHOP-DEMO-FILTER',
        'type': 'consu', 'is_storable': True, 'sale_ok': True, 'invoice_policy': 'order',
        'list_price': 35, 'standard_price': 15, 'workshop_shop_published': True,
        'workshop_compatibility': 'Demo product — verify fit with the workshop',
        'description_sale': 'Development sample for testing catalogue, cart and pickup orders.'})
    quant = env['stock.quant'].with_context(inventory_mode=True).create({'product_id': product.id,
        'location_id': warehouse.lot_stock_id.id, 'inventory_quantity': 10})
    quant.action_apply_inventory()
env.cr.commit()
print('Demo shop part available. Existing product quantities and real payment records were not changed.')
