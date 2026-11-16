from odoo import fields, models, api
from odoo.exceptions import ValidationError

class Partner(models.Model):
    _inherit = 'res.partner'
    workshop_customer = fields.Boolean(index=True)
    workshop_status = fields.Selection([('active','Active'),('inactive','Inactive')], default='active')

class User(models.Model):
    _inherit = 'res.users'
    workshop_specialization = fields.Char()

class Vehicle(models.Model):
    _inherit = 'workshop.vehicle'
    active = fields.Boolean(default=True)
    status = fields.Selection([('active','Active'),('inactive','Inactive'),('pending','Pending')], default='active')
    vehicle_type = fields.Char(default='car')
    make = fields.Char()
    model = fields.Char()
    year = fields.Integer()
    chassis_number = fields.Char()
    engine_number = fields.Char()
    km_reading = fields.Float()

class Job(models.Model):
    _inherit = 'workshop.job'
    active = fields.Boolean(default=True)
    job_type = fields.Selection([('repair','Repair'),('service','Service'),('inspection','Inspection'),('custom','Custom')], default='service', required=True)
    priority = fields.Selection([('low','Low'),('medium','Medium'),('high','High'),('urgent','Urgent')], default='medium')
    expected_completion = fields.Datetime()
    completed_at = fields.Datetime(readonly=True)
    diagnosis = fields.Text()
    instructions = fields.Text()
    quality_rating = fields.Float(help='Manager review score, from 0 to 5.')
    task_ids = fields.One2many('workshop.task','job_id')
    quote_ids = fields.One2many('sale.order','workshop_job_id')
    note_ids = fields.One2many('workshop.note','job_id')
    time_ids = fields.One2many('workshop.time','job_id')
    state = fields.Selection(selection_add=[('assigned','Assigned'),('paused','Paused')], ondelete={'assigned':'set default','paused':'set default'})

    @api.constrains('quality_rating')
    def _check_rating(self):
        for job in self:
            if not 0 <= job.quality_rating <= 5:
                raise ValidationError('Quality rating must be from 0 to 5.')

class Task(models.Model):
    _name = 'workshop.task'
    _description = 'Workshop Labour Task'
    _order = 'sequence,id'
    job_id = fields.Many2one('workshop.job', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    description = fields.Char(required=True)
    hours = fields.Float(default=1)
    rate = fields.Float()
    state = fields.Selection([('pending','Pending'),('in_progress','In progress'),('completed','Completed')], default='pending', required=True)
    notes = fields.Text()

class Note(models.Model):
    _name = 'workshop.note'
    _description = 'Workshop Technician Note'
    _order = 'create_date desc,id desc'
    job_id = fields.Many2one('workshop.job', required=True, ondelete='cascade')
    author_id = fields.Many2one('res.users', required=True)
    content = fields.Text(required=True)
    kind = fields.Selection([('progress','Progress'),('issue','Issue'),('resolution','Resolution')], default='progress', required=True)

class Time(models.Model):
    _name = 'workshop.time'
    _description = 'Workshop Work Timer'
    _order = 'start desc,id desc'
    job_id = fields.Many2one('workshop.job', required=True, ondelete='cascade')
    technician_id = fields.Many2one('res.users', required=True)
    activity = fields.Char(required=True)
    start = fields.Datetime(required=True, default=fields.Datetime.now)
    end = fields.Datetime()
    minutes = fields.Float(compute='_compute_minutes', store=True)

    @api.depends('start','end')
    def _compute_minutes(self):
        for line in self:
            line.minutes = max(0, (line.end-line.start).total_seconds()/60) if line.start and line.end else 0

class Photo(models.Model):
    _inherit = 'workshop.photo'
    kind = fields.Selection([('before','Before'),('during','During'),('after','After'),('issue','Issue')], default='during', required=True)
    description = fields.Char()
    author_id = fields.Many2one('res.users', default=lambda self:self.env.user)

class PartRequest(models.Model):
    _inherit = 'workshop.part.request'
    used = fields.Boolean()

class Product(models.Model):
    _inherit = 'product.template'
    workshop_min_stock = fields.Float()
    workshop_max_stock = fields.Float()
    workshop_bin = fields.Char()
    workshop_supplier_id = fields.Many2one('res.partner')

class Payment(models.Model):
    _inherit = 'account.payment'
    workshop_invoice_id = fields.Many2one('account.move', index=True, copy=False)
    workshop_method = fields.Selection([('cash','Cash'),('bank','Bank transfer'),('card','Card'),('check','Cheque'),('other','Other')], default='cash')
    workshop_reference = fields.Char()
    workshop_transaction = fields.Char()
    workshop_last4 = fields.Char(size=4)
    workshop_bank = fields.Char()
    workshop_notes = fields.Text()
    workshop_refund_of_id = fields.Many2one('account.payment', copy=False)

class Move(models.Model):
    _inherit = 'account.move'
    workshop_job_id = fields.Many2one('workshop.job', copy=False, index=True)
    workshop_discount_amount = fields.Monetary()

class Sale(models.Model):
    _inherit = 'sale.order'
    workshop_job_id = fields.Many2one('workshop.job', copy=False, index=True)
    workshop_discount_amount = fields.Monetary()
