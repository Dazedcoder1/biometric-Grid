// src/pages/org/ReportLeave.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import { orgApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { Download, Calendar, RefreshCw, AlertCircle, FileText, Briefcase } from 'lucide-react';

const ReportLeave = () => {
  const { logout } = useAuth();
  const today = new Date().toISOString().split("T")[0];
  const [fromDate, setFromDate] = useState(today);
  const [toDate, setToDate] = useState(today);
  const [stats, setStats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [generated, setGenerated] = useState(false);

  const generateReport = async () => {
    setLoading(true);
    setError("");
    setGenerated(false);
    try {
      const employees = await orgApi.getEmployees();
      const leaves = await orgApi.getLeaveRequests();

      const reportMap = {};
      employees.forEach(emp => { reportMap[emp.name] = { name: emp.name, employee_code: emp.employee_code, sick: 0, casual: 0, earned: 0, total: 0, pending: 0, approved: 0, rejected: 0 }; });

      leaves.forEach(l => {
        const leaveStart = l.start_date?.split("T")[0];
        const leaveEnd = l.end_date?.split("T")[0];
        const overlaps = leaveStart <= toDate && leaveEnd >= fromDate;
        if (!overlaps) return;

        const empName = l.employee_name;
        if (!reportMap[empName]) reportMap[empName] = { name: empName, employee_code: '', sick: 0, casual: 0, earned: 0, total: 0, pending: 0, approved: 0, rejected: 0 };

        const days = 1;
        const leaveType = l.leave_type?.toLowerCase();
        if (leaveType === "sick") reportMap[empName].sick += days;
        else if (leaveType === "casual") reportMap[empName].casual += days;
        else if (leaveType === "earned") reportMap[empName].earned += days;
        
        reportMap[empName].total += days;
        if (l.status === "pending") reportMap[empName].pending += days;
        else if (l.status === "approved" || l.status === "approved_by_dept") reportMap[empName].approved += days;
        else if (l.status === "rejected") reportMap[empName].rejected += days;
      });

      const result = Object.values(reportMap).map(r => ({ ...r, status: r.total === 0 ? "No leaves" : r.pending > 0 ? `${r.pending} pending` : "approved" }));
      setStats(result);
      setGenerated(true);
    } catch (err) {
      if (err?.response?.status === 401) logout();
      setError("Failed to generate report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { generateReport(); }, []);

  const downloadCSV = () => {
    let csv = "Employee Code,Employee Name,Sick,Casual,Earned,Total,Status\n";
    stats.forEach(s => { csv += `${s.employee_code || ''},${s.name},${s.sick},${s.casual},${s.earned},${s.total},${s.status}\n`; });
    const blob = new Blob([csv], { type: "text/csv" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `leave_report_${fromDate}_to_${toDate}.csv`;
    link.click();
  };

  const totalLeaves = stats.reduce((sum, s) => sum + s.total, 0);
  const totalPending = stats.reduce((sum, s) => sum + s.pending, 0);

  return (
    <DashboardLayout title="Leave Report" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      <div className="stats-grid">
        <div className="stat-card purple"><div className="stat-label"><Briefcase size={14} /> Total Leave Days</div><div className="stat-value">{totalLeaves}</div><div className="stat-sub">Across all employees</div></div>
        <div className="stat-card amber"><div className="stat-label">Pending Requests</div><div className="stat-value">{totalPending}</div><div className="stat-sub">Awaiting approval</div></div>
        <div className="stat-card teal"><div className="stat-label">Employees</div><div className="stat-value">{stats.length}</div><div className="stat-sub">With leave records</div></div>
      </div>

      <div className="card-box" style={{ marginBottom: '1.5rem' }}>
        <h4 style={{ marginBottom: '0.5rem' }}>Generate Leave Report</h4>
        <p style={{ color: 'var(--text3)', fontSize: '0.8rem', marginBottom: '1.5rem' }}>Select a date range to generate leave summary</p>
        {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '10px', padding: '12px', marginBottom: '1rem', color: '#f87171' }}><AlertCircle size={16} /> {error}</div>}
        <div className="form-grid" style={{ marginBottom: '1rem' }}>
          <div className="form-group"><label className="form-label"><Calendar size={14} /> From Date</label><input className="form-input" type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} /></div>
          <div className="form-group"><label className="form-label"><Calendar size={14} /> To Date</label><input className="form-input" type="date" value={toDate} onChange={e => setToDate(e.target.value)} /></div>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button className="btn btn-teal" onClick={generateReport} disabled={loading}><RefreshCw size={16} /> {loading ? 'Generating...' : 'Generate Report'}</button>
          <button className="btn btn-ghost" onClick={downloadCSV} disabled={!generated || stats.length === 0}><Download size={16} /> Download CSV</button>
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-header"><span className="table-title"><FileText size={16} /> Leave Statistics {generated && `(${fromDate} to ${toDate})`}</span></div>
        {loading ? (<div style={{ textAlign: 'center', padding: '3rem' }}>Loading report data...</div>) : !generated ? (<div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>Click "Generate Report" to view leave summary</div>) : stats.length === 0 ? (<div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>No data found for selected date range</div>) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', minWidth: '700px' }}>
              <thead>
                <tr><th>Employee</th><th>Code</th><th>Sick</th><th>Casual</th><th>Earned</th><th>Total</th><th>Status</th></tr>
              </thead>
              <tbody>
                {stats.map((s, i) => (
                  <tr key={i}>
                    <td>{s.name}</td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>{s.employee_code || '—'}</td>
                    <td>{s.sick}</td>
                    <td>{s.casual}</td>
                    <td>{s.earned}</td>
                    <td style={{ fontWeight: 600 }}>{s.total}</td>
                    <td><Badge type={s.status.includes("pending") ? "pending" : s.status === "No leaves" ? "inactive" : "approved"}>{s.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default ReportLeave;