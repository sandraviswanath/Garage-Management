import ast
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('staff_policy',ROOT/'odoo/addons/workshop_hub/models/staff_policy.py')
policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)

class StaffPermissionTests(unittest.TestCase):
    def test_customer_cannot_use_any_staff_action(self):
        for action in policy.PERMISSIONS:
            with self.subTest(action=action):self.assertFalse(policy.allow('customer',action,'jobs'))

    def test_technician_cannot_manage_people_or_money(self):
        for action in ['customer.save','vehicle.save','job.save','user.save','payment.create','payment.refund','invoice.post','inventory.stock','part.issue','estimate.approve']:
            with self.subTest(action=action):self.assertFalse(policy.allow('technician',action))

    def test_technician_can_track_work(self):
        for action in ['task.update','job.state','note.add','timer.start','timer.stop','photo.save','part.request','part.use','check.update']:
            with self.subTest(action=action):self.assertTrue(policy.allow('technician',action))

    def test_reception_can_intake_but_cannot_post_finances(self):
        self.assertTrue(policy.allow('receptionist','customer.save'))
        self.assertTrue(policy.allow('receptionist','job.save'))
        self.assertTrue(policy.allow('receptionist','estimate.send'))
        for action in ['payment.create','invoice.post','user.save','estimate.approve']:
            self.assertFalse(policy.allow('receptionist',action))

    def test_accountant_can_bill_but_cannot_assign_jobs(self):
        for action in ['invoice.create','invoice.post','payment.create','payment.refund','report']:
            self.assertTrue(policy.allow('accountant',action))
        for action in ['job.save','job.state','user.save']:
            self.assertFalse(policy.allow('accountant',action))

    def test_user_administration_is_admin_only(self):
        self.assertTrue(policy.allow('admin','user.save'))
        for role in ['manager','receptionist','technician','accountant']:
            self.assertFalse(policy.allow(role,'user.save'))

    def test_read_permissions_cannot_be_bypassed_with_entity_name(self):
        self.assertTrue(policy.allow('technician','detail','jobs'))
        for entity in ['users','customers','inventory','payments','invoices']:
            self.assertFalse(policy.allow('technician','detail',entity))
        self.assertFalse(policy.allow('admin','detail','res.users'))

    def test_unknown_actions_denied(self):
        for role in policy.ALL:
            self.assertFalse(policy.allow(role,'arbitrary.model.write'))

    def test_original_route_inventory_is_preserved(self):
        rows=json.loads((ROOT/'docs/original-route-audit.json').read_text())
        self.assertEqual(len(rows),46)
        allowed_roots={'admin','manager','receptionist','accountant','technician','login','.'}
        for row in rows:
            self.assertIn(row['route'].strip('/').split('/')[0],allowed_roots)

    def test_all_staff_handlers_exist(self):
        tree=ast.parse((ROOT/'odoo/addons/workshop_hub/controllers/staff_api.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        methods={n.name for n in cls.body if isinstance(n,ast.FunctionDef)}
        base=ast.parse((ROOT/'odoo/addons/workshop_hub/controllers/api.py').read_text())
        inherited={n.name for node in base.body if isinstance(node,ast.ClassDef) for n in node.body if isinstance(n,ast.FunctionDef)}
        calls={n.attr for n in ast.walk(cls) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='self' and n.attr.startswith('_')}
        self.assertFalse(calls-methods-inherited)

if __name__=='__main__':unittest.main()
