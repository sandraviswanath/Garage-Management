import React, {useEffect, useRef, useState} from 'react';
import {Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View} from 'react-native';
import {confirmAction} from './confirm';
import {saveInvoice} from './documents';
import PartsShop from './PartsShop';
import type {ApiCall, Invoice, Job, Quote, User, Vehicle} from './types';

type Props = {
  user: User; jobs: Job[]; vehicles: Vehicle[]; busy: boolean;
  call: ApiCall; run: (action: () => Promise<void>) => Promise<void>;
  refresh: () => Promise<void>; openPhoto: (jobId: number, photoId: number) => Promise<void>;
};
type Tab = 'overview' | 'vehicles' | 'booking' | 'invoices' | 'shop';
const label = (value: string) => value.replaceAll('_', ' ');
const money = (value: number, currency: string) => new Intl.NumberFormat('en', {style: 'currency', currency}).format(value);
const today = () => {const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};

function Action({title, onPress, disabled = false, secondary = false}: {title: string; onPress: () => void; disabled?: boolean; secondary?: boolean}) {
  return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress}
    style={[s.action, secondary && s.secondary, disabled && s.disabled]}>
    <Text style={[s.actionText, secondary && s.secondaryText]}>{title}</Text>
  </Pressable>;
}

export default function CustomerWorkspace({user, jobs, vehicles, busy, call, run, refresh, openPhoto}: Props) {
  const [tab, setTab] = useState<Tab>('overview');
  const [selected, setSelected] = useState<number | null>(null);
  const [plate, setPlate] = useState(''), [model, setModel] = useState('');
  const [vehicleId, setVehicleId] = useState<number | null>(null);
  const [date, setDate] = useState(today()), [concern, setConcern] = useState('');
  const [notice, setNotice] = useState('');
  const scroll = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const job = jobs.find(item => item.id === selected);
  useEffect(() => {
    const frame = requestAnimationFrame(() => scroll.current?.scrollTo({y: 0, animated: false}));
    return () => cancelAnimationFrame(frame);
  }, [tab, selected]);
  useEffect(() => {
    if (!vehicles.some(vehicle => vehicle.id === vehicleId)) setVehicleId(vehicles[0]?.id || null);
  }, [vehicles, vehicleId]);
  function navigate(next: Tab) {setTab(next); setSelected(null); setNotice('');}
  const pending = jobs.reduce((total, item) => total + Number(item.state === 'awaiting_approval') + (item.pending_quotes?.length || 0), 0);

  async function addVehicle() {
    const registration = plate.trim().toUpperCase(), makeModel = model.trim();
    if (registration.length < 2 || makeModel.length < 2) throw new Error('Enter a registration number and vehicle make/model.');
    const result = await call<{id: number}>('vehicle', {plate: registration, make_model: makeModel});
    await refresh(); setVehicleId(result.id); setPlate(''); setModel(''); setNotice('Vehicle added. You can now book a service.');
  }
  async function bookService() {
    if (!vehicleId || !vehicles.some(vehicle => vehicle.id === vehicleId)) throw new Error('Choose one of your vehicles.');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date < today()) throw new Error('Enter today or a future date in YYYY-MM-DD format.');
    if (concern.trim().length < 10) throw new Error('Describe the issue using at least 10 characters.');
    const created = await call<Job>('request', {vehicle_id: vehicleId, appointment_date: date, concern: concern.trim()});
    await refresh(); setConcern(''); setSelected(created.id); setTab('overview'); setNotice('Service request sent. Your workshop will confirm the appointment.');
  }
  async function approve(item: Job, quote: Quote) {
    if (!await confirmAction('Approve quotation?', `Approve ${quote.name} for ${money(quote.total, quote.currency)} including tax?`)) return;
    await run(async () => {
      try {
        await call('approve', {job_id: item.id, order_id: quote.id, version: quote.version});
        await refresh(); setNotice('Quotation approved. Your workshop can proceed with the work.');
      } catch (error) {
        // Load the latest prices/version before a customer can retry stale approval.
        await refresh().catch(() => {});
        throw error;
      }
    });
  }
  async function download(item: Job, invoice: Invoice) {
    const file = await call<{name: string; content: string}>('invoice', {job_id: item.id, invoice_id: invoice.id});
    await saveInvoice(file.name, file.content); setNotice('Invoice ready to save.');
  }
  function quoteCard(item: Job, quote: Quote, additional = false) {
    const awaiting = additional || item.state === 'awaiting_approval';
    return <View key={quote.id} style={s.card}>
      <Text style={s.kicker}>{additional ? 'ADDITIONAL WORK' : 'SERVICE ESTIMATE'}</Text>
      <Text style={s.h2}>{quote.name}</Text>
      {quote.lines.map((line, index) => <View style={s.line} key={index}>
        <Text style={s.flexText}>{line.name} × {line.qty}</Text><Text style={s.amount}>{money(line.total, quote.currency)}</Text>
      </View>)}
      <View style={s.line}><Text style={s.flexText}>Total including tax</Text><Text style={s.total}>{money(quote.total, quote.currency)}</Text></View>
      {awaiting ? <Action title={additional ? 'Approve additional work' : 'Approve quotation'} disabled={busy} onPress={() => void approve(item, quote)}/>
        : <Text style={s.hint}>{['requested','cancelled'].includes(item.state) ? 'Your workshop will confirm when this estimate is ready for approval.' : 'Customer approval recorded.'}</Text>}
    </View>;
  }
  function invoiceCard(item: Job, invoice: Invoice) {
    return <View style={s.card} key={`${item.id}-${invoice.id}`}>
      <Text style={s.h2}>{invoice.name}</Text><Text style={s.text}>{item.model} · {item.vehicle}</Text>
      <View style={s.line}><Text style={s.flexText}>Invoice total</Text><Text style={s.total}>{money(invoice.total, invoice.currency)}</Text></View>
      <Text style={s.badge}>Payment: {label(invoice.payment_state)}</Text>
      <Action title={`Download invoice ${invoice.name}`} secondary disabled={busy} onPress={() => void run(() => download(item, invoice))}/>
    </View>;
  }

  return <View style={s.workspace}>
    <View style={s.tabs}>{([['overview','My services'],['vehicles','My vehicles'],['booking','Book a service'],['invoices','Invoices'],['shop','Parts shop']] as [Tab,string][]).map(([key,title]) =>
      <Pressable key={key} accessibilityRole="tab" accessibilityState={{selected: tab === key}} onPress={() => navigate(key)} style={[s.tab, tab === key && s.activeTab]}>
        <Text style={[s.tabText, tab === key && s.activeTabText]}>{title}</Text>
      </Pressable>)}</View>
    <ScrollView ref={scroll} contentContainerStyle={s.content} keyboardShouldPersistTaps="handled"
      refreshControl={<RefreshControl refreshing={busy} onRefresh={() => void run(refresh)} tintColor="#225641"/>}>
      {!!notice && <View accessibilityRole="alert" style={s.notice}><Text style={s.noticeText}>{notice}</Text></View>}
      {tab === 'shop' && <PartsShop call={call} run={run} busy={busy} user={user}/>}
      {tab === 'overview' && !job && <>
        <Text style={s.kicker}>YOUR VEHICLE. YOUR PEACE OF MIND.</Text>
        <Text style={s.title}>Hello, {user.name.split(' ')[0]}.</Text>
        <Text style={s.text}>Book a service, review estimates, and follow your repair.</Text>
        <View style={s.summary}>
          <View><Text style={s.number}>{vehicles.length}</Text><Text style={s.summaryLabel}>Vehicles</Text></View>
          <View><Text style={s.number}>{jobs.filter(item => !['completed','cancelled'].includes(item.state)).length}</Text><Text style={s.summaryLabel}>Active services</Text></View>
          <View><Text style={s.number}>{pending}</Text><Text style={s.summaryLabel}>To approve</Text></View>
        </View>
        <Action title="Book a service" onPress={() => navigate('booking')}/>
        <Text style={s.h2}>Your service history</Text>
        {!jobs.length && <View style={s.card}><Text style={s.text}>No services yet. Add your vehicle and request its first service.</Text></View>}
        {jobs.map(item => <Pressable key={item.id} accessibilityRole="button" accessibilityLabel={`Open service ${item.name}`} style={s.card} onPress={() => {setSelected(item.id); setNotice('');}}>
          <Text style={s.badge}>{label(item.state)}</Text><Text style={s.h2}>{item.model}</Text>
          <Text style={s.meta}>{item.vehicle} · {item.name}</Text><Text style={s.text}>{item.concern}</Text>
          {(item.state === 'awaiting_approval' || !!item.pending_quotes?.length) && <Text style={s.approval}>Your quotation is ready to review</Text>}
          <Text style={s.link}>View service →</Text>
        </Pressable>)}
      </>}
      {tab === 'overview' && job && <>
        <Action title="Back to my services" secondary onPress={() => setSelected(null)}/>
        <Text style={s.title}>{job.model}</Text><Text style={s.meta}>{job.vehicle} · {job.name}</Text>
        <View style={s.card}><Text style={s.badge}>{label(job.state)}</Text>
          <Text style={s.h2}>Repair progress</Text><Text style={s.text}>{job.concern}</Text>
          <Text style={s.meta}>Technician: {job.technician}</Text>{!!job.date && <Text style={s.meta}>Requested date: {job.date}</Text>}
          <Text style={s.text}>{job.checks.filter(check => check.done).length} of {job.checks.length} inspection checks completed</Text>
          {job.checks.map(check => <Text style={s.check} key={check.id}>{check.done ? '✓' : '○'} {check.name}</Text>)}
        </View>
        {job.quote && quoteCard(job, job.quote)}
        {(job.pending_quotes || []).map(quote => quoteCard(job, quote, true))}
        {!!job.parts.length && <View style={s.card}><Text style={s.h2}>Parts for your repair</Text>{job.parts.map(part =>
          <View key={part.id} style={s.line}><Text style={s.flexText}>{part.name} × {part.quantity}</Text><Text style={s.meta}>{label(part.state)}</Text></View>)}</View>}
        <View style={s.card}><Text style={s.h2}>Repair photos</Text>
          {!job.photos.length && <Text style={s.text}>Your technician's repair photos will appear here.</Text>}
          {job.photos.map(photo => <Action key={photo.id} title={`View photo: ${photo.name}`} secondary disabled={busy} onPress={() => void run(() => openPhoto(job.id, photo.id))}/>)}
        </View>
        <Text style={s.h2}>Invoices</Text>
        {!(job.invoices || []).length && <View style={s.card}><Text style={s.text}>Your invoice will appear once the workshop posts it.</Text></View>}
        {(job.invoices || []).map(invoice => invoiceCard(job, invoice))}
      </>}
      {tab === 'vehicles' && <>
        <Text style={s.title}>My vehicles</Text><Text style={s.text}>Keep your vehicles together for bookings and service history.</Text>
        {!vehicles.length && <Text style={s.text}>No vehicles registered yet.</Text>}
        {vehicles.map(vehicle => <View style={s.card} key={vehicle.id}><Text style={s.h2}>{vehicle.model}</Text><Text style={s.badge}>{vehicle.plate}</Text>
          <Action title={`Book service for ${vehicle.plate}`} secondary onPress={() => {setVehicleId(vehicle.id); navigate('booking');}}/>
        </View>)}
        <View style={s.card}><Text style={s.h2}>Add a vehicle</Text>
          <Text style={s.fieldLabel}>Registration number</Text><TextInput accessibilityLabel="Registration number" value={plate} onChangeText={setPlate} autoCapitalize="characters" maxLength={30} style={s.input}/>
          <Text style={s.fieldLabel}>Make and model</Text><TextInput accessibilityLabel="Make and model" value={model} onChangeText={setModel} maxLength={120} placeholder="e.g. Honda City 2024" style={s.input}/>
          <Action title="Save vehicle" disabled={busy || plate.trim().length < 2 || model.trim().length < 2} onPress={() => void run(addVehicle)}/>
        </View>
      </>}
      {tab === 'booking' && <>
        <Text style={s.title}>Book a service</Text><Text style={s.text}>Tell us what needs attention. Your workshop will review the request and confirm availability.</Text>
        <View style={s.card}><Text style={s.h2}>Choose your vehicle</Text>
          {!vehicles.length && <><Text style={s.text}>Add a vehicle before booking a service.</Text><Action title="Add my vehicle" onPress={() => navigate('vehicles')}/></>}
          {vehicles.map(vehicle => <Pressable key={vehicle.id} accessibilityRole="radio" accessibilityState={{checked: vehicle.id === vehicleId}} accessibilityLabel={`${vehicle.plate} ${vehicle.model}`}
            onPress={() => setVehicleId(vehicle.id)} style={[s.choice, vehicle.id === vehicleId && s.chosen]}>
            <Text style={s.choiceText}>{vehicle.id === vehicleId ? '●' : '○'} {vehicle.plate} — {vehicle.model}</Text>
          </Pressable>)}
          <Text style={s.fieldLabel}>Preferred date (YYYY-MM-DD)</Text>
          <TextInput accessibilityLabel="Preferred date" value={date} onChangeText={setDate} placeholder="YYYY-MM-DD" maxLength={10} autoCapitalize="none" style={s.input}/>
          <Text style={s.fieldLabel}>What needs attention?</Text>
          <TextInput accessibilityLabel="Service concern" value={concern} onChangeText={setConcern} multiline maxLength={4000} placeholder="Describe the issue or service you need…" style={[s.input, s.multiline]}/>
          <Action title="Send service request" disabled={busy || !vehicleId || concern.trim().length < 10} onPress={() => void run(bookService)}/>
          <Text style={s.hint}>This is an appointment request. Your workshop will confirm the date and provide an estimate before repair work.</Text>
        </View>
      </>}
      {tab === 'invoices' && <>
        <Text style={s.title}>My invoices</Text><Text style={s.text}>Review invoice totals and recorded payment status.</Text>
        {!jobs.some(item => item.invoices?.length) && <View style={s.card}><Text style={s.text}>No posted invoices yet. They will appear here after your workshop issues them.</Text></View>}
        {jobs.flatMap(item => (item.invoices || []).map(invoice => invoiceCard(item, invoice)))}
      </>}
      <Text style={s.footer}>WORKSHOP HUB · CARE YOU CAN FOLLOW</Text>
    </ScrollView>
  </View>;
}

const s = StyleSheet.create({
  workspace: {flex: 1}, content: {padding: 22, paddingBottom: 48, width: '100%', maxWidth: 760, alignSelf: 'center'},
  tabs: {flexDirection: 'row', flexWrap: 'wrap', gap: 6, padding: 12, backgroundColor: '#fff', borderBottomWidth: 1, borderColor: '#e0e7da'},
  tab: {paddingHorizontal: 12, paddingVertical: 12, borderRadius: 9}, activeTab: {backgroundColor: '#225641'},
  tabText: {fontSize: 12, fontWeight: '600', color: '#526253'}, activeTabText: {color: '#fff'},
  kicker: {fontSize: 9, letterSpacing: 2, color: '#547249', fontWeight: '700', marginTop: 10},
  title: {fontSize: 32, lineHeight: 39, fontWeight: '700', color: '#183b2c', marginTop: 14, marginBottom: 8},
  h2: {fontSize: 18, color: '#183b2c', fontWeight: '700', marginTop: 10, marginBottom: 12},
  text: {fontSize: 13, lineHeight: 22, color: '#607463', marginVertical: 7},
  meta: {fontSize: 11, lineHeight: 18, color: '#718075', marginVertical: 4},
  card: {padding: 20, backgroundColor: '#fff', borderRadius: 16, borderWidth: 1, borderColor: '#e0e7da', marginVertical: 9},
  summary: {flexDirection: 'row', justifyContent: 'space-between', gap: 10, padding: 20, backgroundColor: '#d6ef9a', borderRadius: 16, marginVertical: 18},
  number: {fontSize: 32, color: '#225641', fontWeight: '700'}, summaryLabel: {fontSize: 11, color: '#355337', marginTop: 5},
  action: {paddingHorizontal: 16, paddingVertical: 14, backgroundColor: '#225641', borderRadius: 10, alignItems: 'center', marginVertical: 6},
  actionText: {fontSize: 12, fontWeight: '700', color: '#fff'}, secondary: {backgroundColor: '#ebf2e4', borderWidth: 1, borderColor: '#d9e5d0'}, secondaryText: {color: '#225641'}, disabled: {opacity: 0.45},
  badge: {fontSize: 11, textTransform: 'capitalize', color: '#52704d', backgroundColor: '#ecf2e6', padding: 8, borderRadius: 9, alignSelf: 'flex-start'},
  link: {fontSize: 12, fontWeight: '700', color: '#225641', marginTop: 12}, approval: {fontSize: 12, color: '#8a5b15', fontWeight: '600', marginTop: 8},
  line: {flexDirection: 'row', gap: 14, justifyContent: 'space-between', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderColor: '#edf1e8'},
  flexText: {flex: 1, color: '#526253', fontSize: 12, lineHeight: 19}, amount: {fontSize: 12, color: '#183b2c'}, total: {fontSize: 17, fontWeight: '700', color: '#183b2c'},
  check: {fontSize: 12, color: '#526253', paddingVertical: 11, lineHeight: 19},
  fieldLabel: {fontSize: 12, color: '#526253', marginTop: 16, marginBottom: 8, fontWeight: '600'},
  input: {fontSize: 14, borderWidth: 1, borderColor: '#dce5d7', borderRadius: 9, padding: 13, backgroundColor: '#fafcf7', color: '#183b2c', marginBottom: 8}, multiline: {minHeight: 110, textAlignVertical: 'top'},
  hint: {fontSize: 11, lineHeight: 18, color: '#718075', marginTop: 9},
  choice: {padding: 14, borderWidth: 1, borderColor: '#e0e7da', borderRadius: 9, marginVertical: 4}, chosen: {backgroundColor: '#eaf2df', borderColor: '#809976'}, choiceText: {fontSize: 13, lineHeight: 20, color: '#225641'},
  notice: {padding: 14, backgroundColor: '#e5f2da', borderRadius: 10}, noticeText: {fontSize: 12, color: '#225641', lineHeight: 19},
  footer: {fontSize: 9, letterSpacing: 1, color: '#718075', marginTop: 26, textAlign: 'center'},
});
