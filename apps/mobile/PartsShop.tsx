import React,{useEffect,useState} from 'react';
import {Image,Pressable,StyleSheet,Text,TextInput,View} from 'react-native';
import type {ApiCall,User} from './types';
import type {ShopCatalog,ShopOrder,ShopOrders} from './shop-types';
import {confirmAction} from './confirm';
import {saveInvoice} from './documents';

type Props={call:ApiCall;run:(action:()=>Promise<void>)=>Promise<void>;busy:boolean;user:User};
const money=(n:number,currency:string)=>new Intl.NumberFormat('en',{style:'currency',currency}).format(n);
function Button({title,onPress,disabled=false,secondary=false,label}:{title:string;onPress:()=>void;disabled?:boolean;secondary?:boolean;label?:string}){
  return <Pressable accessibilityRole="button" accessibilityLabel={label||title} disabled={disabled} onPress={onPress} style={[s.button,secondary&&s.secondary,disabled&&s.disabled]}><Text style={[s.buttonText,secondary&&s.secondaryText]}>{title}</Text></Pressable>;
}
export default function PartsShop({call,run,busy,user}:Props){
  const [mode,setMode]=useState<'catalog'|'cart'|'orders'>('catalog');
  const [catalog,setCatalog]=useState<ShopCatalog>({products:[],total:0,offset:0,limit:24,categories:[]});
  const [cart,setCart]=useState<ShopOrder|null>(null),[orders,setOrders]=useState<ShopOrders>({orders:[],total:0,offset:0,limit:20});
  const [search,setSearch]=useState(''),[category,setCategory]=useState(''),[notice,setNotice]=useState('');
  const [name,setName]=useState(user.name),[phone,setPhone]=useState(''),[note,setNote]=useState('');
  async function load(offset=0){const [products,current]=await Promise.all([call<ShopCatalog>('shop/catalog',{search,category,offset}),call<ShopOrder>('shop/cart')]);setCatalog(products);setCart(current);}
  useEffect(()=>{void run(()=>load());},[]);
  async function update(productId:number,quantity:number){setCart(await call<ShopOrder>('shop/cart/update',{product_id:productId,quantity}));}
  async function showOrders(offset=0){setOrders(await call<ShopOrders>('shop/orders',{offset}));setMode('orders');setNotice('');}
  async function checkout(){
    if(!cart)return;
    if(!await confirmAction('Place pickup order?',`${money(cart.total,cart.currency)} including tax. Collect and pay at the workshop. No online payment is taken.`,'Place order'))return;
    await run(async()=>{try{const order=await call<ShopOrder>('shop/checkout',{order_id:cart.id,version:cart.version,contact_name:name,contact_phone:phone,note});await showOrders();setCart(await call<ShopOrder>('shop/cart'));setNotice(`Order ${order.name} confirmed. Collect and pay at the workshop.`);}catch(error){setCart(await call<ShopOrder>('shop/cart'));throw error;}});
  }
  async function cancel(order:ShopOrder){if(await confirmAction('Cancel parts order?',`Cancel ${order.name} and release its stock reservation?`,'Cancel order'))await run(async()=>{await call('shop/cancel',{order_id:order.id});await showOrders(orders.offset);setNotice('Order cancelled.');});}
  return <View>
    <Text style={s.title}>Parts shop</Text><Text style={s.text}>Buy spare parts for collection and payment at your workshop.</Text>
    <View style={s.tabs}>{(['catalog','cart','orders'] as const).map(key=><Button key={key} title={key==='catalog'?'Browse parts':key==='cart'?`Cart (${cart?.lines.reduce((n,l)=>n+l.quantity,0)||0})`:'My parts orders'} secondary={mode!==key} disabled={busy} onPress={()=>{setNotice('');if(key==='orders')void run(()=>showOrders());else if(key==='cart')void run(async()=>{setCart(await call<ShopOrder>('shop/cart'));setMode('cart');});else setMode('catalog');}}/>)}</View>
    {!!notice&&<View accessibilityRole="alert" style={s.notice}><Text style={s.text}>{notice}</Text></View>}
    {mode==='catalog'&&<>
      <Text style={s.label}>Search by part, SKU or vehicle model</Text><TextInput accessibilityLabel="Search parts" value={search} onChangeText={setSearch} style={s.input} placeholder="e.g. oil filter"/>
      <View style={s.tabs}>{['',...catalog.categories].map(item=><Button key={item} title={item||'All categories'} secondary={category!==item} onPress={()=>setCategory(item)}/>)}</View>
      <Button title="Search catalogue" disabled={busy} onPress={()=>void run(()=>load())}/>
      {!catalog.products.length&&!busy&&<View style={s.card}><Text style={s.text}>No parts found. Try another search or contact your workshop.</Text></View>}
      {catalog.products.map(product=><View style={s.card} key={product.id}>
        {product.image&&<Image source={{uri:`data:image/png;base64,${product.image}`}} style={s.image} resizeMode="contain" accessibilityLabel={product.name}/>}
        <Text style={s.meta}>{product.category} · {product.sku}</Text><Text style={s.h2}>{product.name}</Text>
        <Text style={s.text}>{product.description||'Workshop spare part.'}</Text>{!!product.compatibility&&<Text style={s.text}>Fits: {product.compatibility}</Text>}
        <Text style={s.total}>{money(product.price,product.currency)}</Text><Text style={s.meta}>{product.available>0?`${product.available} ${product.unit} available`:'Out of stock'}</Text>
        <Text style={s.meta}>Taxes are calculated in your cart. Verify fit before ordering.</Text>
        <Button title={`Add ${product.name} to cart`} disabled={busy||product.available<=0} onPress={()=>void run(async()=>{await update(product.id,(cart?.lines.find(l=>l.product_id===product.id)?.quantity||0)+1);setNotice(`${product.name} added to cart.`);})}/>
      </View>)}
      <Text style={s.meta}>{catalog.total} parts</Text><View style={s.tabs}><Button title="Previous parts" secondary disabled={busy||catalog.offset===0} onPress={()=>void run(()=>load(Math.max(0,catalog.offset-24)))}/><Button title="Next parts" secondary disabled={busy||catalog.offset+24>=catalog.total} onPress={()=>void run(()=>load(catalog.offset+24))}/></View>
    </>}
    {mode==='cart'&&<>
      <Text style={s.h2}>Your cart</Text>{!cart?.lines.length?<View style={s.card}><Text style={s.text}>Your cart is empty. Browse parts to get started.</Text></View>:<>
        {cart.lines.map(line=><View style={s.card} key={line.id}><Text style={s.h2}>{line.name}</Text><Text style={s.text}>{money(line.unit_price,cart.currency)} each · Quantity: {line.quantity}</Text><View style={s.tabs}><Button title="−" label={`Decrease ${line.name}`} secondary disabled={busy} onPress={()=>void run(()=>update(line.product_id,Math.max(0,line.quantity-1)))}/><Button title="+" label={`Increase ${line.name}`} secondary disabled={busy} onPress={()=>void run(()=>update(line.product_id,line.quantity+1))}/></View><Text style={s.total}>{money(line.total,cart.currency)}</Text><Button title="Remove item" label={`Remove ${line.name}`} secondary disabled={busy} onPress={()=>void run(()=>update(line.product_id,0))}/></View>)}
        <View style={s.card}><Text style={s.text}>Subtotal: {money(cart.subtotal,cart.currency)}</Text><Text style={s.text}>Tax: {money(cart.tax,cart.currency)}</Text><Text style={s.total}>Total: {money(cart.total,cart.currency)}</Text>
          <Text style={s.h2}>Pickup details</Text><Text style={s.label}>Contact name</Text><TextInput accessibilityLabel="Collection contact name" value={name} onChangeText={setName} maxLength={120} style={s.input}/>
          <Text style={s.label}>Contact phone</Text><TextInput accessibilityLabel="Collection phone" value={phone} onChangeText={setPhone} keyboardType="phone-pad" maxLength={40} style={s.input}/>
          <Text style={s.label}>Order note / vehicle details</Text><TextInput accessibilityLabel="Parts order note" value={note} onChangeText={setNote} multiline maxLength={1000} style={s.input}/>
          <Text style={s.text}>Collect and pay at the workshop. Stock is reserved when you place the order. No online payment is collected.</Text>
          <Button title="Place pickup order" disabled={busy||name.trim().length<2||phone.trim().length<5} onPress={()=>void checkout()}/>
        </View>
      </>}
    </>}
    {mode==='orders'&&<><Text style={s.h2}>My parts orders</Text>{!orders.orders.length&&<Text style={s.text}>No parts orders yet.</Text>}
      {orders.orders.map(order=><View style={s.card} key={order.id}><Text style={s.h2}>{order.name}</Text><Text style={s.badge}>{order.status.replaceAll('_',' ')}</Text><Text style={s.meta}>{order.date} · Workshop pickup</Text>
        {order.lines.map(line=><View style={s.line} key={line.id}><Text style={s.lineText}>{line.name} × {line.quantity}</Text><Text style={s.text}>{money(line.total,order.currency)}</Text></View>)}
        <Text style={s.total}>Total: {money(order.total,order.currency)}</Text><Text style={s.text}>Contact: {order.contact_name} · {order.contact_phone}</Text>
        <Text style={s.meta}>Payment at the workshop. {order.invoices.length?'Invoice balances are shown below.':'No posted invoice yet.'}</Text>
        {order.invoices.map(invoice=><View key={invoice.id}><Text style={s.text}>{invoice.name} · {invoice.payment_state} · {money(invoice.balance,invoice.currency)} due</Text><Button title={`Download invoice ${invoice.name}`} secondary disabled={busy} onPress={()=>void run(async()=>{const file=await call<{name:string;content:string}>('shop/invoice',{order_id:order.id,invoice_id:invoice.id});await saveInvoice(file.name,file.content);})}/></View>)}
        {order.can_cancel&&<Button title={`Cancel order ${order.name}`} secondary disabled={busy} onPress={()=>void cancel(order)}/>}</View>)}
      <View style={s.tabs}><Button title="Previous orders" secondary disabled={busy||orders.offset===0} onPress={()=>void run(()=>showOrders(Math.max(0,orders.offset-20)))}/><Button title="Next orders" secondary disabled={busy||orders.offset+20>=orders.total} onPress={()=>void run(()=>showOrders(orders.offset+20))}/></View>
    </>}
  </View>;
}
const s=StyleSheet.create({title:{fontSize:30,color:'#183b2c',fontWeight:'700',marginVertical:12},h2:{fontSize:18,color:'#183b2c',fontWeight:'700',marginVertical:10},text:{fontSize:13,lineHeight:21,color:'#607463',marginVertical:7},meta:{fontSize:11,lineHeight:18,color:'#718075',marginVertical:5},card:{padding:20,backgroundColor:'white',borderRadius:16,borderWidth:1,borderColor:'#e0e7da',marginVertical:10},image:{width:90,height:90},total:{fontSize:19,fontWeight:'700',color:'#225641',marginVertical:12},tabs:{flexDirection:'row',flexWrap:'wrap',gap:7},button:{backgroundColor:'#225641',padding:13,borderRadius:9,alignItems:'center',maxWidth:'100%',marginVertical:5},buttonText:{fontSize:12,fontWeight:'600',color:'white'},secondary:{backgroundColor:'#ebf2e4'},secondaryText:{color:'#225641'},disabled:{opacity:.45},label:{fontSize:12,color:'#526253',marginTop:14,marginBottom:8},input:{padding:13,fontSize:14,borderWidth:1,borderColor:'#dce5d7',borderRadius:9,color:'#183b2c',backgroundColor:'#fff',marginBottom:8},notice:{padding:13,backgroundColor:'#e5f2da',borderRadius:9},badge:{backgroundColor:'#ecf2e6',color:'#52704d',padding:8,alignSelf:'flex-start',borderRadius:8,textTransform:'capitalize'},line:{flexDirection:'row',justifyContent:'space-between',gap:10,borderBottomWidth:1,borderColor:'#edf1e8',paddingVertical:7},lineText:{flex:1,fontSize:12,lineHeight:19,color:'#526253'}});
