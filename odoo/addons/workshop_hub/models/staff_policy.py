"""Explicit staff operation permissions, usable by standalone tests."""
ALL = {'admin','manager','receptionist','accountant','technician'}
OFFICE = {'admin','manager','receptionist'}
FINANCE = {'admin','manager','accountant'}
MANAGE = {'admin','manager'}
PERMISSIONS = {
 'dashboard':ALL,'lookups':ALL,'list':ALL,'detail':ALL,
 'customer.save':OFFICE,'customer.archive':MANAGE,'customer.portal':MANAGE,
 'vehicle.save':OFFICE,'vehicle.archive':MANAGE,
 'job.save':OFFICE,'job.archive':MANAGE,'job.state':OFFICE|{'technician'},'job.review':MANAGE,'check.update':OFFICE|{'technician'},
 'task.save':OFFICE,'task.delete':OFFICE,'task.update':OFFICE|{'technician'},
 'note.add':OFFICE|{'technician'},'timer.start':{'technician'},'timer.stop':{'technician'},
 'photo.save':OFFICE|{'technician'},'photo.edit':OFFICE|{'technician'},'photo.delete':OFFICE|{'technician'},
 'part.use':OFFICE|{'technician'},'part.request':OFFICE|{'technician'},'part.issue':MANAGE,'part.reject':OFFICE,
 'estimate.save':OFFICE,'estimate.send':OFFICE,'estimate.approve':MANAGE,'estimate.reject':OFFICE,
 'estimate.duplicate':OFFICE,'estimate.delete':MANAGE,
 'inventory.save':MANAGE,'inventory.stock':MANAGE,'inventory.archive':MANAGE,
 'invoice.create':FINANCE,'invoice.save':FINANCE,'invoice.post':FINANCE,'invoice.cancel':FINANCE,
 'invoice.email':FINANCE,'invoice.remind':FINANCE,'document':ALL,
 'payment.create':FINANCE,'payment.cancel':FINANCE,'payment.refund':FINANCE,
 'user.save':{'admin'},'user.archive':{'admin'},'report':MANAGE|{'accountant'},
 'purchase.create':MANAGE,'purchase.confirm':MANAGE,'purchase.receive':MANAGE,
}
READ = {
 'customers':OFFICE|{'accountant'},'vehicles':OFFICE,'jobs':ALL,'work':OFFICE|{'technician'},
 'estimates':OFFICE|{'accountant'},'inventory':MANAGE|{'accountant'},'transactions':MANAGE|{'accountant'},
 'invoices':OFFICE|{'accountant'},'payments':FINANCE,'users':{'admin'},'purchases':MANAGE|{'accountant'},
}
def allow(role, action, entity=None):
    if role not in PERMISSIONS.get(action,set()):
        return False
    if action in {'list','detail'}:
        return role in READ.get(entity,set())
    return True
