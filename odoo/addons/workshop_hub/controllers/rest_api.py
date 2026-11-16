"""The public REST API lives in Odoo. Next.js only reverse-proxies its URL."""
import json
import logging
import os
import re
import time
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied, AccessError, UserError
from odoo.service import security
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from .staff_api import StaffAPI
from .shop_api import ShopAPI

_logger = logging.getLogger(__name__)
COOKIE = 'workshop_session'
SESSION_SECONDS = 8 * 60 * 60


class WorkshopREST(http.Controller):
    def _response(self, data, status=200, origin=None):
        headers = [('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]
        if origin:
            headers += [('Access-Control-Allow-Origin', origin), ('Access-Control-Allow-Credentials', 'true'),
                        ('Access-Control-Allow-Headers', 'Authorization, Content-Type'),
                        ('Access-Control-Allow-Methods', 'POST, OPTIONS'), ('Vary', 'Origin')]
        return request.make_json_response(data, status=status, headers=headers)

    def _load_session(self):
        authorization = request.httprequest.headers.get('Authorization', '')
        sid = authorization[7:] if authorization.startswith('Bearer ') else request.httprequest.cookies.get(COOKIE, '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', sid):
            raise AccessDenied('Please sign in.')
        session = http.root.session_store.get(sid)
        if not session.uid or session.db != request.db or session.get('workshop_expires_at', 0) < time.time():
            raise AccessDenied('Your session expired. Please sign in.')
        request.session = session
        request.session.can_save = False
        request.update_env(user=session.uid, context=session.context, su=False)
        if not security.check_session(session, request.env, request):
            raise AccessDenied('Your session expired. Please sign in.')
        return session

    @http.route('/workshop/rest/<path:action>', type='http', auth='none', methods=['POST', 'OPTIONS'],
                csrf=False, save_session=False, readonly=False, max_content_length=8 * 1024 * 1024)
    def dispatch(self, action, **unused):
        origin = request.httprequest.headers.get('Origin')
        allowed = {item.strip().rstrip('/') for item in os.getenv('WORKSHOP_ALLOWED_ORIGINS',
            'http://localhost:3001,http://127.0.0.1:3001').split(',') if item.strip()}
        if origin and origin not in allowed and origin != request.httprequest.host_url.rstrip('/'):
            return self._response({'error': 'Invalid request origin.'}, 403)
        if request.httprequest.method == 'OPTIONS':
            return self._response({}, origin=origin)
        if request.httprequest.mimetype != 'application/json':
            return self._response({'error': 'JSON is required.'}, 415, origin)
        if not request.db:
            return self._response({'error': 'Workshop database is unavailable.'}, 503, origin)
        try:
            params = json.loads(request.httprequest.get_data())
            if not isinstance(params, dict):
                return self._response({'error': 'Invalid parameters.'}, 400, origin)
            if action in ['auth/login', 'mobile/login']:
                login, password = params.get('login'), params.get('password')
                if not isinstance(login, str) or not isinstance(password, str) or not login or len(login) > 254 or len(password) > 1024:
                    return self._response({'error': 'Enter your email and password.'}, 400, origin)
                # Never reuse a caller-selected session ID during authentication.
                request.session = http.root.session_store.new()
                request.session.update(http.get_default_session())
                request.session.db = request.db
                info = request.session.authenticate(request.db, {'login': login, 'password': password, 'type': 'password'})
                if not info.get('uid') or info['uid'] != request.session.uid:
                    raise AccessDenied('Complete account authentication in Odoo.')
                user = StaffAPI().me()
                if action == 'mobile/login' and user['role'] not in ['customer', 'technician']:
                    request.session.can_save = False
                    return self._response({'error': 'Use a customer or technician account in the mobile app.'}, 403, origin)
                request.session['workshop_expires_at'] = time.time() + SESSION_SECONDS
                http.root.session_store.rotate(request.session, request.env)
                request.session.can_save = False
                result = {'user': user}
                if action == 'mobile/login':
                    result['session_id'] = request.session.sid
                response = self._response(result, origin=origin)
                if action == 'auth/login':
                    response.set_cookie(COOKIE, request.session.sid, max_age=SESSION_SECONDS,
                        httponly=True, samesite='Strict', path='/',
                        secure=request.httprequest.is_secure or os.getenv('WORKSHOP_COOKIE_SECURE') == '1')
                return response
            if action == 'auth/logout':
                try:
                    session = self._load_session()
                    http.root.session_store.delete(session)
                    session.logout(keep_db=True)
                    session.can_save = False
                except AccessDenied:
                    pass
                response = self._response({'ok': True}, origin=origin)
                response.delete_cookie(COOKIE, path='/')
                return response
            staff, shop = StaffAPI(), ShopAPI()
            handlers = {'me': staff.me, 'dashboard': staff.dashboard, 'job': staff.job,
                'vehicle': staff.vehicle, 'request': staff.service_request, 'approve': staff.approve,
                'status': staff.status, 'check': staff.check, 'photo': staff.photo, 'parts': staff.parts,
                'part-request': staff.part_request, 'invoice': staff.invoice, 'photo-get': staff.photo_get,
                'staff': staff.staff, 'shop/catalog': shop.catalog, 'shop/cart': shop.cart,
                'shop/cart/update': shop.cart_update, 'shop/checkout': shop.checkout,
                'shop/orders': shop.orders, 'shop/order': shop.order, 'shop/cancel': shop.cancel,
                'shop/invoice': shop.shop_invoice}
            self._load_session()
            if action not in handlers:
                return self._response({'error': 'Unknown API endpoint.'}, 404, origin)
            with request.env.cr.savepoint():
                result = handlers[action](**params)
            return self._response(result, origin=origin)
        except (AccessDenied, http.SessionExpiredException):
            return self._response({'error': 'Please sign in with a valid account.'}, 401, origin)
        except AccessError as error:
            return self._response({'error': str(error)}, 403, origin)
        except UserError as error:
            return self._response({'error': str(error)}, 400, origin)
        except (ValueError, TypeError, KeyError):
            return self._response({'error': 'Invalid request parameters.'}, 400, origin)
        except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
            # Odoo must retry the complete transaction after simultaneous cart
            # requests; returning a response here would swallow that mechanism.
            raise
        except Exception:
            _logger.exception('Workshop REST request failed: %s', action)
            return self._response({'error': 'Odoo could not complete this request. Please try again.'}, 500, origin)
