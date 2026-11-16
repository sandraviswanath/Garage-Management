export type ShopProduct = {id:number;name:string;sku:string;description:string;category:string;compatibility:string;price:number;currency:string;available:number;unit:string;image:string|null};
export type ShopInvoice = {id:number;name:string;total:number;balance:number;currency:string;payment_state:string};
export type ShopOrder = {id:number;name:string;state:string;status:string;date:string;currency:string;subtotal:number;tax:number;total:number;version:string;can_cancel:boolean;contact_name:string;contact_phone:string;note:string;invoices:ShopInvoice[];lines:{id:number;product_id:number;name:string;sku:string;quantity:number;unit_price:number;total:number;available:number}[]};
export type ShopCatalog = {products:ShopProduct[];total:number;offset:number;limit:number;categories:string[]};
export type ShopOrders = {orders:ShopOrder[];total:number;offset:number;limit:number};
