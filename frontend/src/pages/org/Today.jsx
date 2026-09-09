import React, { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, Plus, UserCheck, UserX, Clock, Calendar as CalendarIcon, AlertCircle, RefreshCw } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import { orgApi, tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const Today = () => {
  const { logout } = useAuth();
  const [attendanceData, setAttendanceData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [settings, setSettings] = useState(null);

  const fetchSettings = async () => {
    try {
      const data = await tenantApi.getSettings();
      setSettings(data);
    } catch (err) {
      console.error("Failed to fetch settings:", err);
    }
  };

  const fetchTodayAttendance = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await orgApi.getTodayAttendance();
      console.log("Today attendance:", data);
      
      // Handle both array and object response formats
      if (data && data.employees && Array.isArray(data.employees)) {
        setAttendanceData(data);
      } else if (Array.isArray(data)) {
        // Fallback for old API format
        setAttendanceData({
          summary: {
            total_employees: data.length,
            present: data.filter(a => a.status === "present").length,
            absent: data.filter(a => a.status === "absent").length,
            late: data.filter(a => a.is_late).length,
            attendance_rate: (data.filter(a => a.status === "present").length / data.length) * 100,
            compliance_rate: 0,
            total_valid_hours: 0,
            average_hours: 0
          },
          employees: data
        });
      } else {
        setAttendanceData(null);
        setError("Invalid data format received");
      }
    } catch (err) {
      if (err?.response?.status === 401) logout();
      setError("Failed to load attendance");
      console.error("Error fetching attendance:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
    fetchTodayAttendance();
  }, []);

  const formatTime = (timestamp) => {
    if (!timestamp) return "--";
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatDate = (timestamp) => {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const getStatusBadge = (status, isLate) => {
    if (status === "absent") {
      return <Badge type="absent">Absent</Badge>;
    }
    if (isLate) {
      return <Badge type="late">Late</Badge>;
    }
    return <Badge type="present">Present</Badge>;
  };

  if (loading) {
    return (
      <DashboardLayout title="Today's Attendance" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
        <div className="loading-container" style={{ textAlign: 'center', padding: '3rem' }}>
          <div className="spinner"></div>
          <p>Loading attendance data...</p>
        </div>
      </DashboardLayout>
    );
  }

  const summary = attendanceData?.summary || {
    total_employees: 0,
    present: 0,
    absent: 0,
    late: 0,
    attendance_rate: 0,
    compliance_rate: 0,
    total_valid_hours: 0,
    average_hours: 0
  };

  const employees = attendanceData?.employees || [];

  return (
    <DashboardLayout title="Today's Attendance" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card green">
          <div className="stat-label"><UserCheck size={14} /> Present</div>
          <div className="stat-value">{summary.present || 0}</div>
          <div className="stat-sub">{((summary.present / summary.total_employees) * 100 || 0).toFixed(1)}%</div>
        </div>
        <div className="stat-card amber">
          <div className="stat-label"><Clock size={14} /> Late</div>
          <div className="stat-value">{summary.late || 0}</div>
        </div>
        <div className="stat-card red">
          <div className="stat-label"><UserX size={14} /> Absent</div>
          <div className="stat-value">{summary.absent || 0}</div>
        </div>
        <div className="stat-card purple">
          <div className="stat-label">Attendance Rate</div>
          <div className="stat-value">{summary.attendance_rate || 0}%</div>
        </div>
      </div>

      {/* Main Table */}
      <div className="table-wrap">
        <div className="table-header">
          <span className="table-title">
            Today's Attendance - {formatDate(attendanceData?.date || new Date().toISOString())}
          </span>
          <button className="btn btn-ghost" onClick={fetchTodayAttendance}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
        
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', minWidth: '700px' }}>
            <thead>
              <tr>
                <th>Employee</th>
                <th>Employee Code</th>
                <th>Check In</th>
                <th>Check Out</th>
                <th>Hours Worked</th>
                <th>Status</th>
                <th>Remarks</th>
              </tr>
            </thead>
            <tbody>
              {employees.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '3rem', color: '#6b7585' }}>
                    No attendance records for today
                  </td>
                </tr>
              ) : (
                employees.map((emp, idx) => (
                  <tr key={emp.id || idx}>
                    <td style={{ fontWeight: 500 }}>
                      {emp.name}
                      {emp.employee_code && <span style={{ fontSize: '0.7rem', color: '#6b7585', display: 'block' }}>{emp.employee_code}</span>}
                    </td>
                    <td style={{ fontSize: '0.85rem' }}>{emp.employee_code || '—'}</td>
                    <td>
                      {formatTime(emp.check_in)}
                      {emp.is_late && emp.late_message && (
                        <span style={{ color: '#f59e0b', marginLeft: '6px', fontSize: '0.7rem', display: 'block' }}>
                          {emp.late_message}
                        </span>
                      )}
                    </td>
                    <td>{formatTime(emp.check_out)}</td>
                    <td style={{ fontWeight: emp.met_min_hours ? 600 : 400 }}>
                      {emp.hours_worked ? `${emp.hours_worked.toFixed(1)}h` : '—'}
                    </td>
                    <td>
                      {getStatusBadge(emp.status, emp.is_late)}
                    </td>
                    <td style={{ fontSize: '0.8rem', color: '#6b7585', maxWidth: '200px' }}>
                      {emp.status_message || (emp.is_late ? emp.late_message : '—')}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Compliance Summary */}
      {employees.length > 0 && (
        <div style={{ 
          marginTop: '1rem', 
          padding: '1rem', 
          background: 'rgba(0,212,170,0.05)', 
          borderRadius: '8px',
          borderLeft: '3px solid #00d4aa'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <strong>Compliance Summary</strong>
              <div style={{ fontSize: '0.8rem', color: '#6b7585', marginTop: '4px' }}>
                {summary.met_minimum_hours || 0} out of {summary.total_employees} employees met minimum hours
              </div>
            </div>
            <div style={{ fontSize: '0.8rem' }}>
              <span>Total Valid Hours: {summary.total_valid_hours?.toFixed(1) || 0}h</span>
              <span style={{ marginLeft: '1rem' }}>Avg Hours: {summary.average_hours?.toFixed(1) || 0}h</span>
            </div>
          </div>
        </div>
      )}

      {/* Settings Info */}
      {settings && (
        <div style={{ 
          marginTop: '1rem', 
          padding: '0.5rem 1rem', 
          background: 'rgba(0,212,170,0.05)', 
          borderRadius: '8px', 
          fontSize: '0.7rem', 
          textAlign: 'center',
          color: '#6b7585'
        }}>
          ⏱️ Min working hours required: {settings.min_working_hours}h 
          (within {settings.office_start_time?.slice(0,5)} - {settings.office_end_time?.slice(0,5)})
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div style={{ 
          marginTop: '1rem', 
          padding: '0.75rem', 
          background: 'rgba(239,68,68,0.1)', 
          borderRadius: '8px', 
          fontSize: '0.8rem', 
          textAlign: 'center',
          color: '#ef4444'
        }}>
          <AlertCircle size={14} style={{ display: 'inline', marginRight: '6px' }} />
          {error}
        </div>
      )}
    </DashboardLayout>
  );
};

export default Today;