import base64
import math
from datetime import timedelta
from io import BytesIO
from odoo import http, fields, Command
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError
from ..models.staff_policy import allow
from ..models.policy import positive_quantity, photo_bytes
from .api import WorkshopAPI

class StaffAPI(WorkshopAPI):
    """All staff screens use this bounded action API, never a generic ORM proxy."""
    def _env(self, model):
        return request.env[model].sudo().with_company(request.env.company)

    def _company(self):
        return request.env.company.id

    def _record(self, model, record_id, shared=False):
        domain=[('id','=',int(record_id))]
        if 'company_id' in self._env(model)._fields:
            domain += [('company_id','in',[False,self._company()])] if shared else [('company_id','=',self._company())]
        record=self._env(model).with_context(active_test=False).search(domain,limit=1)
        if not record:
            raise AccessError('Record not found in your company.')
        return record

    def _text(self, value, maxlen=4000):
        text=str(value or '').strip()
        if len(text)>maxlen:
            raise ValidationError('Text is too long.')
        return text

    def _number(self, value, maximum=1e9):
        try: number=float(value or 0)
        except (TypeError,ValueError): raise ValidationError('Enter a valid number.') from None
        if not math.isfinite(number) or number<0 or number>maximum:
            raise ValidationError('Enter a non-negative number within the allowed range.')
        return number

    def _choice(self, value, options):
        if value not in options:
            raise ValidationError('Invalid selection.')
        return value

    def _lock(self, record):
        # Model names are fixed by callers, never supplied by the client.
        from psycopg2 import sql
        request.env.cr.execute(sql.SQL('SELECT id FROM {} WHERE id = %s FOR UPDATE').format(sql.Identifier(record._table)),(record.id,))
        record.invalidate_recordset()

    def _staff_job(self, job_id):
        job=self._job(job_id)
        if job.company_id.id != self._company():
            raise AccessError('Job is not in your active company.')
        return job

    def _job_data(self, job):
        data=self._serialize(job)
        order=job.sale_order_id
        orders=job.quote_ids|order
        invoices=(orders.invoice_ids|self._env('account.move').search([('workshop_job_id','=',job.id)])).filtered(lambda inv: inv.state!='cancel')
        data.update({
            'partner_id':job.partner_id.id,'customer':job.partner_id.name,'phone':job.partner_id.phone or '',
            'email':job.partner_id.email or '', 'vehicle_id':job.vehicle_id.id,'technician_id':job.technician_id.id or '',
            'job_type':job.job_type,'priority':job.priority,'diagnosis':job.diagnosis or '',
            'instructions':job.instructions or '', 'expected_completion':str(job.expected_completion or ''),
            'completed_at':str(job.completed_at or ''),'created_at':str(job.create_date),
            'quality_rating':job.quality_rating,'active':job.active,
            'tasks':[{'id':t.id,'description':t.description,'hours':t.hours,'rate':t.rate,'total':t.hours*t.rate,'state':t.state,'notes':t.notes or ''} for t in job.task_ids],
            'notes':[{'id':n.id,'content':n.content,'kind':n.kind,'author':n.author_id.name,'date':str(n.create_date)} for n in job.note_ids],
            'timers':[{'id':t.id,'activity':t.activity,'start':str(t.start),'end':str(t.end or ''),'minutes':t.minutes,'technician':t.technician_id.name} for t in job.time_ids],
            'photos':[{'id':p.id,'name':p.name,'kind':p.kind,'description':p.description or '', 'author':p.author_id.name or '', 'date':str(p.create_date)} for p in job.photo_ids],
            'parts':[{'id':p.id,'product_id':p.product_id.id,'name':p.product_id.display_name,'quantity':p.quantity,'state':p.state,'used':p.used,'note':p.note or ''} for p in job.part_ids],
            'total':sum((orders.filtered(lambda q:q.state=='sale')|order.filtered(lambda q:q.state not in ['sale','cancel'])).mapped('amount_total')) if order else sum(t.hours*t.rate for t in job.task_ids),
            'quotations':[{'id':q.id,'name':q.name,'state':q.state,'total':q.amount_total,'currency':q.currency_id.name} for q in orders],
            'currency':order.currency_id.name if order else request.env.company.currency_id.name,
            'paid':bool(invoices.filtered(lambda inv:inv.move_type=='out_invoice' and inv.state=='posted')) and all(inv.amount_residual==0 for inv in invoices.filtered(lambda inv:inv.move_type=='out_invoice' and inv.state=='posted')),
            'invoices':[self._invoice_data(inv,False) for inv in invoices],
        })
        return data

    def _customer_data(self, partner, detail=False):
        jobs=self._env('workshop.job').search([('partner_id','=',partner.id),('company_id','=',self._company())])
        invoices=self._env('account.move').search([('partner_id','=',partner.id),('company_id','=',self._company()),('state','=','posted'),('move_type','in',['out_invoice','out_refund'])])
        data={'id':partner.id,'name':partner.name,'email':partner.email or '', 'phone':partner.phone or '',
              'address':partner.street or '', 'vat':partner.vat or '', 'status':partner.workshop_status,
              'total_jobs':len(jobs),'open_jobs':len(jobs.filtered(lambda j:j.state not in ['completed','cancelled'])),
              'total_spent':sum(invoices.mapped('amount_total_signed')),'currency':request.env.company.currency_id.name,'active':partner.active}
        if detail:
            data['vehicles']=[self._vehicle_data(v) for v in self._env('workshop.vehicle').search([('partner_id','=',partner.id),('company_id','=',self._company())])]
            data['jobs']=[self._job_data(job) for job in jobs]
        return data

    def _vehicle_data(self, vehicle, detail=False):
        data={'id':vehicle.id,'plate':vehicle.plate,'make_model':vehicle.make_model,'partner_id':vehicle.partner_id.id,
              'customer':vehicle.partner_id.name,'vehicle_type':vehicle.vehicle_type or '', 'make':vehicle.make or '',
              'model':vehicle.model or '', 'year':vehicle.year or '', 'chassis_number':vehicle.chassis_number or '',
              'engine_number':vehicle.engine_number or '', 'km_reading':vehicle.km_reading,'active':vehicle.active,'status':vehicle.status}
        if detail: data['jobs']=[self._job_data(j) for j in vehicle.job_ids]
        return data

    def _inventory_data(self, product):
        return {'id':product.id,'name':product.name,'sku':product.default_code or '', 'description':product.description_sale or '',
                'category':product.categ_id.name,'supplier_id':product.workshop_supplier_id.id or '',
                'supplier':product.workshop_supplier_id.name or '', 'quantity':product.qty_available,
                'min_stock_level':product.workshop_min_stock,'max_stock_level':product.workshop_max_stock,
                'unit_cost':product.standard_price,'retail_price':product.lst_price,'location':product.workshop_bin or '',
                'low_stock':product.qty_available<=product.workshop_min_stock,'active':product.active}

    def _estimate_data(self, order):
        return {'id':order.id,'name':order.name,'customer':order.partner_id.name,'job_id':order.workshop_job_id.id or '',
                'job':order.workshop_job_id.name or order.origin or '', 'state':order.state,'date':str(order.date_order),
                'validity_date':str(order.validity_date or ''),'notes':order.note or '', 'total':order.amount_total,
                'tax':order.amount_tax,'subtotal':order.amount_untaxed,'currency':order.currency_id.name,'discount_amount':order.workshop_discount_amount,
                'lines':[{'id':line.id,'product_id':line.product_id.id,'description':line.name,'qty':line.product_uom_qty,
                          'unit_price':line.price_unit,'discount':line.discount,'tax_ids':line.tax_id.ids,'total':line.price_subtotal}
                          for line in order.order_line if not line.display_type and line.name!='Workshop order discount']}

    def _invoice_data(self, invoice, detail=True):
        data={'id':invoice.id,'name':invoice.name,'customer':invoice.partner_id.name,'job_id':invoice.workshop_job_id.id or '',
              'job':invoice.workshop_job_id.name or invoice.invoice_origin or '', 'state':invoice.state,
              'payment_state':invoice.payment_state,'move_type':invoice.move_type,'date':str(invoice.invoice_date or ''),
              'due_date':str(invoice.invoice_date_due or ''),'total':invoice.amount_total,'balance':invoice.amount_residual,
              'tax':invoice.amount_tax,'currency':invoice.currency_id.name,'notes':invoice.narration or '','discount_amount':invoice.workshop_discount_amount}
        if detail:
            data['lines']=[{'id':line.id,'product_id':line.product_id.id,'description':line.name,'qty':line.quantity,
                 'unit_price':line.price_unit,'discount':line.discount,'tax_ids':line.tax_ids.ids,'total':line.price_subtotal}
                 for line in invoice.invoice_line_ids if line.display_type in [False,'product']]
            data['payments']=[self._payment_data(p) for p in self._env('account.payment').search([('workshop_invoice_id','=',invoice.id)])]
        return data

    def _payment_data(self,payment):
        inv=payment.workshop_invoice_id
        refunds=self._env('account.payment').search([('workshop_refund_of_id','=',payment.id),('state','not in',['draft','canceled'])])
        refunded=sum(refunds.mapped('amount'))
        status='pending' if payment.state=='draft' else 'failed' if payment.state in ['canceled','rejected'] else 'refunded' if refunded and refunded>=payment.amount else 'partial_refund' if refunded else 'completed'
        return {'id':payment.id,'name':payment.name or 'Payment','invoice_id':inv.id or '', 'invoice':inv.name or '',
                'customer':payment.partner_id.name,'amount':payment.amount,'currency':payment.currency_id.name,
                'date':str(payment.date),'method':payment.workshop_method or '', 'reference':payment.workshop_reference or '',
                'transaction':payment.workshop_transaction or '', 'last4':payment.workshop_last4 or '',
                'bank':payment.workshop_bank or '', 'notes':payment.workshop_notes or '', 'state':payment.state,
                'type':payment.payment_type,'refund_of':payment.workshop_refund_of_id.id or '','status':status,'refunded_amount':refunded,
                'journal_id':payment.journal_id.id,'journal':payment.journal_id.name}

    def _user_role(self,user):
        if user.has_group('workshop_hub.group_manager'):
            return 'admin' if user.has_group('base.group_system') else 'manager'
        for role in ['receptionist','accountant','technician']:
            if user.has_group('workshop_hub.group_'+role):return role
        return ''

    def _user_data(self,user):
        return {'id':user.id,'name':user.name,'email':user.login,'phone':user.partner_id.phone or '',
                'role':self._user_role(user),'specialization':user.workshop_specialization or '', 'active':user.active}

    def _lookups(self):
        company=self._company()
        users=self._env('res.users').search([('company_ids','in',[company]),('share','=',False)])
        techs=users.filtered(lambda u:u.has_group('workshop_hub.group_technician'))
        role=self._role()
        common={'technicians':[self._user_data(u) for u in techs],
                'currency':request.env.company.currency_id.name,'company':request.env.company.name}
        if role=='technician':
            common['products']=[{**p,'storable':True} for p in self.parts()]
            return common
        common.update({
          'customers':[{'id':p.id,'name':p.name} for p in self._env('res.partner').search([('workshop_customer','=',True),'|',('company_id','=',False),('company_id','=',company)],limit=1000)],
          'vehicles':[self._vehicle_data(v) for v in self._env('workshop.vehicle').search([('company_id','=',company)],limit=1000)],
          'products':[{'id':p.id,'name':p.display_name,'price':p.lst_price,'cost':p.standard_price,'quantity':p.qty_available,'storable':p.is_storable,'tax_ids':p.taxes_id.filtered(lambda t:t.company_id.id==company).ids} for p in self._env('product.product').search(['|',('company_id','=',False),('company_id','=',company)],limit=1000)],
          'suppliers':[{'id':p.id,'name':p.name} for p in self._env('res.partner').search([('supplier_rank','>',0),'|',('company_id','=',False),('company_id','=',company)],limit=1000)],
          'taxes':[{'id':t.id,'name':t.name,'use':t.type_tax_use} for t in self._env('account.tax').search([('company_id','=',company),('active','=',True)])],
          'categories':[{'id':c.name,'name':c.name} for c in self._env('product.category').search([])],
          'journals':[{'id':j.id,'name':j.name,'type':j.type} for j in self._env('account.journal').search([('company_id','=',company),('type','in',['cash','bank'])])],
          'jobs':[{'id':j.id,'name':j.name+' — '+j.vehicle_id.plate,'state':j.state} for j in self._env('workshop.job').search([('company_id','=',company)],limit=1000)],
          'invoices':[{'id':inv.id,'name':'%s — %s — %s %s due'%(inv.name,inv.partner_id.name,inv.amount_residual,inv.currency_id.name)} for inv in self._env('account.move').search([('company_id','=',company),('workshop_job_id','!=',False),('state','=','posted'),('move_type','=','out_invoice'),('amount_residual','>',0)],limit=1000)],
        })
        return common

    def _list(self,entity,p):
        company=self._company();q=self._text(p.get('search'),120)
        offset=max(0,int(p.get('offset',0)));limit=50
        configs={
          'customers':('res.partner',[('workshop_customer','=',True),'|',('company_id','=',False),('company_id','=',company)],'name',self._customer_data),
          'vehicles':('workshop.vehicle',[('company_id','=',company)],'plate',self._vehicle_data),
          'jobs':('workshop.job',[('company_id','=',company)],'name',self._job_data),
          'work':('workshop.job',[('company_id','=',company)],'name',self._job_data),
          'estimates':('sale.order',[('company_id','=',company),('workshop_job_id','!=',False)],'name',self._estimate_data),
          'inventory':('product.product',[('is_storable','=',True),'|',('company_id','=',False),('company_id','=',company)],'name',self._inventory_data),
          'invoices':('account.move',[('company_id','=',company),('workshop_job_id','!=',False),('move_type','in',['out_invoice','out_refund'])],'name',lambda inv:self._invoice_data(inv,False)),
          'payments':('account.payment',[('company_id','=',company),('workshop_invoice_id','!=',False)],'name',self._payment_data),
          'users':('res.users',[('company_ids','in',[company]),('share','=',False)],'name',self._user_data),
          'transactions':('stock.move',[('company_id','=',company),('state','=','done')],'reference',lambda m:{'id':m.id,'date':str(m.date),'product':m.product_id.display_name,'quantity':m.quantity,'from':m.location_id.display_name,'to':m.location_dest_id.display_name,'reference':m.reference or m.origin or '', 'state':m.state}),
          'purchases':('purchase.order',[('company_id','=',company)],'name',self._purchase_data),
        }
        model,domain,search_field,serializer=configs[entity]
        if self._role()=='technician':domain += [('technician_id','=',request.env.uid)]
        if q:
            fields_to_search={'customers':['name','phone','email'],'vehicles':['plate','make_model','partner_id.name'],'jobs':['name','vehicle_id.plate','partner_id.name'],'work':['name','vehicle_id.plate','partner_id.name']}.get(entity,[search_field])
            domain += ['|']*(len(fields_to_search)-1)+[(field,'ilike',q) for field in fields_to_search]
        if p.get('state') and entity not in ['inventory','payments']:
            if entity=='customers':domain += [('workshop_status','=',p['state'])]
            elif entity=='vehicles':domain += [('status','=',p['state'])]
            elif p['state']=='open' and model=='workshop.job':domain += [('state','not in',['completed','cancelled'])]
            elif 'state' in self._env(model)._fields:domain += [('state','=',p['state'])]
        if p.get('job_type') and model=='workshop.job':domain += [('job_type','=',p['job_type'])]
        if p.get('category') and entity=='inventory':domain += [('categ_id.name','=',p['category'])]
        if p.get('method') and entity=='payments':domain += [('workshop_method','=',p['method'])]
        if p.get('date') and entity=='payments':domain += [('date','=',fields.Date.to_date(p['date']))]
        if p.get('payment_state') and entity=='invoices':
            if p['payment_state']=='overdue':domain += [('invoice_date_due','<',fields.Date.today()),('amount_residual','>',0),('state','=','posted')]
            else:domain += [('payment_state','=',p['payment_state'])]
        if p.get('technician_id') and model=='workshop.job':domain += [('technician_id','=',int(p['technician_id']))]
        if p.get('archived'):model_env=self._env(model).with_context(active_test=False)
        else:model_env=self._env(model)
        records=model_env.search(domain,order='id desc')
        if entity=='inventory' and p.get('state'):
            records=records.filtered(lambda part: part.qty_available<=0 if p['state']=='out-of-stock' else 0<part.qty_available<=part.workshop_min_stock if p['state']=='low-stock' else part.qty_available>part.workshop_min_stock)
        if entity=='payments' and p.get('state'):records=records.filtered(lambda pay:self._payment_data(pay)['status']==p['state'])
        metrics={'records':len(records)}
        if entity=='inventory':metrics.update({'low_stock':len(records.filtered(lambda r:r.qty_available<=r.workshop_min_stock)), 'out_of_stock':len(records.filtered(lambda r:r.qty_available<=0)),'stock_value':sum(r.qty_available*r.standard_price for r in records)})
        elif entity in ['jobs','work']:metrics.update({'completed':len(records.filtered(lambda r:r.state=='completed')),'open':len(records.filtered(lambda r:r.state not in ['completed','cancelled']))})
        elif entity=='invoices':metrics.update({'invoiced':sum(records.filtered(lambda r:r.state=='posted').mapped('amount_total_signed')),'outstanding':sum(records.filtered(lambda r:r.state=='posted' and r.move_type=='out_invoice').mapped('amount_residual_signed'))})
        elif entity=='estimates':metrics.update({'draft':len(records.filtered(lambda r:r.state=='draft')),'sent':len(records.filtered(lambda r:r.state=='sent')),'approved':len(records.filtered(lambda r:r.state=='sale'))})
        return {'rows':[serializer(r) for r in records[offset:offset+limit]],'total':len(records),'offset':offset,'limit':limit,'metrics':metrics,'currency':request.env.company.currency_id.name}

    def _detail(self,entity,record_id):
        if entity in ['jobs','work']:return self._job_data(self._staff_job(record_id))
        config={'customers':('res.partner',lambda r:self._customer_data(r,True),True),
          'vehicles':('workshop.vehicle',lambda r:self._vehicle_data(r,True),False),
          'estimates':('sale.order',self._estimate_data,False),'inventory':('product.product',self._inventory_data,True),
          'invoices':('account.move',self._invoice_data,False),'payments':('account.payment',self._payment_data,False),
          'users':('res.users',self._user_data,True),'purchases':('purchase.order',self._purchase_data,False)}
        if entity not in config:raise ValidationError('No detail view for this resource.')
        model,serializer,shared=config[entity]
        record=self._record(model,record_id,shared)
        if model=='res.users' and self._company() not in record.company_ids.ids:raise AccessError('User not in your company.')
        if model=='sale.order' and not record.workshop_job_id:raise AccessError('This is not a workshop quotation.')
        if model=='account.move' and not record.workshop_job_id:raise AccessError('This is not a workshop invoice.')
        if model=='account.payment' and not record.workshop_invoice_id:raise AccessError('This is not a workshop payment.')
        return serializer(record)

    @http.route('/workshop/api/staff',type='json',auth='user',methods=['POST'])
    def staff(self,action,payload=None):
        p=payload or {}
        if not isinstance(p,dict):raise ValidationError('Invalid payload.')
        role=self._role();entity=p.get('entity')
        if not allow(role,action,entity):raise AccessError('Your role cannot perform this operation.')
        if action=='lookups':return self._lookups()
        if action=='list':return self._list(entity,p)
        if action=='detail':return self._detail(entity,p['id'])
        if action in ['dashboard','report']:return self._report(p,action=='dashboard')
        handlers={
          'customer.save':self._save_customer,'customer.portal':self._customer_portal,'vehicle.save':self._save_vehicle,'job.save':self._save_job,
          'customer.archive':lambda p:self._archive('res.partner',p,True),'vehicle.archive':lambda p:self._archive('workshop.vehicle',p),
          'job.archive':lambda p:self._archive('workshop.job',p),'user.archive':self._archive_user,
          'task.save':self._task_save,'task.delete':self._task_delete,'task.update':self._task_update,
          'job.state':self._job_state,'job.review':self._job_review,'check.update':self._check_update,'note.add':self._note_add,'timer.start':self._timer_start,'timer.stop':self._timer_stop,
          'photo.save':self._photo_save,'photo.edit':self._photo_edit,'photo.delete':self._photo_delete,
          'part.use':self._part_use,'part.request':self._part_request,'part.issue':self._part_issue,'part.reject':self._part_reject,
          'estimate.save':self._estimate_save,'estimate.send':self._estimate_send,'estimate.approve':self._estimate_approve,
          'estimate.reject':self._estimate_reject,'estimate.duplicate':self._estimate_duplicate,'estimate.delete':self._estimate_delete,
          'inventory.save':self._inventory_save,'inventory.stock':self._inventory_stock,'inventory.archive':lambda p:self._archive('product.product',p,True),
          'invoice.create':self._invoice_create,'invoice.save':self._invoice_save,'invoice.post':self._invoice_post,'invoice.cancel':self._invoice_cancel,
          'invoice.email':lambda p:self._invoice_email(p,False),'invoice.remind':lambda p:self._invoice_email(p,True),
          'payment.create':self._payment_create,'payment.cancel':self._payment_cancel,'payment.refund':self._payment_refund,
          'user.save':self._user_save,'document':self._document,
          'purchase.create':self._purchase_create,'purchase.confirm':self._purchase_confirm,'purchase.receive':self._purchase_receive,
        }
        return handlers[action](p)

    def _archive(self,model,p,shared=False):
        record=self._record(model,p['id'],shared)
        if model=='workshop.job' and record.state not in ['requested','cancelled','completed']:
            raise ValidationError('Cancel or complete this job before archiving it.')
        record.active=not bool(p.get('archive',True))
        return {'id':record.id}

    def _save_customer(self,p):
        name=self._text(p.get('name'),120);phone=self._text(p.get('phone'),40)
        if not name or not phone:raise ValidationError('Customer name and phone are required.')
        values={'name':name,'phone':phone,'email':self._text(p.get('email'),254), 'street':self._text(p.get('address'),500),
          'vat':self._text(p.get('vat'),50),'workshop_customer':True,'customer_rank':1,
          'workshop_status':self._choice(p.get('status','active'),['active','inactive'])}
        if p.get('id'):
            partner=self._record('res.partner',p['id'],True);partner.write(values)
        else:partner=self._env('res.partner').create({**values,'company_id':self._company()})
        if p.get('vehicle_plate'):
            self._save_vehicle({'partner_id':partner.id,'plate':p['vehicle_plate'],'make_model':p.get('vehicle_model','Vehicle'),
                 'year':p.get('vehicle_year',0),'chassis_number':p.get('vin','')})
        return self._customer_data(partner,True)

    def _customer_portal(self,p):
        partner=self._record('res.partner',p['id'],True)
        password=str(p.get('password') or '')
        if not partner.workshop_customer or not partner.email or len(password)<12:raise ValidationError('Add a customer email and a password of at least 12 characters.')
        users=self._env('res.users').with_context(active_test=False).search([('partner_id','=',partner.id)])
        if users and (len(users)!=1 or not users.share):raise ValidationError('This contact is linked to an internal account. Review it in Odoo.')
        if users:users.write({'password':password,'active':True})
        else:self._env('res.users').with_context(no_reset_password=True).create({'name':partner.name,'login':partner.email,'email':partner.email,
            'partner_id':partner.id,'password':password,'company_id':self._company(),'company_ids':[Command.set([self._company()])],
            'groups_id':[Command.set([request.env.ref('base.group_portal').id])]})
        return {'ok':True,'message':'Customer portal access configured. Share credentials securely.'}

    def _save_vehicle(self,p):
        partner=self._record('res.partner',p['partner_id'],True)
        values={'partner_id':partner.id,'plate':self._text(p.get('plate'),30).upper(),
          'make_model':self._text(p.get('make_model') or ('%s %s'%(p.get('make',''),p.get('model',''))),120),
          'vehicle_type':self._text(p.get('vehicle_type','car'),40),'make':self._text(p.get('make'),80),'model':self._text(p.get('model'),80),
          'year':int(self._number(p.get('year'),2100)),'km_reading':self._number(p.get('km_reading'),1e7),
          'status':self._choice(p.get('status','active'),['active','inactive','pending']),
          'chassis_number':self._text(p.get('chassis_number'),80),'engine_number':self._text(p.get('engine_number'),80)}
        if not values['plate'] or not values['make_model']:raise ValidationError('Vehicle registration and model are required.')
        if p.get('id'):
            vehicle=self._record('workshop.vehicle',p['id'])
            if vehicle.partner_id!=partner and vehicle.job_ids:raise ValidationError('A vehicle with service history cannot be moved to another customer.')
            vehicle.write(values)
        else:vehicle=self._env('workshop.vehicle').create({**values,'company_id':self._company()})
        return self._vehicle_data(vehicle,True)

    def _save_job(self,p):
        partner=self._record('res.partner',p['partner_id'],True);vehicle=self._record('workshop.vehicle',p['vehicle_id'])
        if vehicle.partner_id!=partner:raise ValidationError('Select a vehicle belonging to this customer.')
        values={'partner_id':partner.id,'vehicle_id':vehicle.id,'concern':self._text(p.get('concern')),
          'job_type':self._choice(p.get('job_type','service'),['repair','service','inspection','custom']),
          'priority':self._choice(p.get('priority','medium'),['low','medium','high','urgent']),
          'instructions':self._text(p.get('instructions')),'diagnosis':self._text(p.get('diagnosis')),
          'expected_completion':fields.Datetime.to_datetime(p.get('expected_completion')) if p.get('expected_completion') else False,
          'technician_id':int(p.get('technician_id') or 0) or False}
        if not values['concern']:raise ValidationError('Reported issue is required.')
        if p.get('id'):
            job=self._staff_job(p['id'])
            if job.state in ['completed','cancelled']:raise ValidationError('Closed jobs cannot be edited.')
            if job.sale_order_id and (job.partner_id!=partner or job.vehicle_id!=vehicle):raise ValidationError('Quoted jobs cannot change customer or vehicle.')
            job.write(values)
        else:job=self._env('workshop.job').create({**values,'company_id':self._company()})
        return self._job_data(job)

    def _task_save(self,p):
        job=self._staff_job(p['job_id'])
        if job.state in ['completed','cancelled']:raise ValidationError('Closed job.')
        values={'description':self._text(p.get('description'),250),'hours':self._number(p.get('hours'),10000),'rate':self._number(p.get('rate'))}
        if not values['description']:raise ValidationError('Task description is required.')
        if p.get('id'):
            task=job.task_ids.filtered(lambda t:t.id==int(p['id']))
            if not task:raise AccessError('Task not in this job.')
            task.write(values)
        else:self._env('workshop.task').create({**values,'job_id':job.id})
        return self._job_data(job)

    def _task_delete(self,p):
        job=self._staff_job(p['job_id']);task=job.task_ids.filtered(lambda t:t.id==int(p['id']))
        if job.state not in ['requested','awaiting_approval'] or not task:raise ValidationError('Only unstarted tasks on draft jobs can be removed.')
        task.unlink();return self._job_data(job)

    def _task_update(self,p):
        job=self._staff_job(p['job_id']);task=job.task_ids.filtered(lambda t:t.id==int(p['id']))
        if not task or job.state not in ['approved','assigned','in_progress','paused','waiting_parts']:raise ValidationError('Task is not editable on this job.')
        task.write({'state':self._choice(p.get('state'),['pending','in_progress','completed']),'notes':self._text(p.get('notes'))})
        return self._job_data(job)

    def _job_state(self,p):
        job=self._staff_job(p['job_id']);target=p['state'];self._lock(job)
        if self._role()=='technician' and target in ['cancelled','assigned']:raise AccessError('Only reception or management can cancel or assign jobs.')
        if target=='cancelled':
            if job.state=='completed' or job.sale_order_id.invoice_ids.filtered(lambda i:i.state=='posted'):raise ValidationError('Invoiced or completed jobs cannot be cancelled here.')
            if job.sale_order_id:job.sale_order_id.action_cancel()
            self._stop_job_timers(job);job.state='cancelled'
        elif target=='assigned':
            if job.state!='approved' or not job.technician_id:raise ValidationError('Approve the quotation and assign a technician first.')
            job.state='assigned'
        else:job._technician_update(target,self._text(p.get('note')))
        if p.get('quality_rating') is not None:job.quality_rating=self._number(p['quality_rating'],5)
        return self._job_data(job)

    def _job_review(self,p):
        job=self._staff_job(p['job_id']);job.quality_rating=self._number(p.get('quality_rating'),5)
        return self._job_data(job)

    def _check_update(self,p):
        job=self._staff_job(p['job_id']);check=job.checklist_ids.filtered(lambda r:r.id==int(p['id']))
        if not check or job.state in ['completed','cancelled'] or not isinstance(p.get('done'),bool):raise ValidationError('Invalid inspection update.')
        check.done=p['done'];return self._job_data(job)

    def _note_add(self,p):
        job=self._staff_job(p['job_id']);content=self._text(p.get('content'))
        if not content:raise ValidationError('Enter a note.')
        self._env('workshop.note').create({'job_id':job.id,'author_id':request.env.uid,'content':content,'kind':self._choice(p.get('kind','progress'),['progress','issue','resolution'])})
        return self._job_data(job)

    def _timer_start(self,p):
        job=self._staff_job(p['job_id'])
        request.env.cr.execute('SELECT id FROM res_users WHERE id=%s FOR UPDATE',(request.env.uid,))
        if job.state!='in_progress':raise ValidationError('Start or resume this repair first.')
        if self._env('workshop.time').search_count([('technician_id','=',request.env.uid),('end','=',False)]):raise ValidationError('Stop your existing timer before starting another.')
        self._env('workshop.time').create({'job_id':job.id,'technician_id':request.env.uid,'activity':self._text(p.get('activity') or 'Repair work',250)})
        return self._job_data(job)

    def _timer_stop(self,p):
        job=self._staff_job(p['job_id']);self._stop_job_timers(job,request.env.uid);return self._job_data(job)

    def _stop_job_timers(self,job,uid=None):
        domain=[('job_id','=',job.id),('end','=',False)]
        if uid:domain.append(('technician_id','=',uid))
        self._env('workshop.time').search(domain).write({'end':fields.Datetime.now()})

    def _photo_save(self,p):
        job=self._staff_job(p['job_id'])
        if job.state=='cancelled':raise ValidationError('Cancelled job.')
        try:
            raw,mime=photo_bytes(p.get('image'))
            from PIL import Image
            with Image.open(BytesIO(raw)) as image:
                if image.width*image.height>25000000:raise ValueError('Image too large.')
                image.verify()
        except Exception as exc:raise ValidationError('Upload a valid JPEG/PNG up to 5 MB and 25 megapixels.') from exc
        self._env('workshop.photo').create({'job_id':job.id,'name':self._text(p.get('name') or 'Repair photo',120),
            'image':base64.b64encode(raw),'mimetype':mime,'author_id':request.env.uid,
            'kind':self._choice(p.get('kind','during'),['before','during','after','issue']),'description':self._text(p.get('description'),250)})
        return self._job_data(job)

    def _photo_edit(self,p):
        job=self._staff_job(p['job_id']);photo=job.photo_ids.filtered(lambda r:r.id==int(p['id']))
        if not photo:raise AccessError('Photo not in this job.')
        photo.write({'description':self._text(p.get('description'),250),'kind':self._choice(p.get('kind','during'),['before','during','after','issue'])})
        return self._job_data(job)

    def _photo_delete(self,p):
        job=self._staff_job(p['job_id']);photo=job.photo_ids.filtered(lambda r:r.id==int(p['id']))
        if not photo:raise AccessError('Photo not in this job.')
        photo.unlink();return self._job_data(job)

    def _part_request(self,p):
        job=self._staff_job(p['job_id']);product=self._record('product.product',p['product_id'],True)
        if not product.is_storable or job.state in ['completed','cancelled']:raise ValidationError('Choose an inventory part for an open job.')
        try:quantity=positive_quantity(p.get('quantity'))
        except ValueError as exc:raise ValidationError(str(exc)) from exc
        self._env('workshop.part.request').create({'job_id':job.id,'product_id':product.id,'quantity':quantity,'note':self._text(p.get('note'))})
        return self._job_data(job)

    def _job_part(self,p):
        job=self._staff_job(p['job_id']);part=job.part_ids.filtered(lambda r:r.id==int(p['id']))
        if not part:raise AccessError('Part request not in this job.')
        return job,part

    def _part_issue(self,p):
        job,part=self._job_part(p);part.action_issue();return self._job_data(job)
    def _part_reject(self,p):
        job,part=self._job_part(p)
        if part.state!='requested':raise ValidationError('Only pending requests can be rejected.')
        part.state='rejected';return self._job_data(job)
    def _part_use(self,p):
        job,part=self._job_part(p)
        if part.state!='issued':raise ValidationError('Stock must be issued before marking it used.')
        part.used=bool(p.get('used'));return self._job_data(job)

    def _lines(self,lines,invoice=False):
        if not isinstance(lines,list) or not 1<=len(lines)<=100:raise ValidationError('Add 1 to 100 quotation/invoice lines.')
        result=[]
        for line in lines:
            product=self._record('product.product',line.get('product_id') or request.env.ref('workshop_hub.product_labour').id,True)
            qty=self._number(line.get('qty',1),10000)
            if qty<=0:raise ValidationError('Line quantities must be positive.')
            taxes=[]
            for tax_id in line.get('tax_ids',[]):
                tax=self._record('account.tax',tax_id)
                if tax.type_tax_use!='sale':raise ValidationError('Choose sales taxes.')
                taxes.append(tax.id)
            values={'product_id':product.id,'name':self._text(line.get('description') or product.display_name,1000),
              'quantity' if invoice else 'product_uom_qty':qty,'price_unit':self._number(line.get('unit_price')),
              'discount':self._number(line.get('discount'),100),
              'tax_ids' if invoice else 'tax_id':[Command.set(taxes)]}
            result.append(Command.create(values))
        return result

    def _estimate_save(self,p):
        job=self._staff_job(p['job_id'])
        if job.state in ['completed','cancelled']:raise ValidationError('Closed jobs cannot receive new quotations.')
        first_quote=job.state in ['requested','awaiting_approval']
        order=self._record('sale.order',p['id']) if p.get('id') else job.sale_order_id if first_quote else False
        if order and order.state=='cancel' and not p.get('id'):order=False
        if order and (order.workshop_job_id and order.workshop_job_id!=job):raise ValidationError('Quotation belongs to another job.')
        if order and order.state not in ['draft','sent']:raise ValidationError('Confirmed quotations cannot be edited here.')
        discount=self._number(p.get('discount_amount'))
        subtotal=sum(self._number(line.get('qty'))*self._number(line.get('unit_price'))*(1-self._number(line.get('discount'),100)/100) for line in p.get('lines',[]))
        if discount>subtotal:raise ValidationError('Order discount cannot exceed the untaxed line subtotal.')
        commands=self._lines(p.get('lines'))
        if discount:commands.append(Command.create({'product_id':request.env.ref('workshop_hub.product_labour').id,'name':'Workshop order discount','product_uom_qty':1,'price_unit':-discount,'tax_id':[Command.clear()]}))
        values={'partner_id':job.partner_id.id,'company_id':job.company_id.id,'workshop_job_id':job.id,
          'origin':job.name,'validity_date':fields.Date.to_date(p['validity_date']) if p.get('validity_date') else fields.Date.today()+timedelta(days=15),
          'note':self._text(p.get('notes')),'workshop_discount_amount':discount,'order_line':[Command.clear()]+commands}
        if order:order.write(values)
        else:order=self._env('sale.order').create(values)
        if first_quote:
            job.sale_order_id=order
            job.state='requested'
        return self._estimate_data(order)

    def _order(self,p):
        order=self._record('sale.order',p['id'])
        if not order.workshop_job_id:raise AccessError('This is not a workshop estimate.')
        return order

    def _estimate_send(self,p):
        order=self._order(p);job=order.workshop_job_id
        if order.state not in ['draft','sent'] or job.state in ['completed','cancelled']:raise ValidationError('Use a draft quotation on an open job.')
        order.write({'state':'sent'})
        if job.sale_order_id==order:job.state='awaiting_approval'
        if p.get('email'):
            if not order.partner_id.email:raise ValidationError('Customer email is missing.')
            template=request.env.ref('sale.email_template_edi_sale',raise_if_not_found=False)
            if not template:raise ValidationError('Configure the Odoo sales quotation email template.')
            template.sudo().send_mail(order.id,force_send=False)
        return self._estimate_data(order)

    def _estimate_approve(self,p):
        order=self._order(p);job=order.workshop_job_id;reason=self._text(p.get('reason'),500)
        if len(reason)<8:raise ValidationError('Record how the customer approved this quotation.')
        self._lock(order)
        if order.state not in ['draft','sent'] or job.state in ['completed','cancelled']:raise ValidationError('Only a draft quotation on an open job can be approved.')
        order.action_confirm()
        if job.sale_order_id==order:job.state='approved'
        job.message_post(body='Approval recorded by %s: %s'%(request.env.user.name,reason))
        return self._estimate_data(order)

    def _estimate_reject(self,p):
        order=self._order(p)
        if order.state not in ['draft','sent']:raise ValidationError('Only draft or sent estimates can be rejected.')
        order.action_cancel()
        if order.workshop_job_id.sale_order_id==order:order.workshop_job_id.state='requested'
        return self._estimate_data(order)

    def _estimate_duplicate(self,p):
        order=self._order(p)
        job=self._staff_job(p.get('job_id') or order.workshop_job_id.id)
        if job.state in ['completed','cancelled']:raise ValidationError('Choose an open job for the copied estimate.')
        duplicate=order.copy({'workshop_job_id':job.id,'partner_id':job.partner_id.id,'origin':job.name,'state':'draft'})
        if job.state in ['requested','awaiting_approval']:job.write({'sale_order_id':duplicate.id,'state':'requested'})
        return self._estimate_data(duplicate)

    def _estimate_delete(self,p):
        order=self._order(p)
        if order.state not in ['draft','cancel']:raise ValidationError('Only draft or cancelled estimates can be deleted.')
        job=order.workshop_job_id
        if job.sale_order_id==order:job.write({'sale_order_id':False,'state':'requested'})
        order.unlink();return {'ok':True}

    def _inventory_save(self,p):
        category_name=self._text(p.get('category') or 'Spare Parts',100)
        category=self._env('product.category').search([('name','=',category_name)],limit=1) or self._env('product.category').create({'name':category_name})
        values={'name':self._text(p.get('name'),200),'default_code':self._text(p.get('sku'),80),
          'description_sale':self._text(p.get('description')),'categ_id':category.id,
          'standard_price':self._number(p.get('unit_cost')),'list_price':self._number(p.get('retail_price')),
          'workshop_min_stock':self._number(p.get('min_stock_level')),'workshop_max_stock':self._number(p.get('max_stock_level')),
          'workshop_bin':self._text(p.get('location'),100)}
        if not values['name'] or not values['default_code']:raise ValidationError('SKU and name are required.')
        if p.get('supplier_name'):
            supplier=self._env('res.partner').create({'name':self._text(p['supplier_name'],120),'supplier_rank':1,'company_id':self._company()})
            values['workshop_supplier_id']=supplier.id
        elif p.get('supplier_id'):values['workshop_supplier_id']=self._record('res.partner',p['supplier_id'],True).id
        else:values['workshop_supplier_id']=False
        if p.get('id'):
            product=self._record('product.product',p['id'],True);product.write(values)
        else:
            product=self._env('product.product').create({**values,'type':'consu','is_storable':True,'invoice_policy':'order','company_id':self._company()})
            if self._number(p.get('quantity')):self._add_stock(product,self._number(p['quantity']),'Opening workshop stock')
        return self._inventory_data(product)

    def _add_stock(self,product,quantity,reference):
        warehouse=self._env('stock.warehouse').search([('company_id','=',self._company())],limit=1)
        if not warehouse:raise ValidationError('Configure a warehouse.')
        self._lock(product)
        quant=self._env('stock.quant').search([('product_id','=',product.id),('location_id','=',warehouse.lot_stock_id.id),('lot_id','=',False),('package_id','=',False),('owner_id','=',False)],limit=1)
        if not quant:quant=self._env('stock.quant').create({'product_id':product.id,'location_id':warehouse.lot_stock_id.id})
        quant.with_context(inventory_mode=True).write({'inventory_quantity':quant.quantity+quantity})
        quant.with_context(inventory_name=reference).action_apply_inventory()

    def _inventory_stock(self,p):
        product=self._record('product.product',p['id'],True)
        if not product.is_storable:raise ValidationError('This is not an inventory-tracked part.')
        try:qty=positive_quantity(p.get('quantity'))
        except ValueError as exc:raise ValidationError(str(exc)) from exc
        self._add_stock(product,qty,self._text(p.get('reference') or 'Workshop stock receipt',200))
        if p.get('unit_cost') is not None:product.standard_price=self._number(p['unit_cost'])
        return self._inventory_data(product)

    def _invoice(self,p):
        invoice=self._record('account.move',p['id'])
        if not invoice.workshop_job_id or invoice.move_type not in ['out_invoice','out_refund']:raise AccessError('Not a workshop invoice.')
        return invoice

    def _invoice_create(self,p):
        job=self._staff_job(p['job_id']);self._lock(job)
        if job.state!='completed' or not job.sale_order_id or job.sale_order_id.state!='sale':raise ValidationError('Complete a job with an approved quotation before invoicing.')
        orders=job.quote_ids.filtered(lambda order:order.state=='sale')|job.sale_order_id
        invoiceable=orders.filtered(lambda order:order.invoice_status=='to invoice')
        invoices=invoiceable._create_invoices() if invoiceable else orders.invoice_ids.filtered(lambda i:i.move_type=='out_invoice' and i.state!='cancel')
        if invoices and not invoiceable:return self._invoice_data(invoices[0])
        if not invoices:raise ValidationError('No invoiceable lines. Validate the parts delivery first if using delivered-quantity billing.')
        invoices.write({'workshop_job_id':job.id,'invoice_date':fields.Date.to_date(p['date']) if p.get('date') else fields.Date.today(),
           'invoice_date_due':fields.Date.to_date(p['due_date']) if p.get('due_date') else fields.Date.today()})
        for invoice in invoices:invoice.workshop_discount_amount=-sum(invoice.invoice_line_ids.filtered(lambda line:line.name=='Workshop order discount').mapped('price_total'))
        return self._invoice_data(invoices[0])

    def _invoice_save(self,p):
        invoice=self._invoice(p)
        if invoice.state!='draft':raise ValidationError('Only draft invoices can be edited.')
        if p.get('discount_amount') is not None:
            discount=self._number(p['discount_amount'])
            discount_lines=invoice.invoice_line_ids.filtered(lambda line:line.name in ['Workshop order discount','Workshop invoice discount'])
            gross=invoice.amount_total-sum(discount_lines.mapped('price_total'))
            if discount>gross:raise ValidationError('Discount cannot exceed the invoice total before discounts.')
            discount_lines.unlink()
            if discount:invoice.write({'invoice_line_ids':[Command.create({'product_id':request.env.ref('workshop_hub.product_labour').id,'name':'Workshop invoice discount','quantity':1,'price_unit':-discount,'tax_ids':[Command.clear()]})]})
            invoice.workshop_discount_amount=discount
        invoice.write({'invoice_date':fields.Date.to_date(p['date']) if p.get('date') else fields.Date.today(),
          'invoice_date_due':fields.Date.to_date(p['due_date']) if p.get('due_date') else fields.Date.today(),
          'narration':self._text(p.get('notes'))})
        return self._invoice_data(invoice)
    def _invoice_post(self,p):
        invoice=self._invoice(p);invoice.action_post();return self._invoice_data(invoice)
    def _invoice_cancel(self,p):
        invoice=self._invoice(p)
        if invoice.state!='draft':raise ValidationError('Posted invoices need a credit note. Only drafts may be cancelled here.')
        invoice.button_cancel();return self._invoice_data(invoice)
    def _invoice_email(self,p,reminder):
        invoice=self._invoice(p)
        if invoice.state!='posted' or not invoice.partner_id.email:raise ValidationError('Post the invoice and add a customer email first.')
        template=request.env.ref('account.email_template_edi_invoice',raise_if_not_found=False)
        if not template:raise ValidationError('Configure the invoice email template.')
        if reminder:invoice.message_post(body='Payment reminder requested by %s.'%request.env.user.name)
        template.sudo().send_mail(invoice.id,force_send=False)
        return {'ok':True,'message':'Email queued in Odoo. Delivery requires a configured outgoing mail server.'}

    def _register_payment(self,invoice,p,refund_of=None):
        if invoice.state!='posted':raise ValidationError('Post the invoice/credit note first.')
        self._lock(invoice)
        amount=self._number(p.get('amount'))
        if amount<=0 or invoice.currency_id.compare_amounts(amount,invoice.amount_residual)>0:raise ValidationError('Payment must be positive and cannot exceed the remaining balance.')
        journal=self._record('account.journal',p['journal_id'])
        method=self._choice(p.get('method','cash'),['cash','bank','card','check','other'])
        if journal.type not in ['cash','bank'] or (method=='cash' and journal.type!='cash'):raise ValidationError('Choose the appropriate cash or bank journal.')
        outbound=invoice.move_type=='out_refund'
        methods=journal.outbound_payment_method_line_ids if outbound else journal.inbound_payment_method_line_ids
        methodline=methods.filtered(lambda m:m.code=='manual')[:1]
        if not methodline:raise ValidationError('Configure a manual payment method and outstanding account on this journal.')
        last4=self._text(p.get('last4'),4)
        if last4 and (len(last4)!=4 or not last4.isdigit()):raise ValidationError('Card last four digits must contain exactly four digits.')
        wizard=self._env('account.payment.register').with_context(active_model='account.move',active_ids=invoice.ids).create({
            'amount':amount,'payment_date':fields.Date.to_date(p['date']) if p.get('date') else fields.Date.today(),
            'journal_id':journal.id,'payment_method_line_id':methodline.id,'communication':self._text(p.get('reference') or invoice.name,250)})
        payments=wizard._create_payments()
        if len(payments)!=1:raise ValidationError('Expected one payment. Review invoice installments in Odoo.')
        payments.write({'workshop_invoice_id':invoice.id,'workshop_method':method,
            'workshop_reference':self._text(p.get('reference'),250),'workshop_transaction':self._text(p.get('transaction'),100),
            'workshop_last4':last4,'workshop_bank':self._text(p.get('bank'),120),'workshop_notes':self._text(p.get('notes')),
            'workshop_refund_of_id':refund_of.id if refund_of else False})
        return payments

    def _payment_create(self,p):
        invoice=self._invoice({'id':p['invoice_id']})
        if invoice.move_type!='out_invoice':raise ValidationError('Use the refund action for credit notes.')
        return self._payment_data(self._register_payment(invoice,p))

    def _payment(self,p):
        payment=self._record('account.payment',p['id'])
        if not payment.workshop_invoice_id:raise AccessError('Not a workshop payment.')
        return payment

    def _payment_cancel(self,p):
        payment=self._payment(p)
        if payment.is_matched or payment.workshop_refund_of_id or self._env('account.payment').search_count([('workshop_refund_of_id','=',payment.id)]):raise ValidationError('Matched or refunded payments need accountant review in Odoo.')
        payment.move_id.line_ids.remove_move_reconcile()
        payment.action_draft();payment.action_cancel()
        return self._payment_data(payment)

    def _payment_refund(self,p):
        payment=self._payment(p);self._lock(payment)
        invoice=payment.workshop_invoice_id
        if payment.payment_type!='inbound' or payment.state in ['draft','canceled','cancelled']:raise ValidationError('Only recorded incoming payments can be refunded.')
        refunded=self._env('account.payment').search([('workshop_refund_of_id','=',payment.id),('state','not in',['draft','canceled'])])
        amount=self._number(p.get('amount'))
        if amount<=0 or invoice.currency_id.compare_amounts(amount,payment.amount-sum(refunded.mapped('amount')))>0:raise ValidationError('Refund exceeds the unrefunded payment amount.')
        reason=self._text(p.get('reason'),500)
        if len(reason)<8:raise ValidationError('Record a refund reason.')
        credit=invoice._reverse_moves([{'date':fields.Date.today(),'ref':reason,'workshop_job_id':invoice.workshop_job_id.id}],cancel=False)
        if credit.state!='draft':raise ValidationError('The reversal needs accountant review before refunding.')
        ratio=amount/invoice.amount_total
        credit.workshop_discount_amount=invoice.workshop_discount_amount*ratio
        for line in credit.invoice_line_ids.filtered(lambda l:l.display_type in [False,'product']):line.quantity*=ratio
        if abs(credit.amount_total-amount)>invoice.currency_id.rounding*2:raise ValidationError('Tax rounding prevents this partial refund; review the credit note in Odoo.')
        credit.action_post()
        values={**p,'amount':credit.amount_residual,'journal_id':p.get('journal_id') or payment.journal_id.id,'method':p.get('method') or payment.workshop_method}
        result=self._register_payment(credit,values,payment)
        invoice.message_post(body='Refund recorded by %s: %s'%(request.env.user.name,reason))
        return self._payment_data(result)

    def _user_save(self,p):
        role=self._choice(p.get('role'),['admin','manager','receptionist','accountant','technician'])
        login=self._text(p.get('email'),254);name=self._text(p.get('name'),120)
        if not login or not name:raise ValidationError('Name and login email are required.')
        group=request.env.ref('workshop_hub.group_manager' if role in ['admin','manager'] else 'workshop_hub.group_'+role)
        groups=[group.id]
        if role=='admin':groups.append(request.env.ref('base.group_system').id)
        values={'name':name,'login':login,'email':login,'workshop_specialization':self._text(p.get('specialization'),200)}
        if p.get('password'):
            if len(p['password'])<12:raise ValidationError('Use a password of at least 12 characters.')
            values['password']=p['password']
        if p.get('id'):
            user=self._record('res.users',p['id'],True)
            if user.id==request.env.uid and role!='admin':raise ValidationError('You cannot remove your own administrator access.')
            oldrole=self._user_role(user)
            if not oldrole:raise ValidationError('This account is not managed by Workshop Hub.')
            # A role change replaces access groups, so previous finance/admin
            # memberships cannot survive a downgrade to technician/reception.
            values['groups_id']=[Command.set(groups)]
            user.write(values)
        else:
            if 'password' not in values:raise ValidationError('Set an initial password.')
            user=self._env('res.users').with_context(no_reset_password=True).create({**values,'company_id':self._company(),
                'company_ids':[Command.set([self._company()])],'groups_id':[Command.set(groups)]})
        user.partner_id.phone=self._text(p.get('phone'),40)
        return self._user_data(user)

    def _archive_user(self,p):
        user=self._record('res.users',p['id'],True)
        if user.id==request.env.uid or not self._user_role(user):raise ValidationError('You cannot archive yourself or an unmanaged system account.')
        user.active=False;return {'id':user.id}

    def _document(self,p):
        kind=p.get('kind')
        if kind=='photo':
            job=self._staff_job(p['job_id']);photo=job.photo_ids.filtered(lambda r:r.id==int(p['id']))
            if not photo:raise AccessError('Photo not in this job.')
            return {'name':photo.name,'content':photo.image.decode(),'mimetype':photo.mimetype}
        if kind=='estimate':
            if not allow(self._role(),'detail','estimates'):raise AccessError('Access denied.')
            record=self._order(p);report='sale.action_report_saleorder'
        elif kind=='invoice':
            if not allow(self._role(),'detail','invoices'):raise AccessError('Access denied.')
            record=self._invoice(p);report='account.account_invoices'
        elif kind=='receipt':
            if not allow(self._role(),'detail','payments'):raise AccessError('Access denied.')
            record=self._payment(p);report='account.action_report_payment_receipt'
        else:raise ValidationError('Invalid document type.')
        content,_=self._env('ir.actions.report')._render_qweb_pdf(report,res_ids=record.ids)
        return {'name':kind+'-%s.pdf'%record.id,'content':base64.b64encode(content).decode(),'mimetype':'application/pdf'}

    def _purchase_data(self,order):
        return {'id':order.id,'name':order.name,'supplier':order.partner_id.name,'state':order.state,
                'total':order.amount_total,'currency':order.currency_id.name,'date':str(order.date_order),
                'lines':[{'name':l.name,'qty':l.product_qty,'price':l.price_unit} for l in order.order_line if not l.display_type]}
    def _purchase_create(self,p):
        supplier=self._record('res.partner',p['supplier_id'],True);product=self._record('product.product',p['product_id'],True)
        try:qty=positive_quantity(p.get('quantity'))
        except ValueError as exc:raise ValidationError(str(exc)) from exc
        order=self._env('purchase.order').create({'partner_id':supplier.id,'company_id':self._company(),
          'order_line':[Command.create({'product_id':product.id,'name':product.display_name,'product_qty':qty,
           'product_uom':product.uom_po_id.id,'price_unit':self._number(p.get('unit_cost')),'date_planned':fields.Datetime.now()})]})
        return self._purchase_data(order)
    def _purchase_confirm(self,p):
        order=self._record('purchase.order',p['id']);order.button_confirm();return self._purchase_data(order)
    def _purchase_receive(self,p):
        order=self._record('purchase.order',p['id'])
        if order.state not in ['purchase','done']:raise ValidationError('Confirm the purchase order first.')
        for picking in order.picking_ids.filtered(lambda r:r.state not in ['done','cancel']):
            picking.action_assign()
            for move in picking.move_ids.filtered(lambda r:r.state not in ['done','cancel']):
                if move.product_id.tracking!='none':raise ValidationError('Tracked lots/serials need an Odoo receipt review.')
                move.quantity=move.product_uom_qty;move.picked=True
            picking.button_validate()
            if picking.state!='done':raise ValidationError('Receipt needs manual review.')
        return self._purchase_data(order)

    def _report(self,p,dashboard=False):
        company=self._company();domain=[('company_id','=',company)]
        if self._role()=='technician':domain += [('technician_id','=',request.env.uid)]
        if p.get('date_from'):domain += [('create_date','>=',str(fields.Date.to_date(p['date_from']))+' 00:00:00')]
        if p.get('date_to'):domain += [('create_date','<=',str(fields.Date.to_date(p['date_to']))+' 23:59:59')]
        if p.get('state'):domain += [('state','=',p['state'])]
        if p.get('technician_id'):domain += [('technician_id','=',int(p['technician_id']))]
        if p.get('job_type'):domain += [('job_type','=',p['job_type'])]
        jobs=self._env('workshop.job').search(domain)
        invoice_domain=[('company_id','=',company),('workshop_job_id','!=',False),('state','=','posted'),('move_type','in',['out_invoice','out_refund'])]
        if p.get('date_from'):invoice_domain.append(('invoice_date','>=',p['date_from']))
        if p.get('date_to'):invoice_domain.append(('invoice_date','<=',p['date_to']))
        if p.get('payment_state'):invoice_domain.append(('payment_state','=',p['payment_state']))
        if self._role()=='technician':invoice_domain.append(('workshop_job_id','in',jobs.ids))
        invoices=self._env('account.move').search(invoice_domain)
        payment_domain=[('company_id','=',company),('workshop_invoice_id','!=',False),('state','not in',['draft','canceled'])]
        if p.get('date_from'):payment_domain.append(('date','>=',p['date_from']))
        if p.get('date_to'):payment_domain.append(('date','<=',p['date_to']))
        if p.get('method'):payment_domain.append(('workshop_method','=',p['method']))
        payments=self._env('account.payment').search(payment_domain) if self._role()!='technician' else self._env('account.payment')
        if p.get('method'):invoices=invoices.filtered(lambda inv:inv.id in payments.workshop_invoice_id.ids)
        technicians=jobs.technician_id
        performance=[]
        for technician in technicians:
            own=jobs.filtered(lambda j:j.technician_id==technician);done=own.filtered(lambda j:j.state=='completed')
            hours=sum(own.task_ids.mapped('hours'));actual=sum(own.time_ids.mapped('minutes'))/60
            rated=done.filtered(lambda j:j.quality_rating>0)
            performance.append({'id':technician.id,'name':technician.name,'specialization':technician.workshop_specialization or '',
              'jobs':len(own),'completed':len(done),'active':len(own.filtered(lambda j:j.state not in ['completed','cancelled'])),
              'efficiency':round(hours/actual*100,1) if actual else None,
              'quality':round(sum(rated.mapped('quality_rating'))/len(rated),2) if rated else None,
              'minutes':round(sum(done.time_ids.mapped('minutes'))/len(done),1) if done else None,
              'revenue':sum(invoices.filtered(lambda i:i.workshop_job_id in own).mapped('amount_total_signed'))})
        if p.get('efficiency'):performance=[r for r in performance if r['efficiency'] is not None and r['efficiency']>=self._number(p['efficiency'])]
        if p.get('quality'):performance=[r for r in performance if r['quality'] is not None and r['quality']>=self._number(p['quality'],5)]
        if p.get('specialization'):performance=[r for r in performance if p['specialization'].lower() in r['specialization'].lower()]
        totals={'jobs':len(jobs),'completed':len(jobs.filtered(lambda j:j.state=='completed')),
           'active':len(jobs.filtered(lambda j:j.state not in ['completed','cancelled'])),
           'customers':self._env('res.partner').search_count([('workshop_customer','=',True),'|',('company_id','=',False),('company_id','=',company)]),
           'invoiced':sum(invoices.mapped('amount_total_signed')),
           'outstanding':sum(invoices.filtered(lambda i:i.move_type=='out_invoice').mapped('amount_residual_signed')),
           'received':sum(pay.currency_id._convert(pay.amount,request.env.company.currency_id,request.env.company,pay.date)*(1 if pay.payment_type=='inbound' else -1) for pay in payments),
           'awaiting_approval':len(jobs.filtered(lambda j:j.state=='awaiting_approval'))}
        if dashboard:
            return {'totals':totals,'recent':[self._job_data(job) for job in jobs[:10]],'technicians':performance,
              'currency':request.env.company.currency_id.name,'company':request.env.company.name,'user':self.me(),
              'statuses':[{'name':state,'count':len(jobs.filtered(lambda j:j.state==state))} for state in ['requested','awaiting_approval','approved','assigned','in_progress','paused','waiting_parts','completed','cancelled']]}
        kind=p.get('kind','jobs')
        if kind=='technician':rows=performance
        elif kind=='revenue':rows=[self._invoice_data(inv,False) for inv in invoices]
        elif kind=='payments':rows=[self._payment_data(pay) for pay in payments]
        else:rows=[{k:v for k,v in self._job_data(j).items() if k in ['id','name','customer','vehicle','job_type','state','technician','total','currency','created_at','completed_at','quality_rating']} for j in jobs]
        return {'rows':rows,'totals':totals,'currency':request.env.company.currency_id.name}
