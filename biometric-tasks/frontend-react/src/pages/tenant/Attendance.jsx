// src/pages/tenant/Attendance.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { 
  Search, RefreshCw, AlertCircle, Calendar as CalendarIcon, 
  Download, FileText, Users, Clock, Briefcase, CheckCircle, XCircle
} from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const Attendance = () => {
  const { logout } = useAuth();
  const [attendance, setAttendance] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [selectedDept, setSelectedDept] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [settings, setSettings] = useState(null);
  const [stats, setStats] = useState({
    total_employees: 0,
    present: 0,
    absent: 0,
    late_checkins: 0,
    met_minimum_hours: 0,
    attendance_rate: 0,
    compliance_rate: 0
  });

  const fetchAttendance = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await tenantApi.getAttendanceByDate(selectedDate, selectedDept || undefined);
      console.log('Attendance data:', data);
      
      if (data && data.employees) {
        setAttendance(data.employees || []);
        setStats({
          total_employees: data.summary?.total_employees || 0,
          present: data.summary?.present || 0,
          absent: data.summary?.absent || 0,
          late_checkins: data.summary?.late_checkins || 0,
          met_minimum_hours: data.summary?.met_minimum_hours || 0,
          attendance_rate: data.summary?.attendance_rate || 0,
          compliance_rate: data.summary?.compliance_rate || 0
        });
      }
    } catch (err) {
      console.error('Fetch attendance error:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load attendance');
    } finally {
      setLoading(false);
    }
  }, [selectedDate, selectedDept, logout]);

  const fetchDepartments = async () => {
    try {
      const data = await tenantApi.getDepartments();
      setDepartments(data || []);
    } catch (err) {
      console.error('Fetch departments error:', err);
    }
  };

  const fetchSettings = async () => {
    try {
      const data = await tenantApi.getSettings();
      setSettings(data);
    } catch (err) {
      console.error('Fetch settings error:', err);
    }
  };

  useEffect(() => {
    fetchAttendance();
    fetchDepartments();
    fetchSettings();
  }, [fetchAttendance]);

  const formatTime = (timestamp) => {
    if (!timestamp) return '--';
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '--';
    }
  };

  const filteredAttendance = attendance.filter(record => {
    const searchLower = searchTerm.toLowerCase();
    return (
      (record.name || '').toLowerCase().includes(searchLower) ||
      (record.employee_code || '').toLowerCase().includes(searchLower)
    );
  });

  if (loading) {
    return (
      <DashboardLayout 
        title="Attendance Management" 
        role="superadmin" 
        label="Tenant Admin" 
        abbr="TA" 
        color="#a855f7" 
        bgColor="rgba(168,85,247,0.15)"
      >
        <div className="skeleton-loader">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} style={{ background: 'var(--bg2)', borderRadius: '16px', height: '120px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>
            ))}
          </div>
          <div style={{ background: 'var(--bg2)', borderRadius: '16px', height: '400px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>
        </div>
        <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }`}</style>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="Attendance Management" 
      role="superadmin" 
      label="Tenant Admin" 
      abbr="TA" 
      color="#a855f7" 
      bgColor="rgba(168,85,247,0.15)"
    >
      <style>{`
        .stat-card { transition: all 0.2s; }
        .stat-card:hover { transform: translateY(-2px); }
      `}</style>

      {/* Stats Cards */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
        <div className="stat-card green">
          <div className="stat-label"><Users size={14} /> Present</div>
          <div className="stat-value">{stats.present}</div>
          <div className="stat-sub">{stats.attendance_rate}% rate</div>
        </div>
        <div className="stat-card red">
          <div className="stat-label"><XCircle size={14} /> Absent</div>
          <div className="stat-value">{stats.absent}</div>
        </div>
        <div className="stat-card amber">
          <div className="stat-label"><Clock size={14} /> Late Check-in</div>
          <div className="stat-value">{stats.late_checkins}</div>
        </div>
        <div className="stat-card purple">
          <div className="stat-label"><Briefcase size={14} /> Met Min Hours</div>
          <div className="stat-value">{stats.met_minimum_hours}</div>
          <div className="stat-sub">{stats.compliance_rate}% compliance</div>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <div className="input-wrap" style={{ position: 'relative' }}>
            <CalendarIcon size={16} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)' }} />
            <input 
              type="date" 
              className="form-input" 
              style={{ paddingLeft: '32px', width: '180px' }}
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
            />
          </div>
          <select 
            className="form-select" 
            style={{ width: '160px' }}
            value={selectedDept}
            onChange={(e) => setSelectedDept(e.target.value)}
          >
            <option value="">All Departments</option>
            {departments.filter(d => d.is_active).map(dept => (
              <option key={dept.department_id} value={dept.department_id}>
                {dept.department_name}
              </option>
            ))}
          </select>
          <div className="input-wrap" style={{ position: 'relative', width: '200px' }}>
            <Search size={16} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)' }} />
            <input 
              type="text" 
              className="form-input" 
              placeholder="Search employee..." 
              style={{ paddingLeft: '32px' }}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <button className="btn btn-ghost" onClick={fetchAttendance}>
            <RefreshCw size={16} style={{ marginRight: '4px' }} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '8px', padding: '12px', marginBottom: '1rem', color: '#f87171' }}>
          <AlertCircle size={16} style={{ marginRight: '8px' }} /> {error}
        </div>
      )}

      {/* Settings Banner */}
      {settings && (
        <div style={{ 
          background: 'rgba(168,85,247,0.05)', 
          border: '1px solid rgba(168,85,247,0.15)',
          borderRadius: '10px',
          padding: '8px 16px',
          marginBottom: '1rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.5rem',
          fontSize: '0.75rem'
        }}>
          <span>🕘 Office Hours: {settings.office_start_time?.slice(0,5)} - {settings.office_end_time?.slice(0,5)}</span>
          <span>⚠️ Late after: +{settings.late_threshold_minutes} min</span>
          <span>⏱️ Min hours required: {settings.min_working_hours}h</span>
        </div>
      )}

      {/* Attendance Table */}
      <div className="table-wrap">
        <div className="table-header">
          <span className="table-title">
            Attendance for {new Date(selectedDate).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          </span>
        </div>
        
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', minWidth: '700px' }}>
            <thead>
              <tr>
                <th>Employee</th>
                <th>Code</th>
                <th>Department</th>
                <th>Check In</th>
                <th>Check Out</th>
                <th>Hours Worked</th>
                <th>Met Min Hours?</th>
              </tr>
              </thead>
            <tbody>
              {filteredAttendance.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>
                    {searchTerm ? 'No matching employees found' : 'No attendance records found'}
                  </td>
                </tr>
              ) : (
                filteredAttendance.map((record, idx) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 500 }}>{record.name}</td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>{record.employee_code || '—'}</td>
                    <td>{record.department_name || '—'}</td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>
                      {formatTime(record.check_in)}
                      {record.is_late && <span style={{ color: 'var(--amber)', marginLeft: '6px', fontSize: '0.7rem' }}>(late)</span>}
                    </td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>{formatTime(record.check_out)}</td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem', fontWeight: record.met_min_hours ? 600 : 400 }}>
                      <span style={{ color: record.met_min_hours ? 'var(--green)' : (record.check_in ? 'var(--amber)' : 'var(--text3)') }}>
                        {record.hours_worked || 0}h
                      </span>
                      {record.lost_hours > 0.1 && (
                        <span style={{ fontSize: '0.65rem', color: 'var(--text3)', display: 'block' }}>
                          ({record.lost_hours}h outside office hours)
                        </span>
                      )}
                    </td>
                    <td>
                      {record.check_in ? (
                        record.met_min_hours ? (
                          <Badge type="present">
                            <CheckCircle size={10} style={{ display: 'inline', marginRight: '4px' }} />
                            Yes
                          </Badge>
                        ) : (
                          <Badge type="late">
                            <AlertCircle size={10} style={{ display: 'inline', marginRight: '4px' }} />
                            No
                          </Badge>
                        )
                      ) : (
                        <span style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer Summary */}
      {attendance.length > 0 && (
        <div style={{ 
          marginTop: '1rem', 
          padding: '0.75rem 1rem', 
          background: 'var(--bg2)', 
          borderRadius: '10px',
          border: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.5rem',
          fontSize: '0.75rem'
        }}>
          <div>📊 Total: {attendance.length} employees</div>
          <div>✅ Present: {stats.present}</div>
          <div>❌ Absent: {stats.absent}</div>
          <div>💪 Met min hours: {stats.met_minimum_hours}</div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>
            Min required: {settings?.min_working_hours || 9}h within office hours
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default Attendance;