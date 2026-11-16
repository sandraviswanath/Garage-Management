import base64
import hashlib
import json
from datetime import date
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError
from ..models.policy import photo_bytes, positive_quantity


class WorkshopAPI(http.Controller):
    """Session authenticated, purpose-specific API. Never accepts arbitrary model/fields."""

    def _role(self):
        user = request.env.user
        if user.has_group('workshop_hub.group_manager') and user.has_group('base.group_system'):
            return 'admin'
        if user.has_group('workshop_hub.group_manager'):
            return 'manager'
        if user.has_group('workshop_hub.group_receptionist'):
            return 'receptionist'
        if user.has_group('workshop_hub.group_accountant'):
            return 'accountant'
        if user.has_group('workshop_hub.group_technician'):
            return 'technician'
        if user.has_group('base.group_portal'):
            return 'customer'
        raise AccessError('This account has no Workshop Hub role.')

    def _require(self, role):
        if self._role() != role:
            raise AccessError('This operation is not available for your role.')

    def _jobs(self):
        role = self._role()
        domain = [('company_id', 'in', request.env.user.company_ids.ids)]
        if role == 'technician':
            domain += [('technician_id', '=', request.env.uid)]
        elif role == 'customer':
            domain += [('partner_id', '=', request.env.user.partner_id.id)]
        return request.env['workshop.job'].sudo(), domain

    def _job(self, job_id):
        model, domain = self._jobs()
        job = model.search(domain + [('id', '=', int(job_id))], limit=1)
        if not job:
            raise AccessError('Job not found or unavailable for this account.')
        return job

    def _serialize(self, job):
        order = job.sale_order_id
        orders=job.quote_ids|order
        return {
            'id': job.id, 'name': job.name, 'state': job.state,
            'vehicle': job.vehicle_id.plate, 'model': job.vehicle_id.make_model,
            'concern': job.concern, 'date': str(job.appointment_date or ''),
            'technician': job.technician_id.name or 'Not assigned',
            'quote': ({'id': order.id, 'name': order.name, 'total': order.amount_total,
                'currency': order.currency_id.name, 'version': self._quote_version(order),
                'lines': [{'name': line.name, 'qty': line.product_uom_qty, 'total': line.price_subtotal}
                    for line in order.order_line if not line.display_type]} if order else None),
            'checks': [{'id': line.id, 'name': line.name, 'done': line.done} for line in job.checklist_ids],
            'parts': [{'id': line.id, 'name': line.product_id.display_name,
                       'quantity': line.quantity, 'state': line.state} for line in job.part_ids],
            'photos': [{'id': photo.id, 'name': photo.name} for photo in job.photo_ids[:20]],
            'invoices': [{'id': invoice.id, 'name': invoice.name, 'total': invoice.amount_total,
                'currency': invoice.currency_id.name, 'payment_state': invoice.payment_state}
                for invoice in orders.invoice_ids if invoice.state == 'posted' and invoice.move_type == 'out_invoice'],
            'pending_quotes':[{'id':extra.id,'name':extra.name,'total':extra.amount_total,'currency':extra.currency_id.name,'version':self._quote_version(extra),
                'lines':[{'name':line.name,'qty':line.product_uom_qty,'total':line.price_subtotal} for line in extra.order_line if not line.display_type]}
                for extra in orders if extra!=order and extra.state=='sent'],
            'tasks': [{'id':task.id,'description':task.description,'hours':task.hours,'rate':task.rate,'state':task.state,'notes':task.notes or ''} for task in job.task_ids],
            'notes': [{'id':note.id,'content':note.content,'kind':note.kind,'author':note.author_id.name,'date':str(note.create_date)} for note in job.note_ids],
            'timers': [{'id':timer.id,'activity':timer.activity,'start':str(timer.start),'end':str(timer.end or ''),'minutes':timer.minutes} for timer in job.time_ids],
        }

    def _quote_version(self, order):
        snapshot = [order.id, order.state, str(order.write_date), order.amount_total,
            order.currency_id.id, [(line.id, str(line.write_date), line.name, line.product_id.id,
                line.product_uom_qty, line.price_unit, line.discount, line.tax_id.ids)
                for line in order.order_line]]
        return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()

    @http.route('/workshop/api/me', type='json', auth='user', methods=['POST'])
    def me(self):
        return {'name': request.env.user.name, 'role': self._role(), 'uid': request.env.uid}

    @http.route('/workshop/api/dashboard', type='json', auth='user', methods=['POST'])
    def dashboard(self):
        model, domain = self._jobs()
        jobs = model.search(domain, limit=100)
        partner = request.env.user.partner_id
        vehicles = request.env['workshop.vehicle'].sudo().search([
            ('partner_id', '=', partner.id), ('company_id', 'in', request.env.user.company_ids.ids)]) if self._role() == 'customer' else []
        return {'user': self.me(), 'jobs': [self._serialize(job) for job in jobs],
            'vehicles': [{'id': v.id, 'plate': v.plate, 'model': v.make_model} for v in vehicles]}

    @http.route('/workshop/api/job', type='json', auth='user', methods=['POST'])
    def job(self, job_id):
        return self._serialize(self._job(job_id))

    @http.route('/workshop/api/vehicle', type='json', auth='user', methods=['POST'])
    def vehicle(self, plate, make_model):
        self._require('customer')
        plate, make_model = str(plate).strip().upper(), str(make_model).strip()
        if not 2 <= len(plate) <= 30 or not 2 <= len(make_model) <= 120:
            raise ValidationError('Enter a valid registration and vehicle model.')
        request.env.user.partner_id.sudo().workshop_customer = True
        vehicle = request.env['workshop.vehicle'].sudo().create({
            'plate': plate, 'make_model': make_model,
            'partner_id': request.env.user.partner_id.id, 'company_id': request.env.company.id})
        return {'id': vehicle.id}

    @http.route('/workshop/api/request', type='json', auth='user', methods=['POST'])
    def service_request(self, vehicle_id, concern, appointment_date=None):
        self._require('customer')
        vehicle = request.env['workshop.vehicle'].sudo().search([
            ('id', '=', int(vehicle_id)), ('partner_id', '=', request.env.user.partner_id.id),
            ('company_id', '=', request.env.company.id)], limit=1)
        if not vehicle:
            raise AccessError('Choose one of your own vehicles.')
        concern = str(concern).strip()
        if not 10 <= len(concern) <= 4000:
            raise ValidationError('Describe the problem using 10 to 4,000 characters.')
        if appointment_date:
            try:
                selected_date = date.fromisoformat(appointment_date)
            except (ValueError, TypeError):
                raise ValidationError('Choose a valid appointment date.') from None
            if selected_date < fields.Date.context_today(request.env.user):
                raise ValidationError('Choose today or a future appointment date.')
        job = request.env['workshop.job'].sudo().create({
            'partner_id': request.env.user.partner_id.id, 'vehicle_id': vehicle.id,
            'concern': concern, 'appointment_date': appointment_date or False,
            'company_id': vehicle.company_id.id})
        lead = request.env['crm.lead'].sudo().create({
            'name': job.name + ' - ' + vehicle.plate, 'type': 'opportunity',
            'partner_id': job.partner_id.id, 'description': concern, 'company_id': job.company_id.id})
        job.lead_id = lead
        return self._serialize(job)

    @http.route('/workshop/api/approve', type='json', auth='user', methods=['POST'])
    def approve(self, job_id, version, order_id=None):
        self._require('customer')
        job = self._job(job_id)
        order = (job.quote_ids|job.sale_order_id).filtered(lambda order:order.id==int(order_id)) if order_id else job.sale_order_id
        if not order:
            raise ValidationError('No quotation is available.')
        request.env.cr.execute('SELECT id FROM sale_order WHERE id = %s FOR UPDATE', (order.id,))
        order.invalidate_recordset()
        if self._quote_version(order) != version:
            raise ValidationError('The quotation changed. Refresh and review it before approving.')
        if order==job.sale_order_id:
            job._approve_customer_quote()
        else:
            if order.state!='sent' or job.state in ['completed','cancelled']:raise ValidationError('This additional quotation is not awaiting approval.')
            order.action_confirm()
            job.message_post(body='Customer approved additional quotation %s.'%order.name)
        return self._serialize(job)

    @http.route('/workshop/api/status', type='json', auth='user', methods=['POST'])
    def status(self, job_id, state, note=''):
        self._require('technician')
        if len(str(note)) > 2000:
            raise ValidationError('Notes must be under 2,000 characters.')
        job = self._job(job_id)
        request.env.cr.execute('SELECT id FROM workshop_job WHERE id = %s FOR UPDATE', (job.id,))
        job.invalidate_recordset()
        job._technician_update(state, str(note))
        return self._serialize(job)

    @http.route('/workshop/api/check', type='json', auth='user', methods=['POST'])
    def check(self, job_id, check_id, done):
        self._require('technician')
        job = self._job(job_id)
        if job.state not in ['approved', 'assigned', 'in_progress', 'paused', 'waiting_parts']:
            raise ValidationError('Inspection checks are editable only on active jobs.')
        check = job.checklist_ids.filtered(lambda line: line.id == int(check_id))
        if not check or not isinstance(done, bool):
            raise ValidationError('Invalid inspection check.')
        check.done = done
        return self._serialize(job)

    @http.route('/workshop/api/photo', type='json', auth='user', methods=['POST'])
    def photo(self, job_id, image, name='Repair photo', kind='during', description=''):
        self._require('technician')
        job = self._job(job_id)
        if job.state not in ['approved', 'assigned', 'in_progress', 'paused', 'waiting_parts']:
            raise ValidationError('Upload photos while the repair job is active.')
        try:
            raw, mimetype = photo_bytes(image)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        # Verify image contents as well as magic bytes.
        from PIL import Image
        from io import BytesIO
        try:
            with Image.open(BytesIO(raw)) as picture:
                if picture.width * picture.height > 25_000_000:
                    raise ValueError('Image dimensions are too large.')
                picture.verify()
        except Exception as exc:
            raise ValidationError('Upload a valid JPEG or PNG up to 25 megapixels.') from exc
        request.env['workshop.photo'].sudo().create({'job_id': job.id, 'name': str(name)[:120],
            'image': base64.b64encode(raw), 'mimetype': mimetype,
            'kind':kind if kind in ['before','during','after','issue'] else 'during',
            'description':str(description)[:250],'author_id':request.env.uid})
        return self._serialize(job)

    @http.route('/workshop/api/parts', type='json', auth='user', methods=['POST'])
    def parts(self):
        self._require('technician')
        products = request.env['product.product'].sudo().search([
            ('is_storable', '=', True), ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', 'in', request.env.user.company_ids.ids)], limit=100)
        return [{'id': product.id, 'name': product.display_name} for product in products]

    @http.route('/workshop/api/part-request', type='json', auth='user', methods=['POST'])
    def part_request(self, job_id, product_id, quantity, note=''):
        self._require('technician')
        job = self._job(job_id)
        if job.state not in ['approved', 'assigned', 'in_progress', 'paused', 'waiting_parts']:
            raise ValidationError('Parts can only be requested for active repairs.')
        allowed = {product['id'] for product in self.parts()}
        if int(product_id) not in allowed:
            raise ValidationError('Choose an available spare part.')
        try:
            quantity = positive_quantity(quantity)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        request.env['workshop.part.request'].sudo().create({'job_id': job.id,
            'product_id': int(product_id), 'quantity': quantity, 'note': str(note)[:2000]})
        return self._serialize(job)

    @http.route('/workshop/api/invoice', type='json', auth='user', methods=['POST'])
    def invoice(self, job_id, invoice_id):
        self._require('customer')
        job = self._job(job_id)
        invoice = (job.quote_ids|job.sale_order_id).invoice_ids.filtered(lambda inv:
            inv.id == int(invoice_id) and inv.state == 'posted' and inv.move_type == 'out_invoice'
            and inv.partner_id == job.partner_id)
        if not invoice:
            raise AccessError('Invoice not found for this job.')
        pdf, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf('account.account_invoices', res_ids=invoice.ids)
        return {'name': 'invoice-%s.pdf' % invoice.id, 'content': base64.b64encode(pdf).decode()}

    @http.route('/workshop/api/photo-get', type='json', auth='user', methods=['POST'])
    def photo_get(self, job_id, photo_id):
        job = self._job(job_id)
        photo = job.photo_ids.filtered(lambda item: item.id == int(photo_id))
        if not photo:
            raise AccessError('Photo not found for this job.')
        return {'image': photo.image.decode(), 'mimetype': photo.mimetype}
