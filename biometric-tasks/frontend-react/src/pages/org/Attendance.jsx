// src/pages/org/Attendance.jsx
import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import { orgApi, tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { Search, RefreshCw, AlertCircle, Calendar, User, Clock, CheckCircle, XCircle } from 'lucide-react';

const Attendance = () => {
  const { logout, user } = useAuth();
  const todayDate = new Date().toISOString().split('T')[0];
  const [attendance, setAttendance] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedDate, setSelectedDate] = useState(todayDate);
  const [error, setError] = useState("");
  const [settings, setSettings] = useState(null);
  const [stats, setStats] = useState({ present: 0, absent: 0, met_min_hours: 0 });

  const fetchAttendance = async (date) => {
    setLoading(true);
    setError("");
    try {
      const data = await orgApi.getAttendanceByDate(date);
      console.log("Org Attendance data:", data);
      
      if (data && data.employees) {
        setAttendance(data.employees || []);
        setStats({
          present: data.summary?.present || 0,
          absent: data.summary?.absent || 0,
          met_min_hours: data.summary?.met_minimum_hours || 0,
          attendance_rate: data.summary?.attendance_rate || 0,
          compliance_rate: data.summary?.compliance_rate || 0
        });
      } else if (Array.isArray(data)) {
        // Handle old format
        setAttendance(data);
        const present = data.filter(a => a.status === 'present').length;
        const metMin = data.filter(a => a.met_min_hours).length;
        setStats({ present, absent: data.length - present, met_min_hours: metMin });
      }
    } catch (err) {
      if (err?.response?.status === 401) logout();
      setError("Failed to load attendance");
    } finally {
      setLoading(false);
    }
  };

  const fetchSettings = async () => {
    try {
      // Fetch tenant settings using public endpoint or org API
      const data = await tenantApi.getSettings();
      setSettings(data);
    } catch (err) {
      console.error("Fetch settings error:", err);
    }
  };

  useEffect(() => {
    fetchAttendance(selectedDate);
    fetchSettings();
  }, [selectedDate]);

  const formatTime = (timestamp) => {
    if (!timestamp) return "--";
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return "--";
    }
  };

  const filteredData = attendance.filter(a => 
    a.name?.toLowerCase().includes(search.toLowerCase()) ||
    a.employee_code?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <DashboardLayout title="Attendance" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
        <div className="skeleton-loader">Loading...</div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Attendance" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      <style>{`
        .stat-card { transition: all 0.2s; }
        .stat-card:hover { transform: translateY(-2px); }
      `}</style>

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card green">
          <div className="stat-label"><User size={14} /> Present</div>
          <div className="stat-value">{stats.present}</div>
          <div className="stat-sub">{stats.attendance_rate}% rate</div>
        </div>
        <div className="stat-card red">
          <div className="stat-label"><XCircle size={14} /> Absent</div>
          <div className="stat-value">{stats.absent}</div>
        </div>
        <div className="stat-card purple">
          <div className="stat-label"><CheckCircle size={14} /> Met Min Hours</div>
          <div className="stat-value">{stats.met_min_hours}</div>
          <div className="stat-sub">{stats.compliance_rate}% compliance</div>
        </div>
      </div>

      {/* Filters */}
      <div className="table-wrap">
        <div className="table-header">
          <span className="table-title">Attendance for {new Date(selectedDate).toLocaleDateString()}</span>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <div className="input-wrap" style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }} />
              <input className="form-input" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ paddingLeft: '32px', width: '180px' }} />
            </div>
            <div className="input-wrap" style={{ position: 'relative' }}>
              <Calendar size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }} />
              <input type="date" className="form-input" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)} style={{ paddingLeft: '32px', width: '150px' }} />
            </div>
            <button className="btn btn-ghost" onClick={() => fetchAttendance(selectedDate)}><RefreshCw size={14} /> Refresh</button>
          </div>
        </div>

        {error && <div style={{ color: '#f87171', padding: '1rem', textAlign: 'center' }}><AlertCircle size={16} /> {error}</div>}

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', minWidth: '650px' }}>
            <thead>
              <tr>
                <th>Employee</th>
                <th>Code</th>
                <th>Check In</th>
                <th>Check Out</th>
                <th>Hours</th>
                <th>Met Min Hours?</th>
              </tr>
            </thead>
            <tbody>
              {filteredData.length === 0 ? (
                <tr><td colSpan="6" style={{ textAlign: 'center', padding: '3rem' }}>No records found</td></tr>
              ) : (
                filteredData.map((a, idx) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 500 }}>{a.name}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{a.employee_code || '—'}</td>
                    <td style={{ fontFamily: 'monospace' }}>
                      {formatTime(a.check_in)}
                      {a.is_late && <span style={{ color: '#f59e0b', marginLeft: '6px', fontSize: '0.7rem' }}>(late)</span>}
                    </td>
                    <td style={{ fontFamily: 'monospace' }}>{formatTime(a.check_out)}</td>
                    <td style={{ fontFamily: 'monospace', fontWeight: a.met_min_hours ? 600 : 400 }}>
                      <span style={{ color: a.met_min_hours ? '#22c55e' : (a.check_in ? '#f59e0b' : '#6b7585') }}>
                        {a.hours_worked || 0}h
                      </span>
                    </td>
                    <td>
                      {a.check_in ? (
                        a.met_min_hours ? (
                          <Badge type="present">✓ Yes</Badge>
                        ) : (
                          <Badge type="late">✗ No</Badge>
                        )
                      ) : <span style={{ fontSize: '0.7rem', color: '#6b7585' }}>—</span>}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Settings Banner */}
      {settings && (
        <div style={{ marginTop: '1rem', padding: '0.5rem 1rem', background: 'rgba(0,212,170,0.05)', borderRadius: '8px', fontSize: '0.7rem', textAlign: 'center' }}>
          Office Hours: {settings.office_start_time?.slice(0,5)} - {settings.office_end_time?.slice(0,5)} | 
          Min Required: {settings.min_working_hours}h
        </div>
      )}
    </DashboardLayout>
  );
};

export default Attendance;