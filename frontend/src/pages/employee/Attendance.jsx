// src/pages/employee/Attendance.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import { employeeApi, tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const Attendance = () => {
  const { logout } = useAuth();
  const [attendanceList, setAttendanceList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [settings, setSettings] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());

  useEffect(() => {
    fetchAttendanceData();
    fetchSettings();
  }, [selectedMonth, selectedYear]);

  const fetchSettings = async () => {
    try {
      const data = await tenantApi.getSettings();
      setSettings(data);
    } catch (err) {
      console.error("Fetch settings error:", err);
    }
  };

  const fetchAttendanceData = async () => {
    setLoading(true);
    setError(null);
    try {
      const history = await employeeApi.getAttendanceHistory();
      
      const filteredHistory = history.filter(record => {
        if (!record.date) return false;
        const recordDate = new Date(record.date);
        return recordDate.getMonth() + 1 === selectedMonth && 
               recordDate.getFullYear() === selectedYear;
      });
      
      setAttendanceList(filteredHistory);
    } catch (err) {
      console.error('Failed to fetch attendance:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '--';
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
  };

  const formatTime = (timeStr) => {
    if (!timeStr) return '--';
    return new Date(timeStr).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  const getMonthOptions = () => {
    const options = [];
    const currentDate = new Date();
    for (let i = 0; i < 12; i++) {
      const date = new Date(currentDate.getFullYear(), currentDate.getMonth() - i, 1);
      options.push({
        value: `${date.getMonth() + 1}-${date.getFullYear()}`,
        month: date.getMonth() + 1,
        year: date.getFullYear(),
        label: date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
      });
    }
    return options;
  };

  const handleMonthChange = (e) => {
    const [month, year] = e.target.value.split('-');
    setSelectedMonth(parseInt(month));
    setSelectedYear(parseInt(year));
  };

  const monthOptions = getMonthOptions();
  const currentSelection = `${selectedMonth}-${selectedYear}`;

  if (loading) {
    return (
      <DashboardLayout title="My Attendance" role="user" label="Employee" abbr="EM" color="#f59e0b" bgColor="rgba(245,158,11,0.15)">
        <div className="card-box" style={{ textAlign: 'center', padding: '4rem' }}>Loading...</div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="My Attendance" role="user" label="Employee" abbr="EM" color="#f59e0b" bgColor="rgba(245,158,11,0.15)">
      <div className="table-wrap">
        <div className="table-header">
          <span className="table-title">My Attendance History</span>
          <select className="form-select" style={{ width: '180px' }} value={currentSelection} onChange={handleMonthChange}>
            {monthOptions.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
        
        {attendanceList.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>
            No attendance records found
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', minWidth: '600px' }}>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Check In</th>
                  <th>Check Out</th>
                  <th>Hours Worked</th>
                  <th>Met Min Hours?</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {attendanceList.map((a, idx) => (
                  <tr key={idx}>
                    <td style={{ fontFamily: 'monospace' }}>{formatDate(a.date)}</td>
                    <td style={{ fontFamily: 'monospace' }}>
                      {formatTime(a.check_in)}
                      {a.is_late && <span style={{ color: '#f59e0b', marginLeft: '6px', fontSize: '0.7rem' }}>(late)</span>}
                    </td>
                    <td style={{ fontFamily: 'monospace' }}>{formatTime(a.check_out)}</td>
                    <td style={{ fontFamily: 'monospace', fontWeight: a.met_min_hours ? 600 : 400 }}>
                      <span style={{ color: a.met_min_hours ? '#22c55e' : '#f59e0b' }}>
                        {a.hours_worked || 0}h
                      </span>
                    </td>
                    <td>
                      {a.met_min_hours ? (
                        <Badge type="present">✓ Yes</Badge>
                      ) : a.check_in ? (
                        <Badge type="late">✗ No</Badge>
                      ) : (
                        <span style={{ fontSize: '0.7rem', color: '#6b7585' }}>—</span>
                      )}
                    </td>
                    <td><Badge type={a.status === 'present' ? (a.is_late ? 'late' : 'present') : 'absent'}>{a.status === 'present' ? (a.is_late ? 'Late' : 'Present') : 'Absent'}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {settings && (
        <div style={{ marginTop: '1rem', padding: '0.5rem 1rem', background: 'rgba(245,158,11,0.05)', borderRadius: '8px', fontSize: '0.7rem', textAlign: 'center' }}>
          ⏱️ Minimum working hours required: {settings.min_working_hours}h (within office hours)
        </div>
      )}
    </DashboardLayout>
  );
};

export default Attendance;