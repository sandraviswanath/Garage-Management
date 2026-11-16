from odoo import fields, models


class ShopProduct(models.Model):
    _inherit = 'product.template'
    workshop_shop_published = fields.Boolean('Sell in customer parts shop', default=False, index=True)
    workshop_compatibility = fields.Char('Vehicle compatibility', help='Make/model/engine or OEM references; verify fit before ordering.')


class ShopOrder(models.Model):
    _inherit = 'sale.order'
    workshop_shop_order = fields.Boolean('Customer parts order', default=False, copy=False, index=True)
    workshop_checkout_at = fields.Datetime('Customer checkout time', copy=False)
    workshop_collection_name = fields.Char('Collection contact')
    workshop_collection_phone = fields.Char('Collection phone')
    workshop_shop_note = fields.Text('Customer order note')
    workshop_shop_vehicle_id = fields.Many2one('workshop.vehicle', string='Customer vehicle', copy=False)

    def init(self):
        self.env.cr.execute('''CREATE UNIQUE INDEX IF NOT EXISTS workshop_one_shop_cart
            ON sale_order (partner_id, company_id)
            WHERE workshop_shop_order AND state = 'draft' AND workshop_checkout_at IS NULL''')
