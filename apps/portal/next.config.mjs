import {fileURLToPath} from 'node:url';

/** @type {import('next').NextConfig} */
export default {
  turbopack: {root: fileURLToPath(new URL('.', import.meta.url))},
  // Use the installed TypeScript 5 compiler API; retain full build type checking.
  experimental: {useTypeScriptCli: false},
  async rewrites() {
    // Transport-only proxy. Authentication, API responses and business logic live in Odoo.
    return [{source: '/api/:path*', destination: `${(process.env.ODOO_URL || 'http://127.0.0.1:8070').replace(/\/$/, '')}/workshop/rest/:path*`}];
  },
};
