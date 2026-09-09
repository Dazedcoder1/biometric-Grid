// src/pages/tenant/Employees.jsx
import React, { useState, useEffect } from 'react';
import { Search, RefreshCw, AlertCircle, Eye, User, Mail, Fingerprint, Building2, Calendar, Clock } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const Employees = () => {
  const { logout } = useAuth();
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDept, setSelectedDept] = useState('');
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [attendanceHistory, setAttendanceHistory] = useState([]);

  useEffect(() => {
    fetchData();
  }, [selectedDept]);

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const [employeesData, deptsData] = await Promise.all([
        tenantApi.getAllEmployees(selectedDept || undefined),
        tenantApi.getDepartments(),
      ]);
      setEmployees(employeesData || []);
      setDepartments(deptsData || []);
    } catch (err) {
      console.error('Fetch error:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load employees');
    } finally {
      setLoading(false);
    }
  };

  const fetchEmployeeDetails = async (employeeId) => {
    try {
      const [details, attendance] = await Promise.all([
        tenantApi.getEmployeeDetail(employeeId),
        tenantApi.getEmployeeAttendance(employeeId),
      ]);
      setSelectedEmployee(details);
      setAttendanceHistory(attendance || []);
      setShowDetailModal(true);
    } catch (err) {
      console.error('Fetch employee details error:', err);
      setError('Failed to load employee details');
    }
  };

  const filteredEmployees = employees.filter(emp =>
    emp.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    emp.employee_code?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    emp.email?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const stats = {
    total: employees.length,
    active: employees.filter(e => e.is_active).length,
    enrolled: employees.filter(e => e.finger_id).length,
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '--';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
  };

  const formatTime = (timeStr) => {
    if (!timeStr) return '--';
    const date = new Date(timeStr);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="Employees" 
        role="superadmin" 
        label="Tenant Admin" 
        abbr="TA" 
        color="#a855f7" 
        bgColor="rgba(168,85,247,0.15)"
      >
        <div className="skeleton-loader" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
          {[1,2,3,4,5,6].map(i => <div key={i} style={{ background: 'var(--bg2)', borderRadius: '12px', height: '180px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>)}
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="Employee Management" 
      role="superadmin" 
      label="Tenant Admin" 
      abbr="TA" 
      color="#a855f7" 
      bgColor="rgba(168,85,247,0.15)"
    >
      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0,0,0,0.7);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 2000;
          backdrop-filter: blur(4px);
        }
        .modal-content {
          background: var(--bg2);
          border: 1px solid var(--border);
          border-radius: 16px;
          max-width: 600px;
          width: 90%;
          max-height: 80vh;
          overflow-y: auto;
          padding: 1.5rem;
        }
      `}</style>

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card purple">
          <div className="stat-label">Total Employees</div>
          <div className="stat-value">{stats.total}</div>
          <div className="stat-sub">Across all departments</div>
        </div>
        <div className="stat-card green">
          <div className="stat-label">Active</div>
          <div className="stat-value">{stats.active}</div>
          <div className="stat-sub">Currently employed</div>
        </div>
        <div className="stat-card teal">
          <div className="stat-label">Fingerprint Enrolled</div>
          <div className="stat-value">{stats.enrolled}</div>
          <div className="stat-sub">{((stats.enrolled / stats.total) * 100 || 0).toFixed(1)}% of total</div>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', flex: 1, maxWidth: '400px' }}>
          <div className="input-wrap" style={{ flex: 1, position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)' }} />
            <input 
              type="text" 
              className="form-input" 
              placeholder="Search by name, code, or email..." 
              style={{ paddingLeft: '32px' }}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
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
          <button className="btn btn-ghost" onClick={fetchData} title="Refresh">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '8px', padding: '12px', marginBottom: '1rem', color: '#f87171', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {/* Employees Grid */}
      {filteredEmployees.length === 0 ? (
        <div className="card-box" style={{ textAlign: 'center', padding: '3rem' }}>
          <User size={48} style={{ color: 'var(--text3)', marginBottom: '1rem' }} />
          <p style={{ color: 'var(--text3)' }}>No employees found</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
          {filteredEmployees.map(emp => (
            <div key={emp.id} style={{
              background: 'var(--bg2)',
              border: `1px solid ${emp.is_active ? 'var(--border)' : 'rgba(239,68,68,0.3)'}`,
              borderRadius: '12px',
              padding: '1.25rem',
              transition: 'all 0.2s'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: '12px',
                    background: 'rgba(168,85,247,0.15)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '1.2rem'
                  }}>
                    <User size={24} style={{ color: '#a855f7' }} />
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '1rem' }}>{emp.name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text3)', fontFamily: 'var(--mono)' }}>
                      {emp.employee_code || 'No code'}
                    </div>
                  </div>
                </div>
                <Badge type={emp.is_active ? 'active' : 'inactive'}>
                  {emp.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '1rem', padding: '0.5rem 0', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
                {emp.email && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem' }}>
                    <Mail size={14} style={{ color: 'var(--text3)' }} />
                    <span>{emp.email}</span>
                  </div>
                )}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem' }}>
                  <Building2 size={14} style={{ color: 'var(--text3)' }} />
                  <span>{emp.department_name || 'No department'}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem' }}>
                  <Fingerprint size={14} style={{ color: emp.finger_id ? 'var(--teal)' : 'var(--text3)' }} />
                  <span style={{ color: emp.finger_id ? 'var(--teal)' : 'var(--text3)' }}>
                    {emp.finger_id ? `FP-${String(emp.finger_id).padStart(3, '0')}` : 'Not enrolled'}
                  </span>
                </div>
              </div>
              
              <button 
                className="btn btn-teal" 
                onClick={() => fetchEmployeeDetails(emp.id)}
                style={{ width: '100%', fontSize: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
              >
                <Eye size={14} /> View Details
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Employee Detail Modal */}
      {showDetailModal && selectedEmployee && (
        <div className="modal-overlay" onClick={() => setShowDetailModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 600 }}>Employee Details</h3>
              <button className="btn btn-ghost" onClick={() => setShowDetailModal(false)} style={{ padding: '4px' }}>✕</button>
            </div>
            
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border)' }}>
              <div style={{
                width: '64px',
                height: '64px',
                borderRadius: '16px',
                background: 'rgba(168,85,247,0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <User size={32} style={{ color: '#a855f7' }} />
              </div>
              <div>
                <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{selectedEmployee.name}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text3)' }}>{selectedEmployee.employee_code}</div>
                <Badge type={selectedEmployee.is_active ? 'active' : 'inactive'} style={{ marginTop: '6px' }}>
                  {selectedEmployee.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
              <div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text3)', fontFamily: 'var(--mono)' }}>Email</div>
                <div style={{ fontSize: '0.9rem' }}>{selectedEmployee.email || 'Not set'}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text3)', fontFamily: 'var(--mono)' }}>Department</div>
                <div style={{ fontSize: '0.9rem' }}>{selectedEmployee.department_name || 'Not assigned'}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text3)', fontFamily: 'var(--mono)' }}>Fingerprint ID</div>
                <div style={{ fontSize: '0.9rem' }}>{selectedEmployee.finger_id ? `FP-${String(selectedEmployee.finger_id).padStart(3, '0')}` : 'Not enrolled'}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text3)', fontFamily: 'var(--mono)' }}>Total Attendance</div>
                <div style={{ fontSize: '0.9rem' }}>{selectedEmployee.total_attendance || 0} records</div>
              </div>
            </div>
            
            <h4 style={{ marginBottom: '0.75rem', fontSize: '0.9rem' }}>Recent Attendance</h4>
            {attendanceHistory.length === 0 ? (
              <p style={{ textAlign: 'center', color: 'var(--text3)', padding: '1rem' }}>No attendance records</p>
            ) : (
              <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                <table style={{ width: '100%', fontSize: '0.8rem' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left' }}>Date</th>
                      <th style={{ textAlign: 'left' }}>Check In</th>
                      <th style={{ textAlign: 'left' }}>Check Out</th>
                      <th style={{ textAlign: 'left' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attendanceHistory.slice(0, 10).map((record, idx) => (
                      <tr key={idx}>
                        <td>{formatDate(record.date)}</td>
                        <td>{formatTime(record.check_in)}</td>
                        <td>{formatTime(record.check_out)}</td>
                        <td>
                          <Badge type={record.status === 'present' ? 'present' : 'absent'}>
                            {record.status || 'absent'}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default Employees;