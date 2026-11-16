import {notFound} from 'next/navigation';
import StaffApp from '../../../../components/staff/StaffApp';
import '../../../../components/staff/staff.css';
export default async function Page({params}:{params:Promise<{role:string;segments?:string[]}>}){
 const {role}=await params;if(!['admin','manager','receptionist','accountant','technician'].includes(role))notFound();return <StaffApp role={role}/>;
}
