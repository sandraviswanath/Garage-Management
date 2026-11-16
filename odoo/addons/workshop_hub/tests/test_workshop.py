import json
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user
from odoo.exceptions import AccessError, ValidationError

@tagged('post_install', '-at_install', 'workshop_hub')
class WorkshopIntegrationTests(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = new_test_user(cls.env, login='workshop.customer.test',
            groups='base.group_portal', password='Workshop-Test-Password-123')
        cls.other = new_test_user(cls.env, login='workshop.other.test',
            groups='base.group_portal', password='Workshop-Test-Password-123')
        cls.tech = new_test_user(cls.env, login='workshop.tech.test',
            groups='workshop_hub.group_technician', password='Workshop-Test-Password-123')
        cls.reception = new_test_user(cls.env,login='workshop.reception.test',groups='workshop_hub.group_receptionist',password='Workshop-Test-Password-123')
        cls.accountant = new_test_user(cls.env,login='workshop.accountant.test',groups='workshop_hub.group_accountant',password='Workshop-Test-Password-123')
        cls.vehicle = cls.env['workshop.vehicle'].create({'plate':'TEST-WS-101',
            'make_model':'Test Vehicle', 'partner_id':cls.customer.partner_id.id})
        cls.job = cls.env['workshop.job'].create({'partner_id':cls.customer.partner_id.id,
            'vehicle_id':cls.vehicle.id, 'concern':'Brake inspection required', 'technician_id':cls.tech.id})

    def rpc(self, path, params):
        response = self.url_open('/workshop/api/'+path,
            data=json.dumps({'jsonrpc':'2.0', 'method':'call', 'params':params, 'id':1}),
            headers={'Content-Type':'application/json'})
        return response.json()

    def test_other_customer_cannot_read_job(self):
        self.authenticate(self.other.login, 'Workshop-Test-Password-123')
        result = self.rpc('job', {'job_id':self.job.id})
        self.assertIn('error', result)
        self.assertIn('AccessError', result['error']['data']['name'])

    def test_customer_vehicle_registration_and_booking(self):
        self.authenticate(self.customer.login, 'Workshop-Test-Password-123')
        registered = self.rpc('vehicle', {'plate': 'CUSTOMER-APP-42', 'make_model': 'Honda City 2024'})
        self.assertNotIn('error', registered)
        vehicle_id = registered['result']['id']
        booked = self.rpc('request', {'vehicle_id': vehicle_id, 'concern': 'Please inspect the brake pads and service the vehicle.'})
        self.assertNotIn('error', booked)
        self.assertEqual(booked['result']['state'], 'requested')
        dashboard = self.rpc('dashboard', {})['result']
        self.assertIn(vehicle_id, [vehicle['id'] for vehicle in dashboard['vehicles']])
        self.assertIn(booked['result']['id'], [job['id'] for job in dashboard['jobs']])
        self.authenticate(self.other.login, 'Workshop-Test-Password-123')
        self.assertIn('error', self.rpc('request', {'vehicle_id': vehicle_id, 'concern': 'Trying to book another customer vehicle.'}))
        other = self.rpc('dashboard', {})['result']
        self.assertNotIn(vehicle_id, [vehicle['id'] for vehicle in other['vehicles']])
        self.assertNotIn(booked['result']['id'], [job['id'] for job in other['jobs']])

    def test_customer_cannot_access_other_customer_documents_or_approval(self):
        self.authenticate(self.other.login, 'Workshop-Test-Password-123')
        for path, params in [
            ('photo-get', {'job_id': self.job.id, 'photo_id': 1}),
            ('invoice', {'job_id': self.job.id, 'invoice_id': 1}),
            ('approve', {'job_id': self.job.id, 'version': 'forged-version'}),
        ]:
            result = self.rpc(path, params)
            self.assertIn('error', result)
            self.assertIn('AccessError', result['error']['data']['name'])

    def test_customer_approves_additional_work_during_repair(self):
        admin = self.env.ref('base.user_admin')
        admin.password = 'Workshop-Admin-Test-123'
        self.authenticate(admin.login, 'Workshop-Admin-Test-123')
        quote = self.staff_action('estimate.save', {'job_id': self.job.id,
            'lines': [{'description': 'Initial service', 'qty': 1, 'unit_price': 500}]})
        self.staff_action('estimate.approve', {'id': quote['id'], 'reason': 'Customer approved initial service.'})
        self.authenticate(self.tech.login, 'Workshop-Test-Password-123')
        self.assertNotIn('error', self.rpc('status', {'job_id': self.job.id, 'state': 'in_progress'}))
        self.authenticate(admin.login, 'Workshop-Admin-Test-123')
        extra = self.staff_action('estimate.save', {'job_id': self.job.id,
            'lines': [{'description': 'Additional inspection', 'qty': 1, 'unit_price': 150}]})
        self.staff_action('estimate.send', {'id': extra['id']})
        self.authenticate(self.customer.login, 'Workshop-Test-Password-123')
        job = self.rpc('job', {'job_id': self.job.id})['result']
        pending = next(quote for quote in job['pending_quotes'] if quote['id'] == extra['id'])
        self.assertIn('error', self.rpc('approve', {'job_id': self.job.id, 'order_id': extra['id'], 'version': 'stale'}))
        approved = self.rpc('approve', {'job_id': self.job.id, 'order_id': extra['id'], 'version': pending['version']})
        self.assertNotIn('error', approved)
        self.assertEqual(approved['result']['state'], 'in_progress')
        self.assertFalse(approved['result']['pending_quotes'])

    def test_customer_cannot_change_repair_status(self):
        self.authenticate(self.customer.login, 'Workshop-Test-Password-123')
        self.assertIn('error', self.rpc('status', {'job_id':self.job.id, 'state':'completed'}))

    def test_technician_cannot_self_approve(self):
        self.authenticate(self.tech.login, 'Workshop-Test-Password-123')
        self.assertIn('error', self.rpc('approve', {'job_id':self.job.id, 'version':''}))

    def test_vehicle_owner_validation(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['workshop.job'].create({'partner_id':self.other.partner_id.id,
                'vehicle_id':self.vehicle.id, 'concern':'Wrong owner'})

    def test_completion_requires_inspection(self):
        self.job.state = 'in_progress'
        with self.assertRaises(ValidationError):
            self.job._technician_update('completed')
        self.job.checklist_ids.write({'done':True})
        self.job._technician_update('completed')
        self.assertEqual(self.job.state, 'completed')

    def test_technician_direct_write_denied(self):
        with self.assertRaises(AccessError):
            self.job.with_user(self.tech).write({'state':'completed'})

    def test_pending_parts_prevent_completion(self):
        product = self.env.ref('workshop_hub.product_labour')
        self.env['workshop.part.request'].create({'job_id':self.job.id,
            'product_id':product.id, 'quantity':1})
        self.job.state = 'in_progress'
        self.job.checklist_ids.write({'done':True})
        with self.assertRaises(ValidationError):
            self.job._technician_update('completed')

    def test_customer_cannot_call_staff_api(self):
        self.authenticate(self.customer.login,'Workshop-Test-Password-123')
        self.assertIn('error',self.rpc('staff',{'action':'list','payload':{'entity':'customers'}}))

    def test_reception_cannot_record_payment(self):
        self.authenticate(self.reception.login,'Workshop-Test-Password-123')
        self.assertIn('error',self.rpc('staff',{'action':'payment.create','payload':{'invoice_id':1,'amount':100}}))

    def test_accountant_cannot_create_job(self):
        self.authenticate(self.accountant.login,'Workshop-Test-Password-123')
        self.assertIn('error',self.rpc('staff',{'action':'job.save','payload':{}}))

    def test_reception_customer_creation(self):
        self.authenticate(self.reception.login,'Workshop-Test-Password-123')
        result=self.rpc('staff',{'action':'customer.save','payload':{'name':'Reception Test Customer','phone':'1234567890'}})
        self.assertNotIn('error',result)
        self.assertEqual(result['result']['name'],'Reception Test Customer')

    def test_technician_cannot_list_users(self):
        self.authenticate(self.tech.login,'Workshop-Test-Password-123')
        self.assertIn('error',self.rpc('staff',{'action':'list','payload':{'entity':'users'}}))

    def test_cannot_start_two_work_timers(self):
        self.job.state='in_progress'
        self.authenticate(self.tech.login,'Workshop-Test-Password-123')
        params={'action':'timer.start','payload':{'job_id':self.job.id,'activity':'Inspection'}}
        self.assertNotIn('error',self.rpc('staff',params))
        self.assertIn('error',self.rpc('staff',params))

    def staff_action(self, action, payload):
        result = self.rpc('staff', {'action': action, 'payload': payload})
        self.assertNotIn('error', result, result.get('error'))
        return result['result']

    def test_quote_approval_and_repair_workflow(self):
        """Exercise the same APIs used by Next.js and the native application."""
        admin = self.env.ref('base.user_admin')
        admin.password = 'Workshop-Admin-Test-123'
        self.authenticate(admin.login, 'Workshop-Admin-Test-123')
        job = self.staff_action('task.save', {'job_id': self.job.id,
            'description': 'Inspect brakes', 'hours': 1, 'rate': 500})
        task_id = job['tasks'][0]['id']
        quote = self.staff_action('estimate.save', {'job_id': self.job.id,
            'lines': [{'description': 'Brake inspection', 'qty': 1, 'unit_price': 500}]})
        self.staff_action('estimate.send', {'id': quote['id']})
        self.authenticate(self.customer.login, 'Workshop-Test-Password-123')
        job = self.rpc('job', {'job_id': self.job.id})['result']
        self.assertIn('error', self.rpc('approve', {'job_id': self.job.id, 'version': 'stale'}))
        approved = self.rpc('approve', {'job_id': self.job.id, 'version': job['quote']['version']})
        self.assertEqual(approved['result']['state'], 'approved')
        self.authenticate(self.tech.login, 'Workshop-Test-Password-123')
        started = self.rpc('status', {'job_id': self.job.id, 'state': 'in_progress'})
        self.assertEqual(started['result']['state'], 'in_progress')
        self.staff_action('timer.start', {'job_id': self.job.id, 'activity': 'Brake inspection'})
        self.staff_action('note.add', {'job_id': self.job.id, 'content': 'Pads checked and road test completed.'})
        self.staff_action('task.update', {'job_id': self.job.id, 'id': task_id, 'state': 'completed'})
        for check in job['checks']:
            self.assertNotIn('error', self.rpc('check', {'job_id': self.job.id,
                'check_id': check['id'], 'done': True}))
        completed = self.rpc('status', {'job_id': self.job.id, 'state': 'completed'})
        self.assertEqual(completed['result']['state'], 'completed')
        self.assertTrue(all(timer['end'] for timer in completed['result']['timers']))

    def test_quoted_stock_is_issued_only_once(self):
        admin = self.env.ref('base.user_admin')
        admin.password = 'Workshop-Admin-Test-123'
        self.authenticate(admin.login, 'Workshop-Admin-Test-123')
        part = self.staff_action('inventory.save', {'name': 'Test oil filter', 'sku': 'TEST-FILTER',
            'quantity': 5, 'unit_cost': 100, 'retail_price': 200})
        quote = self.staff_action('estimate.save', {'job_id': self.job.id,
            'lines': [{'product_id': part['id'], 'qty': 2, 'unit_price': 200}]})
        self.staff_action('estimate.approve', {'id': quote['id'], 'reason': 'Customer approved in person.'})
        job = self.staff_action('part.request', {'job_id': self.job.id,
            'product_id': part['id'], 'quantity': 2})
        request_id = job['parts'][0]['id']
        for _ in range(2):
            self.staff_action('part.issue', {'job_id': self.job.id, 'id': request_id})
        inventory = self.staff_action('detail', {'entity': 'inventory', 'id': part['id']})
        self.assertEqual(inventory['quantity'], 3)
