{
    'name': 'Workshop Hub',
    'version': '18.0.3.0.0',
    'license': 'LGPL-3',
    'category': 'Services',
    'depends': ['crm', 'sale_management', 'sale_stock', 'purchase_stock', 'account', 'portal'],
    'data': [
        'security/groups.xml', 'security/ir.model.access.csv',
        'security/rules.xml', 'data/sequence.xml', 'views/workshop_views.xml', 'views/shop_views.xml',
    ],
    'application': True,
    'installable': True,
}
