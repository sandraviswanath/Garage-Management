import base64
import hashlib
import json
import math
from odoo import Command, fields, http
from odoo.tools.float_utils import float_compare
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError
from .api import WorkshopAPI


class ShopAPI(http.Controller):
    """Customer parts sales use Odoo Sales, pricelists, taxes and stock reservations."""
    def _scope(self):
        WorkshopAPI()._require('customer')
        return request.env.user.partner_id, request.env.company

    def _warehouse(self):
        warehouse = request.env['stock.warehouse'].sudo().search([('company_id', '=', request.env.company.id)], limit=1)
        if not warehouse:
            raise ValidationError('The workshop must configure a stock warehouse before taking parts orders.')
        return warehouse

    def _products(self):
        self._scope()
        return request.env['product.product'].sudo().with_company(request.env.company).with_context(warehouse=self._warehouse().id)

    def _domain(self):
        return [('workshop_shop_published', '=', True), ('sale_ok', '=', True), ('active', '=', True),
            ('is_storable', '=', True), '|', ('company_id', '=', False), ('company_id', '=', request.env.company.id)]

    def _product(self, product_id):
        product = self._products().search(self._domain() + [('id', '=', int(product_id))], limit=1)
        if not product:
            raise AccessError('This part is not available in the customer shop.')
        return product

    def _product_data(self, product):
        partner, company = self._scope()
        pricelist = partner.with_company(company).property_product_pricelist
        price = pricelist._get_product_price(product, 1.0) if pricelist else product.lst_price
        return {'id': product.id, 'name': product.display_name, 'sku': product.default_code or '',
            'description': product.description_sale or '', 'category': product.categ_id.name,
            'compatibility': product.workshop_compatibility or '', 'price': price,
            'currency': (pricelist.currency_id or company.currency_id).name,
            'available': max(0, product.free_qty), 'unit': product.uom_id.name,
            'image': product.image_128.decode() if product.image_128 else None}

    def catalog(self, search='', category='', offset=0):
        products = self._products()
        domain = self._domain()
        text = str(search).strip()[:120]
        if text:
            domain += ['|', '|', ('name', 'ilike', text), ('default_code', 'ilike', text), ('workshop_compatibility', 'ilike', text)]
        if category:
            domain += [('categ_id.name', '=', str(category)[:120])]
        offset = max(0, int(offset))
        rows = products.search(domain, limit=24, offset=offset, order='name,id')
        categories = products.search(self._domain()).categ_id.mapped('name')
        return {'products': [self._product_data(p) for p in rows], 'total': products.search_count(domain),
            'offset': offset, 'limit': 24, 'categories': sorted(set(categories)), 'fulfillment': ['pickup'],
            'payment_methods': ['pay_at_workshop']}

    def _cart_record(self):
        partner, company = self._scope()
        # Serializes cart creation/updates across this customer's devices.
        request.env.cr.execute('SELECT id FROM res_partner WHERE id=%s FOR UPDATE', (partner.id,))
        model = request.env['sale.order'].sudo().with_company(company)
        cart = model.search([('partner_id', '=', partner.id), ('company_id', '=', company.id),
            ('workshop_shop_order', '=', True), ('state', '=', 'draft'), ('workshop_checkout_at', '=', False)], limit=1)
        if not cart:
            cart = model.create({'partner_id': partner.id, 'company_id': company.id,
                'warehouse_id': self._warehouse().id, 'workshop_shop_order': True, 'origin': 'Customer parts shop'})
        request.env.cr.execute('SELECT id FROM sale_order WHERE id=%s FOR UPDATE', (cart.id,))
        cart.invalidate_recordset()
        return cart

    def _version(self, order):
        return hashlib.sha256(json.dumps([order.id, order.state, str(order.write_date), order.amount_total,
            [(line.id, str(line.write_date), line.product_id.id, line.product_uom_qty,
              line.price_unit, line.discount, line.tax_id.ids) for line in order.order_line]], sort_keys=True).encode()).hexdigest()

    def _data(self, order):
        lines = order.order_line.filtered(lambda line: not line.display_type)
        delivered = bool(lines) and all(float_compare(line.qty_delivered, line.product_uom_qty,
            precision_rounding=line.product_uom.rounding) >= 0 for line in lines)
        partial = any(line.qty_delivered > 0 for line in lines)
        return {'id': order.id, 'name': order.name, 'state': order.state,
            'status': 'cancelled' if order.state == 'cancel' else 'completed' if delivered else 'partially_fulfilled' if partial else 'confirmed' if order.workshop_checkout_at else 'cart',
            'date': str(order.workshop_checkout_at or order.create_date), 'currency': order.currency_id.name,
            'subtotal': order.amount_untaxed, 'tax': order.amount_tax, 'total': order.amount_total,
            'version': self._version(order), 'fulfillment': 'pickup', 'payment_method': 'pay_at_workshop',
            'contact_name': order.workshop_collection_name or '', 'contact_phone': order.workshop_collection_phone or '',
            'note': order.workshop_shop_note or '', 'vehicle_id': order.workshop_shop_vehicle_id.id or None,
            'lines': [{'id': line.id, 'product_id': line.product_id.id, 'name': line.name, 'sku': line.product_id.default_code or '',
                'quantity': line.product_uom_qty, 'unit_price': line.price_unit, 'total': line.price_subtotal,
                'available': max(0, line.product_id.with_context(warehouse=order.warehouse_id.id).free_qty)}
                for line in order.order_line if not line.display_type],
            'can_cancel': bool(order.workshop_checkout_at and order.state == 'sale' and not order.locked and not order.picking_ids.filtered(lambda p: p.state == 'done')
                and not order.invoice_ids.filtered(lambda inv: inv.state == 'posted')),
            'invoices': [{'id': inv.id, 'name': inv.name, 'total': inv.amount_total, 'balance': inv.amount_residual,
                'payment_state': inv.payment_state, 'currency': inv.currency_id.name}
                for inv in order.invoice_ids if inv.state == 'posted' and inv.move_type == 'out_invoice']}

    def _refresh_prices(self, cart, validate=False):
        if validate:
            for line in cart.order_line:
                self._product(line.product_id.id)
        cart.with_context(pricelist_update=True)._recompute_prices()

    def cart(self):
        cart = self._cart_record()
        # The cart is re-priced by Odoo, never by values supplied by a client.
        self._refresh_prices(cart)
        return self._data(cart)

    def cart_update(self, product_id, quantity):
        cart = self._cart_record()
        if isinstance(quantity, bool):
            raise ValidationError('Enter a numeric quantity.')
        qty = float(quantity)
        if not math.isfinite(qty) or qty < 0 or qty > 999:
            raise ValidationError('Enter a quantity from 0 to 999.')
        product_id = int(product_id)
        line = cart.order_line.filtered(lambda item: item.product_id.id == product_id)
        if qty == 0:
            line.unlink()
            return self._data(cart)
        product = self._product(product_id)
        if qty > product.free_qty:
            raise ValidationError('Not enough stock for this quantity. Choose a lower quantity.')
        if line:
            line.write({'product_uom_qty': qty})
        else:
            cart.write({'order_line': [Command.create({'product_id': product.id, 'product_uom_qty': qty})]})
        self._refresh_prices(cart)
        return self._data(cart)

    def _order(self, order_id):
        partner, company = self._scope()
        order = request.env['sale.order'].sudo().search([('id', '=', int(order_id)),
            ('partner_id', '=', partner.id), ('company_id', '=', company.id), ('workshop_shop_order', '=', True)], limit=1)
        if not order:
            raise AccessError('Parts order not found for your account.')
        return order

    def checkout(self, order_id, version, contact_name, contact_phone, vehicle_id=None, note=''):
        order = self._order(order_id)
        request.env.cr.execute('SELECT id FROM sale_order WHERE id=%s FOR UPDATE', (order.id,))
        order.invalidate_recordset()
        if order.workshop_checkout_at:
            return self._data(order)  # Safe retry after a network timeout; no second order.
        if order.state != 'draft' or not order.order_line:
            raise ValidationError('Add parts to your cart before placing an order.')
        if len(str(contact_name).strip()) < 2 or not 5 <= len(str(contact_phone).strip()) <= 40:
            raise ValidationError('Enter a collection contact name and phone number.')
        if self._version(order) != version:
            raise ValidationError('Your cart changed. Refresh and review the latest totals before ordering.')
        before = [(line.product_id.id, line.price_unit, line.discount, line.tax_id.ids) for line in order.order_line]
        self._refresh_prices(order, validate=True)
        after = [(line.product_id.id, line.price_unit, line.discount, line.tax_id.ids) for line in order.order_line]
        if before != after:
            raise ValidationError('Prices changed. Refresh your cart and review the latest totals before ordering.')
        if vehicle_id:
            vehicle = request.env['workshop.vehicle'].sudo().search([('id', '=', int(vehicle_id)),
                ('partner_id', '=', order.partner_id.id), ('company_id', '=', order.company_id.id)], limit=1)
            if not vehicle:
                raise AccessError('Choose one of your own vehicles.')
        else:
            vehicle = request.env['workshop.vehicle']
        products = order.order_line.product_id.sorted('id')
        request.env.cr.execute('SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(products.ids),))
        products.invalidate_recordset(['free_qty'])
        for line in order.order_line:
            product = self._product(line.product_id.id)
            if line.product_uom_qty > product.free_qty:
                raise ValidationError('%s has insufficient stock. Refresh your cart.' % product.display_name)
        order.write({'workshop_checkout_at': fields.Datetime.now(), 'workshop_collection_name': str(contact_name).strip()[:120],
            'workshop_collection_phone': str(contact_phone).strip()[:40], 'workshop_shop_note': str(note)[:1000],
            'workshop_shop_vehicle_id': vehicle.id or False})
        order.action_confirm()
        for picking in order.picking_ids.filtered(lambda p: p.state not in ['done', 'cancel']):
            picking.action_assign()
            if picking.state != 'assigned':
                raise ValidationError('These parts could not be reserved. Please refresh your cart and try again.')
        order.message_post(body='Customer placed a parts order for collection and payment at the workshop. No online payment was collected.')
        return self._data(order)

    def orders(self, offset=0):
        partner, company = self._scope()
        domain = [('partner_id', '=', partner.id), ('company_id', '=', company.id), ('workshop_shop_order', '=', True), ('workshop_checkout_at', '!=', False)]
        model = request.env['sale.order'].sudo()
        offset = max(0, int(offset))
        return {'orders': [self._data(order) for order in model.search(domain, order='id desc', limit=20, offset=offset)],
            'total': model.search_count(domain), 'offset': offset, 'limit': 20}

    def order(self, order_id):
        return self._data(self._order(order_id))

    def cancel(self, order_id):
        order = self._order(order_id)
        request.env.cr.execute('SELECT id FROM sale_order WHERE id=%s FOR UPDATE', (order.id,))
        order.invalidate_recordset()
        if order.state == 'cancel':
            return self._data(order)
        if not self._data(order)['can_cancel']:
            raise ValidationError('This order can no longer be cancelled here. Contact the workshop.')
        order.with_context(disable_cancel_warning=True).action_cancel()
        return self._data(order)

    def shop_invoice(self, order_id, invoice_id):
        order = self._order(order_id)
        inv = order.invoice_ids.filtered(lambda item: item.id == int(invoice_id) and item.state == 'posted'
            and item.move_type == 'out_invoice' and item.partner_id == order.partner_id)
        if not inv:
            raise AccessError('Invoice not found for this parts order.')
        pdf, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf('account.account_invoices', res_ids=inv.ids)
        return {'name': 'parts-invoice-%s.pdf' % inv.id, 'content': base64.b64encode(pdf).decode()}
