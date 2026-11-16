"""Backfill relationships created by version 1 of this generated project only."""
for job in env['workshop.job'].search([]):
    job.partner_id.workshop_customer=True
    order=job.sale_order_id
    if order and not order.workshop_job_id:
        order.workshop_job_id=job
    if order:
        for invoice in order.invoice_ids.filtered(lambda inv:not inv.workshop_job_id):
            invoice.workshop_job_id=job
env.cr.commit()
print('Existing Workshop Hub links updated. No original external database was imported.')
