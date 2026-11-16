import json
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user
from odoo import fields


@tagged('post_install', '-at_install', 'workshop_hub')
class ShopAPITests(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.secret = 'Workshop-Shop-Test-123'
        cls.customer = new_test_user(cls.env, login='shop.customer.test', groups='base.group_portal', password=cls.secret)
        cls.other = new_test_user(cls.env, login='shop.other.test', groups='base.group_portal', password=cls.secret)
        cls.tech = new_test_user(cls.env, login='shop.tech.test', groups='workshop_hub.group_technician', password=cls.secret)
        cls.product = cls.env['product.product'].create({'name': 'Shop Test Filter', 'default_code': 'SHOP-TEST',
            'type': 'consu', 'is_storable': True, 'sale_ok': True, 'invoice_policy': 'order',
            'list_price': 100, 'taxes_id': [(5, 0, 0)], 'workshop_shop_published': True,
            'workshop_compatibility': 'Test vehicle only'})
        cls.hidden = cls.env['product.product'].create({'name': 'Private part', 'type': 'consu', 'is_storable': True})
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(cls.product, cls.warehouse.lot_stock_id, 5)

    def rest(self, path, params=None, token=None, expected=200, extra_headers=None):
        headers = {'Content-Type': 'application/json', **(extra_headers or {})}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        response = self.url_open('/workshop/rest/' + path, data=json.dumps(params or {}), headers=headers)
        self.assertEqual(response.status_code, expected, response.text[:500])
        return response.json()

    def login(self, user=None):
        return self.rest('mobile/login', {'login': (user or self.customer).login, 'password': self.secret})['session_id']

    def checkout(self, token, cart):
        return self.rest('shop/checkout', {'order_id': cart['id'], 'version': cart['version'],
            'contact_name': 'Shop Test Customer', 'contact_phone': '1234567890'}, token)

    def test_rest_cookie_login_and_logout(self):
        self.rest('dashboard', expected=401)
        result = self.rest('auth/login', {'login': self.customer.login, 'password': self.secret})
        self.assertEqual(result['user']['role'], 'customer')
        self.assertNotIn('session_id', result)
        self.rest('dashboard')
        self.rest('auth/logout')
        self.rest('dashboard', expected=401)

    def test_native_session_origin_and_role_security(self):
        token = self.login()
        self.assertEqual(self.rest('me', token=token)['role'], 'customer')
        self.rest('shop/cart', token=token, expected=403, extra_headers={'Origin': 'https://attacker.example'})
        self.rest('res.users/write', token=token, expected=404)
        self.rest('parts', token=token, expected=403)
        self.rest('auth/logout', token=token)
        self.rest('me', token=token, expected=401)
        self.rest('shop/cart', token=self.login(self.tech), expected=403)

    def test_catalog_and_private_product(self):
        token = self.login()
        products = self.rest('shop/catalog', {'search': 'SHOP-TEST'}, token)['products']
        self.assertEqual([product['id'] for product in products], [self.product.id])
        self.assertEqual(products[0]['available'], 5)
        self.assertEqual(products[0]['price'], 100)
        self.rest('shop/cart/update', {'product_id': self.hidden.id, 'quantity': 1}, token, expected=403)

    def test_cart_is_persistent_scoped_and_server_priced(self):
        token = self.login()
        cart = self.rest('shop/cart/update', {'product_id': self.product.id, 'quantity': 2}, token)
        self.assertEqual(cart['total'], 200)
        again = self.rest('shop/cart', token=self.login())
        self.assertEqual(again['id'], cart['id'])
        self.assertEqual(again['lines'][0]['quantity'], 2)
        self.rest('shop/order', {'order_id': cart['id']}, self.login(self.other), expected=403)
        self.rest('shop/cart/update', {'product_id': self.product.id, 'quantity': 9999}, token, expected=400)
        self.rest('shop/cart/update', {'product_id': self.product.id, 'quantity': True}, token, expected=400)
        self.rest('shop/cart/update', {'product_id': self.product.id, 'quantity': 1, 'price_unit': 0.01}, token, expected=400)

    def test_checkout_reserves_stock_is_idempotent_and_cancel_releases_it(self):
        token = self.login()
        cart = self.rest('shop/cart/update', {'product_id': self.product.id, 'quantity': 2}, token)
        order = self.checkout(token, cart)
        self.assertEqual(order['status'], 'confirmed')
        self.assertEqual(order['total'], 200)
        repeated = self.checkout(token, cart)
        self.assertEqual(repeated['id'], order['id'])
        self.assertEqual(self.rest('shop/orders', token=token)['total'], 1)
        self.assertEqual(self.rest('shop/catalog', {'search': 'SHOP-TEST'}, token)['products'][0]['available'], 3)
        other = self.login(self.other)
        self.rest('shop/cancel', {'order_id': order['id']}, other, expected=403)
        self.rest('shop/invoice', {'order_id': order['id'], 'invoice_id': 1}, other, expected=403)
        self.assertEqual(self.rest('shop/cancel', {'order_id': order['id']}, token)['status'], 'cancelled')
        self.assertEqual(self.rest('shop/catalog', {'search': 'SHOP-TEST'}, token)['products'][0]['available'], 5)

    def test_stale_price_and_stock_changes_prevent_checkout(self):
        token = self.login()
        cart = self.rest('shop/cart/update', {'product_id': self.product.id, 'quantity': 2}, token)
        self.product.list_price = 120
        params = {'order_id': cart['id'], 'version': cart['version'], 'contact_name': 'Test Customer', 'contact_phone': '1234567890'}
        self.rest('shop/checkout', params, token, expected=400)
        fresh = self.rest('shop/cart', token=token)
        self.assertEqual(fresh['total'], 240)
        self.env['stock.quant']._update_available_quantity(self.product, self.warehouse.lot_stock_id, -4)
        params['version'] = fresh['version']
        self.rest('shop/checkout', params, token, expected=400)
        self.assertEqual(self.rest('shop/orders', token=token)['total'], 0)

    def test_expired_session_is_rejected(self):
        token = self.login()
        from odoo import http
        session = http.root.session_store.get(token)
        session['workshop_expires_at'] = 1
        http.root.session_store.save(session)
        self.rest('me', token=token, expected=401)

    def test_collected_order_cannot_be_cancelled(self):
        token = self.login()
        cart = self.rest('shop/cart/update', {'product_id': self.product.id, 'quantity': 1}, token)
        order = self.checkout(token, cart)
        record = self.env['sale.order'].browse(order['id'])
        for picking in record.picking_ids:
            for move in picking.move_ids:
                move.write({'quantity': move.product_uom_qty, 'picked': True})
            picking.button_validate()
        self.assertEqual(self.rest('shop/order', {'order_id': order['id']}, token)['status'], 'completed')
        self.rest('shop/cancel', {'order_id': order['id']}, token, expected=400)
