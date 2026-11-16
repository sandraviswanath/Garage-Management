from odoo import api, fields, models, Command, _
from odoo.exceptions import AccessError, ValidationError
from .policy import technician_transition, positive_quantity


class WorkshopVehicle(models.Model):
    _name = 'workshop.vehicle'
    _description = 'Customer Vehicle'
    _rec_name = 'plate'

    plate = fields.Char(required=True, index=True)
    make_model = fields.Char(required=True)
    partner_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    job_ids = fields.One2many('workshop.job', 'vehicle_id')
    _sql_constraints = [('plate_company_unique', 'unique(plate, company_id)', 'Vehicle plate already exists.')]


class WorkshopJob(models.Model):
    _name = 'workshop.job'
    _description = 'Workshop Job Card'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', required=True, tracking=True)
    vehicle_id = fields.Many2one('workshop.vehicle', required=True, ondelete='restrict')
    concern = fields.Text(required=True)
    appointment_date = fields.Date()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    technician_id = fields.Many2one('res.users', tracking=True,
        domain=lambda self: [('groups_id', 'in', [self.env.ref('workshop_hub.group_technician').id])])
    state = fields.Selection([
        ('requested', 'Requested'), ('awaiting_approval', 'Awaiting approval'),
        ('approved', 'Approved'), ('in_progress', 'In progress'),
        ('waiting_parts', 'Waiting for parts'), ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='requested', required=True, tracking=True)
    sale_order_id = fields.Many2one('sale.order', readonly=True, copy=False)
    lead_id = fields.Many2one('crm.lead', readonly=True, copy=False)
    checklist_ids = fields.One2many('workshop.check', 'job_id')
    photo_ids = fields.One2many('workshop.photo', 'job_id')
    part_ids = fields.One2many('workshop.part.request', 'job_id')

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            values['name'] = self.env['ir.sequence'].next_by_code('workshop.job') or 'New'
        jobs = super().create(values_list)
        for job in jobs:
            job.checklist_ids = [Command.create({'name': label}) for label in
                ['Vehicle condition recorded', 'Repair checks completed', 'Final quality check']]
        return jobs

    @api.constrains('vehicle_id', 'partner_id', 'company_id', 'technician_id', 'sale_order_id')
    def _check_relationships(self):
        for job in self:
            if job.vehicle_id.partner_id != job.partner_id or job.vehicle_id.company_id != job.company_id:
                raise ValidationError(_('The vehicle must belong to the job customer and company.'))
            if job.sale_order_id and (job.sale_order_id.partner_id != job.partner_id or job.sale_order_id.company_id != job.company_id):
                raise ValidationError(_('The quotation must belong to this customer and company.'))
            if job.technician_id and (not job.technician_id.has_group('workshop_hub.group_technician')
                    or job.company_id not in job.technician_id.company_ids):
                raise ValidationError(_('Choose a workshop technician with access to this company.'))

    def _require_manager(self):
        if not self.env.user.has_group('workshop_hub.group_manager'):
            raise AccessError(_('Only a workshop manager can perform this action.'))
        self.check_access('write')

    def action_prepare_quote(self):
        self.ensure_one()
        self._require_manager()
        if self.state != 'requested':
            raise ValidationError(_('Prepare a quotation only for a requested job.'))
        if not self.sale_order_id:
            product = self.env.ref('workshop_hub.product_labour')
            order = self.env['sale.order'].create({
                'partner_id': self.partner_id.id, 'company_id': self.company_id.id,
                'origin': self.name, 'workshop_job_id': self.id,
                'order_line': [Command.create({
                    'product_id': product.id, 'name': 'Workshop labour - ' + self.name,
                    'product_uom_qty': 1, 'price_unit': product.lst_price,
                })],
            })
            self.sale_order_id = order
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order',
                'view_mode': 'form', 'res_id': self.sale_order_id.id}

    def action_request_approval(self):
        self.ensure_one()
        self._require_manager()
        if self.state != 'requested' or not self.sale_order_id or self.sale_order_id.state not in ['draft', 'sent']:
            raise ValidationError(_('Prepare a draft quotation first.'))
        if not self.sale_order_id.order_line:
            raise ValidationError(_('Add at least one quotation line.'))
        self.state = 'awaiting_approval'

    def _approve_customer_quote(self):
        """Controller verifies owner before elevation; private to block generic RPC."""
        self.ensure_one()
        if self.state == 'approved':
            return
        if self.state != 'awaiting_approval' or self.sale_order_id.state not in ['draft', 'sent']:
            raise ValidationError(_('This quotation is no longer awaiting approval.'))
        self.sale_order_id.action_confirm()
        self.state = 'approved'
        self.message_post(body='Customer approved the quotation through the portal.')

    def _technician_update(self, target, note=''):
        self.ensure_one()
        try:
            technician_transition(self.state, target)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if target == 'completed':
            if self.quote_ids.filtered(lambda order:order.state in ['draft','sent']):
                raise ValidationError(_('Resolve draft or pending quotations before completing this job.'))
            if any(task.state != 'completed' for task in self.task_ids):
                raise ValidationError(_('Complete all labour tasks first.'))
            if any(not line.done for line in self.checklist_ids):
                raise ValidationError(_('Complete every inspection check first.'))
            if any(line.state == 'requested' for line in self.part_ids):
                raise ValidationError(_('Ask the manager to issue or reject pending parts first.'))
        if target in ['paused', 'waiting_parts', 'completed']:
            self.time_ids.filtered(lambda t: not t.end).write({'end': fields.Datetime.now()})
        if target == 'completed':
            self.completed_at = fields.Datetime.now()
        self.state = target
        self.message_post(body=note or 'Technician updated repair status.')

    def action_create_invoice(self):
        self.ensure_one()
        self._require_manager()
        if self.state != 'completed' or not self.sale_order_id:
            raise ValidationError(_('Complete an approved, quoted job before invoicing.'))
        orders=self.quote_ids.filtered(lambda order:order.state=='sale')|self.sale_order_id
        invoiceable=orders.filtered(lambda order:order.invoice_status=='to invoice')
        invoices=invoiceable._create_invoices() if invoiceable else orders.invoice_ids.filtered(lambda inv: inv.state != 'cancel')
        if invoices:
            invoices.write({'workshop_job_id': self.id})
        if not invoices:
            raise ValidationError(_('No invoiceable lines. Review delivery/invoicing policy in Sales.'))
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move',
                'view_mode': 'form', 'res_id': invoices[0].id}


class WorkshopCheck(models.Model):
    _name = 'workshop.check'
    _description = 'Workshop Inspection Check'
    job_id = fields.Many2one('workshop.job', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    done = fields.Boolean()


class WorkshopPhoto(models.Model):
    _name = 'workshop.photo'
    _description = 'Private Repair Photo'
    _order = 'create_date desc'
    job_id = fields.Many2one('workshop.job', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    image = fields.Binary(attachment=True, required=True)
    mimetype = fields.Char()


class WorkshopPartRequest(models.Model):
    _name = 'workshop.part.request'
    _description = 'Workshop Spare Part Request'
    _order = 'id desc'
    job_id = fields.Many2one('workshop.job', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', required=True)
    quantity = fields.Float(required=True, default=1)
    note = fields.Text()
    state = fields.Selection([('requested', 'Requested'), ('issued', 'Issued'), ('rejected', 'Rejected')], default='requested', required=True)
    picking_id = fields.Many2one('stock.picking', readonly=True)

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            try:
                positive_quantity(line.quantity)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

    def action_reject(self):
        for line in self:
            line.job_id._require_manager()
            if line.state == 'requested':
                line.state = 'rejected'

    def action_issue(self):
        self.ensure_one()
        self.job_id._require_manager()
        # Serialize issue attempts: one request cannot create two deliveries.
        self.env.cr.execute('SELECT id FROM workshop_part_request WHERE id = %s FOR UPDATE', (self.id,))
        self.env.cr.execute('SELECT id FROM workshop_job WHERE id = %s FOR UPDATE', (self.job_id.id,))
        self.invalidate_recordset(['state'])
        self.job_id.part_ids.invalidate_recordset(['state'])
        if self.state == 'issued':
            return
        if self.state != 'requested' or self.job_id.state not in ['approved', 'assigned', 'in_progress', 'paused', 'waiting_parts']:
            raise ValidationError(_('Only active repair jobs can receive requested parts.'))
        orders = self.job_id.quote_ids.filtered(lambda order:order.state=='sale') | self.job_id.sale_order_id.filtered(lambda order:order.state=='sale')
        deliveries = orders.picking_ids.filtered(lambda p: p.location_dest_id.usage == 'customer' and p.state != 'cancel')
        moves = deliveries.move_ids.filtered(lambda m: m.product_id == self.product_id and m.state != 'cancel')
        if any(move.product_uom != self.product_id.uom_id for move in moves):
            raise ValidationError(_('Use the product base unit on this workshop quotation.'))
        already_issued = sum(self.job_id.part_ids.filtered(lambda line:
            line.product_id == self.product_id and line.state == 'issued').mapped('quantity'))
        available = sum(moves.mapped('product_uom_qty')) - already_issued
        if self.quantity > available + 0.00001:
            raise ValidationError(_('This quantity is not on the approved sales delivery. Review the quotation; do not issue unapproved billable parts.'))
        for picking in deliveries.filtered(lambda p: p.state != 'done' and self.product_id in p.move_ids.product_id):
            picking.action_assign()
            if picking.state != 'assigned':
                raise ValidationError(_('Not enough reservable stock. Receive stock through Purchase/Inventory first.'))
            for move in picking.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.button_validate()
            if picking.state != 'done':
                raise ValidationError(_('Delivery needs manual review in Inventory.'))
        done_moves = moves.filtered(lambda m: m.state == 'done')
        if sum(done_moves.mapped('quantity')) - already_issued + 0.00001 < self.quantity:
            raise ValidationError(_('No delivered stock is available for this request.'))
        self.write({'state': 'issued', 'picking_id': done_moves[0].picking_id.id})
