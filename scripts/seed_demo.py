"""Run inside `odoo shell`; env is supplied by the shell command, not imported here."""
import os
from odoo import Command

def password(key):
    value = os.environ.get(key, '')
    if len(value) < 12 or value.startswith(('replace-', 'choose-')):
        raise ValueError('Set %s to your own password of at least 12 characters.' % key)
    return value

admin_password = password('WORKSHOP_ADMIN_PASSWORD')
customer_password = password('DEMO_CUSTOMER_PASSWORD')
technician_password = password('DEMO_TECHNICIAN_PASSWORD')
env.ref('base.user_admin').write({'password': admin_password})
env = env(user=env.ref('base.user_admin').id)

def upsert_user(login, name, secret, group):
    user = env['res.users'].with_context(active_test=False).search([('login', '=', login)], limit=1)
    values = {'name': name, 'login': login, 'email': login, 'password': secret,
              'company_id': env.company.id, 'company_ids': [Command.set([env.company.id])],
              'groups_id': [Command.set([env.ref(group).id])], 'active': True}
    if user:
        user.write(values)
    else:
        user = env['res.users'].with_context(no_reset_password=True).create(values)
    return user

customer = upsert_user(os.environ.get('DEMO_CUSTOMER_EMAIL', 'customer@example.com'),
    'Alex Customer', customer_password, 'base.group_portal')
technician = upsert_user(os.environ.get('DEMO_TECHNICIAN_EMAIL', 'technician@example.com'),
    'Arun Technician', technician_password, 'workshop_hub.group_technician')
customer.partner_id.workshop_customer = True
vehicle = env['workshop.vehicle'].search([('plate', '=', 'KL 10 AB 1234')], limit=1)
if not vehicle:
    vehicle = env['workshop.vehicle'].create({'plate': 'KL 10 AB 1234',
        'make_model': 'Toyota Corolla 2022', 'partner_id': customer.partner_id.id})
if not env['workshop.job'].search_count([('vehicle_id', '=', vehicle.id)]):
    job = env['workshop.job'].create({'partner_id': customer.partner_id.id,
        'vehicle_id': vehicle.id, 'technician_id': technician.id,
        'concern': 'Periodic service and a brake inspection before a long journey.'})
    job.action_prepare_quote()
    job.action_request_approval()
if not env['product.product'].search_count([('default_code', '=', 'WS-OIL-FILTER')]):
    env['product.product'].create({'name': 'Oil Filter', 'default_code': 'WS-OIL-FILTER',
        'type': 'consu', 'is_storable': True, 'list_price': 350, 'standard_price': 200,
        'invoice_policy': 'order'})
env.cr.commit()
print('Demo users and a quotation-ready job created. No artificial stock or payments were added.')
