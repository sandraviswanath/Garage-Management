import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata = {title:'Workshop Hub | Customer Portal',description:'Your vehicle service, from booking to handover.'};
export default function Layout({children}:{children:React.ReactNode}) {return <html lang="en"><body>{children}</body></html>;}
