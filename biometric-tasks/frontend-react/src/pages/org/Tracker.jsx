// src/pages/org/Tracker.jsx
import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { trackerApi } from '../../services/trackerApi';
import { useAuth } from '../../context/AuthContext';
import { 
  Users, 
  Activity, 
  Clock, 
  Camera, 
  TrendingUp, 
  UserCheck, 
  AlertCircle,
  RefreshCw,
  Eye,
  Play,
  X,
  ChevronLeft,
  ChevronRight,
  Search,
  Building2,
  Monitor,
  BarChart3
} from 'lucide-react';

const OrgTracker = () => {
  const { logout, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [employees, setEmployees] = useState([]);
  const [filteredEmployees, setFilteredEmployees] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [departmentName, setDepartmentName] = useState('');
  const [stats, setStats] = useState({
    totalEmployees: 0,
    activeEmployees: 0,
    totalHoursToday: 0,
    totalScreenshots: 0,
    avgHoursPerEmployee: 0,
    complianceRate: 0
  });
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [employeeSessions, setEmployeeSessions] = useState([]);
  const [employeeShots, setEmployeeShots] = useState([]);
  const [activeTab, setActiveTab] = useState('sessions');
  const [viewerOpen, setViewerOpen] = useState(false);
  const [currentShotIndex, setCurrentShotIndex] = useState(0);
  const [chartData, setChartData] = useState({ labels: [], values: [] });
  const [reportsSummary, setReportsSummary] = useState([]);
  const [lastRefreshed, setLastRefreshed] = useState(new Date());

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(() => {
      if (document.hidden === false) {
        fetchDashboardData();
      }
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    filterEmployees();
  }, [searchTerm, employees]);

  const fetchDashboardData = async () => {
    setLoading(true);
    setError('');
    try {
      // Fetch all data in parallel
      const employeesData = await trackerApi.getEmployees().catch(() => []);
      const statsData = await trackerApi.getDashboardStats().catch(() => null);
      const reportsData = await trackerApi.getReports().catch(() => []);
      
      setEmployees(employeesData || []);
      setFilteredEmployees(employeesData || []);
      
      // Calculate activity data from employees
      if (employeesData && employeesData.length > 0) {
        const topUsers = [...employeesData]
          .sort((a, b) => (b.totalWorkingHours || 0) - (a.totalWorkingHours || 0))
          .slice(0, 6);
        
        setChartData({
          labels: topUsers.map(u => (u.name || u.email || 'Unknown').substring(0, 14)),
          values: topUsers.map(u => u.totalWorkingHours || 0)
        });
      }
      
      if (statsData) {
        setStats(statsData);
        setDepartmentName(statsData.department_name || user?.department_name || 'Your Department');
      }
      
      setReportsSummary(reportsData);
      setLastRefreshed(new Date());
    } catch (err) {
      console.error('Tracker dashboard error:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load tracker data');
    } finally {
      setLoading(false);
    }
  };

  const filterEmployees = () => {
    if (!searchTerm.trim()) {
      setFilteredEmployees(employees);
    } else {
      const term = searchTerm.toLowerCase();
      const filtered = employees.filter(emp => 
        (emp.name || '').toLowerCase().includes(term) ||
        (emp.email || '').toLowerCase().includes(term) ||
        (emp.employee_code || '').toLowerCase().includes(term)
      );
      setFilteredEmployees(filtered);
    }
  };

  const fetchEmployeeDetails = async (employeeId) => {
    setError('');
    try {
      const details = await trackerApi.getEmployeeDetails(employeeId);
      const shots = await trackerApi.getScreenshots(employeeId, 50);
      
      setSelectedEmployee(details);
      setEmployeeSessions(details.sessions || []);
      setEmployeeShots(shots || []);
      setShowDetailsModal(true);
      setActiveTab('sessions');
    } catch (err) {
      console.error('Failed to fetch employee details:', err);
      setError(err.message || 'Failed to load employee details');
      setTimeout(() => setError(''), 3000);
    }
  };

  const openImageViewer = (index) => {
    setCurrentShotIndex(index);
    setViewerOpen(true);
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return '--';
    try {
      return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '--';
    }
  };

  const formatDate = (timestamp) => {
    if (!timestamp) return '--';
    try {
      return new Date(timestamp).toLocaleDateString();
    } catch {
      return '--';
    }
  };

  const formatDateTime = (timestamp) => {
    if (!timestamp) return '--';
    try {
      return new Date(timestamp).toLocaleString();
    } catch {
      return '--';
    }
  };

  const getInitials = (name) => {
    if (!name) return 'U';
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="Activity Tracker" 
        role="orgadmin" 
        label="Department Admin" 
        abbr="DA" 
        color="#00d4aa" 
        bgColor="rgba(0,212,170,0.15)"
      >
        <div className="skeleton-loader" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
          {[1,2,3,4].map(i => <div key={i} style={{ background: 'var(--bg2)', borderRadius: '16px', height: '120px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>)}
        </div>
        <div style={{ background: 'var(--bg2)', borderRadius: '16px', height: '400px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="Activity Tracker" 
      role="orgadmin" 
      label="Department Admin" 
      abbr="DA" 
      color="#00d4aa" 
      bgColor="rgba(0,212,170,0.15)"
    >
      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        
        .stat-card { transition: all 0.2s; cursor: pointer; }
        .stat-card:hover { transform: translateY(-2px); }
        
        .employee-row {
          transition: all 0.2s;
          cursor: pointer;
        }
        .employee-row:hover {
          background: var(--bg3);
        }
        
        .status-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 12px;
          border-radius: 20px;
          font-size: 0.7rem;
          font-weight: 600;
        }
        .status-active {
          background: rgba(34,197,94,0.1);
          color: #4ade80;
          border: 1px solid rgba(34,197,94,0.2);
        }
        .status-inactive {
          background: rgba(239,68,68,0.1);
          color: #f87171;
          border: 1px solid rgba(239,68,68,0.2);
        }
        
        .status-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: currentColor;
        }
        .status-dot.pulse {
          animation: pulse-dot 2s infinite;
        }
        @keyframes pulse-dot {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0,0,0,0.85);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 2000;
          animation: fadeIn 0.2s ease;
        }
        
        .modal-content {
          background: var(--bg2);
          border: 1px solid var(--border);
          border-radius: 24px;
          max-width: 950px;
          width: 90%;
          max-height: 85vh;
          overflow-y: auto;
          animation: slideIn 0.3s ease;
        }
        
        .stat-row {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 1rem;
          margin-bottom: 1.5rem;
        }
        
        .stat-box {
          background: var(--bg3);
          border-radius: 12px;
          padding: 1rem;
          text-align: center;
        }
        .stat-box-value {
          font-size: 1.5rem;
          font-weight: 700;
          color: #00d4aa;
        }
        .stat-box-label {
          font-size: 0.7rem;
          color: var(--text3);
          margin-top: 4px;
        }
        
        .session-card {
          background: var(--bg3);
          border-radius: 12px;
          padding: 0.75rem 1rem;
          margin-bottom: 0.5rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 0.5rem;
        }
        
        .screenshot-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 1rem;
        }
        
        .screenshot-card {
          background: var(--bg3);
          border-radius: 12px;
          overflow: hidden;
          cursor: pointer;
          transition: all 0.2s;
          border: 1px solid var(--border);
        }
        .screenshot-card:hover {
          transform: translateY(-2px);
          border-color: #00d4aa;
        }
        .screenshot-card img {
          width: 100%;
          height: 140px;
          object-fit: cover;
          background: var(--bg);
        }
        .screenshot-meta {
          padding: 8px 10px;
          font-size: 0.7rem;
          color: var(--text3);
          border-top: 1px solid var(--border);
        }
        
        .viewer-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0,0,0,0.98);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 3000;
          flex-direction: column;
        }
        .viewer-img {
          max-width: 88vw;
          max-height: 80vh;
          border-radius: 12px;
        }
        .viewer-controls {
          display: flex;
          gap: 1rem;
          margin-top: 1.5rem;
          align-items: center;
        }
        
        .tabs {
          display: flex;
          gap: 0.5rem;
          margin-bottom: 1rem;
          border-bottom: 1px solid var(--border);
          padding-bottom: 0.5rem;
        }
        .tab-btn {
          background: none;
          border: none;
          padding: 0.5rem 1rem;
          cursor: pointer;
          color: var(--text2);
          border-radius: 8px;
          transition: all 0.2s;
        }
        .tab-btn.active {
          background: var(--bg3);
          color: #00d4aa;
        }
        
        .refresh-indicator {
          font-size: 0.7rem;
          color: var(--text3);
        }
        
        .department-badge {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 6px 14px;
          background: rgba(0,212,170,0.1);
          border-radius: 20px;
          font-size: 0.75rem;
          color: #00d4aa;
        }
        
        .chart-container {
          background: var(--bg2);
          border-radius: 16px;
          padding: 1rem;
          margin-top: 1rem;
        }
        .chart-bar {
          height: 8px;
          background: #00d4aa;
          border-radius: 4px;
          transition: width 0.5s ease;
        }
      `}</style>

      {/* Error Message */}
      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '12px', padding: '12px 16px', marginBottom: '1rem', color: '#f87171', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertCircle size={16} /> {error}
          <button onClick={fetchDashboardData} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#f87171', cursor: 'pointer' }}>
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      )}

      {/* Welcome Section */}
      <div className="welcome-section" style={{
        background: 'linear-gradient(135deg, var(--bg2), var(--bg3))',
        border: '1px solid var(--border)',
        borderRadius: '16px',
        padding: '1.25rem 1.5rem',
        marginBottom: '1.5rem'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '4px' }}>
              <Monitor size={20} style={{ color: '#00d4aa' }} />
              <h2 style={{ fontSize: '1.3rem', fontWeight: 600 }}>Employee Activity Monitor</h2>
            </div>
            <p style={{ color: 'var(--text3)', fontSize: '0.85rem' }}>
              Track real-time activity, working hours, and screenshots for your department
            </p>
          </div>
          <div className="department-badge">
            <Building2 size={14} />
            {departmentName || user?.department_name || 'Department Admin'}
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card" style={{ borderTopColor: '#00d4aa', borderTopWidth: '3px' }}>
          <div className="stat-label"><Users size={14} /> Total Employees</div>
          <div className="stat-value">{stats.totalEmployees}</div>
          <div className="stat-sub">In your department</div>
        </div>
        <div className="stat-card" style={{ borderTopColor: '#4ade80', borderTopWidth: '3px' }}>
          <div className="stat-label"><UserCheck size={14} /> Active Now</div>
          <div className="stat-value">{stats.activeEmployees}</div>
          <div className="stat-sub">{stats.complianceRate}% of workforce</div>
        </div>
        <div className="stat-card" style={{ borderTopColor: '#f59e0b', borderTopWidth: '3px' }}>
          <div className="stat-label"><Clock size={14} /> Hours Today</div>
          <div className="stat-value">{stats.totalHoursToday.toFixed(1)}</div>
          <div className="stat-sub">Total tracked hours</div>
        </div>
        <div className="stat-card" style={{ borderTopColor: '#a855f7', borderTopWidth: '3px' }}>
          <div className="stat-label"><Camera size={14} /> Screenshots</div>
          <div className="stat-value">{stats.totalScreenshots}</div>
          <div className="stat-sub">All time captures</div>
        </div>
      </div>

      {/* Top Performers Chart */}
      {chartData.labels.length > 0 && chartData.values.length > 0 && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem' }}>
            <BarChart3 size={16} style={{ color: '#00d4aa' }} />
            <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>Top Performers (Total Hours)</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {chartData.labels.map((label, idx) => {
              const maxValue = Math.max(...chartData.values, 1);
              const percentage = (chartData.values[idx] / maxValue) * 100;
              return (
                <div key={idx}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', marginBottom: '4px' }}>
                    <span style={{ color: 'var(--text2)' }}>{label}</span>
                    <span style={{ fontFamily: 'var(--mono)', color: '#00d4aa' }}>{chartData.values[idx].toFixed(1)}h</span>
                  </div>
                  <div style={{ background: 'var(--bg3)', borderRadius: '4px', overflow: 'hidden' }}>
                    <div className="chart-bar" style={{ width: `${percentage}%` }}></div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Refresh Indicator */}
      <div className="refresh-indicator" style={{ textAlign: 'right', marginBottom: '1rem' }}>
        Last updated: {lastRefreshed.toLocaleTimeString()}
        <RefreshCw size={12} style={{ display: 'inline', marginLeft: '8px', cursor: 'pointer' }} onClick={fetchDashboardData} />
      </div>

      {/* Search Bar */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div className="input-wrap" style={{ position: 'relative', maxWidth: '320px' }}>
          <Search size={16} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)' }} />
          <input 
            type="text" 
            className="form-input" 
            placeholder="Search by name, email or employee code..." 
            style={{ paddingLeft: '32px' }}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Employees Table */}
      <div className="table-wrap">
        <div className="table-header">
          <span className="table-title">
            Employee Activity Monitor
            <span style={{ fontSize: '0.7rem', color: 'var(--text3)', marginLeft: '8px' }}>
              ({filteredEmployees.length} employees)
            </span>
          </span>
          <button className="btn btn-ghost" onClick={fetchDashboardData}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
        
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', minWidth: '700px' }}>
            <thead>
              <tr>
                <th>Employee</th>
                <th>Status</th>
                <th>Today's Hours</th>
                <th>Total Hours</th>
                <th>Screenshots</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredEmployees.length === 0 ? (
                <tr>
                  <td colSpan="6" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>
                    {searchTerm ? 'No matching employees found' : 'No employees in your department'}
                   </td>
                </tr>
              ) : (
                filteredEmployees.map(emp => (
                  <tr key={emp.id} className="employee-row" onClick={() => fetchEmployeeDetails(emp.id)}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{
                          width: '36px',
                          height: '36px',
                          borderRadius: '10px',
                          background: 'rgba(0,212,170,0.15)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 600,
                          fontSize: '0.8rem',
                          color: '#00d4aa'
                        }}>
                          {getInitials(emp.name || emp.email)}
                        </div>
                        <div>
                          <div style={{ fontWeight: 500 }}>{emp.name || emp.email}</div>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>{emp.employee_code || emp.email}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className={`status-badge ${emp.hasActiveSession ? 'status-active' : 'status-inactive'}`}>
                        <span className={`status-dot ${emp.hasActiveSession ? 'pulse' : ''}`}></span>
                        {emp.hasActiveSession ? 'Active' : 'Offline'}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--mono)', fontWeight: 600 }}>{(emp.todayHours || 0).toFixed(1)}h</td>
                    <td style={{ fontFamily: 'var(--mono)' }}>{(emp.totalWorkingHours || 0).toFixed(1)}h</td>
                    <td>📸 {emp.screenshotCount || 0}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button 
                          className="btn btn-teal" 
                          onClick={(e) => { e.stopPropagation(); fetchEmployeeDetails(emp.id); }}
                          style={{ padding: '4px 12px', fontSize: '0.7rem' }}
                        >
                          <Eye size={12} style={{ marginRight: '4px' }} /> Details
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Reports Summary Section */}
      {reportsSummary.length > 0 && (
        <div className="card-box" style={{ marginTop: '1.5rem' }}>
          <h4 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TrendingUp size={16} /> Department Summary
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.75rem' }}>
            {reportsSummary.map((item, idx) => (
              <div key={idx} style={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center',
                padding: '0.5rem 0',
                borderBottom: '1px solid var(--border)'
              }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text3)' }}>{item.label}</span>
                <span style={{ fontWeight: 600, color: '#00d4aa' }}>{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Employee Details Modal */}
      {showDetailsModal && selectedEmployee && (
        <div className="modal-overlay" onClick={() => setShowDetailsModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              padding: '1.25rem 1.5rem',
              borderBottom: '1px solid var(--border)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '12px',
                  background: 'rgba(0,212,170,0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '1.2rem',
                  fontWeight: 600,
                  color: '#00d4aa'
                }}>
                  {getInitials(selectedEmployee.name || selectedEmployee.email)}
                </div>
                <div>
                  <h3 style={{ fontSize: '1.2rem', fontWeight: 600 }}>{selectedEmployee.name || selectedEmployee.email}</h3>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text3)' }}>
                    {selectedEmployee.employee_code || selectedEmployee.email}
                    {selectedEmployee.department_name && ` · ${selectedEmployee.department_name}`}
                  </p>
                </div>
              </div>
              <button 
                className="btn btn-ghost" 
                onClick={() => setShowDetailsModal(false)}
                style={{ padding: '6px' }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ padding: '1.5rem' }}>
              {/* Stats Row */}
              <div className="stat-row">
                <div className="stat-box">
                  <div className="stat-box-value">{(selectedEmployee.totalWorkingHours || 0).toFixed(1)}</div>
                  <div className="stat-box-label">Total Hours</div>
                </div>
                <div className="stat-box">
                  <div className="stat-box-value">{(selectedEmployee.todayHours || 0).toFixed(1)}</div>
                  <div className="stat-box-label">Today's Hours</div>
                </div>
                <div className="stat-box">
                  <div className="stat-box-value">{selectedEmployee.totalSessions || 0}</div>
                  <div className="stat-box-label">Sessions</div>
                </div>
                <div className="stat-box">
                  <div className="stat-box-value">{selectedEmployee.screenshotCount || 0}</div>
                  <div className="stat-box-label">Screenshots</div>
                </div>
              </div>

              {/* Active Session Info */}
              {selectedEmployee.hasActiveSession && selectedEmployee.sessionStart && (
                <div className="session-card" style={{ background: 'rgba(34,197,94,0.05)', borderColor: 'rgba(34,197,94,0.2)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Play size={14} style={{ color: '#4ade80' }} />
                    <span style={{ fontSize: '0.85rem' }}>Active session since {formatDateTime(selectedEmployee.sessionStart)}</span>
                  </div>
                </div>
              )}

              {/* Tabs */}
              <div className="tabs">
                <button 
                  className={`tab-btn ${activeTab === 'sessions' ? 'active' : ''}`}
                  onClick={() => setActiveTab('sessions')}
                >
                  Session History ({employeeSessions.length})
                </button>
                <button 
                  className={`tab-btn ${activeTab === 'captures' ? 'active' : ''}`}
                  onClick={() => setActiveTab('captures')}
                >
                  Screenshots ({employeeShots.length})
                </button>
              </div>

              {/* Sessions Panel */}
              {activeTab === 'sessions' && (
                <div>
                  {employeeSessions.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text3)' }}>
                      No sessions recorded
                    </div>
                  ) : (
                    employeeSessions.map((session, idx) => (
                      <div key={idx} className="session-card">
                        <div>
                          <div style={{ fontWeight: 500 }}>{formatDate(session.checkInTime)}</div>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>
                            {formatTime(session.checkInTime)} → {session.checkOutTime ? formatTime(session.checkOutTime) : 'Active'}
                          </div>
                        </div>
                        <div style={{ fontFamily: 'var(--mono)', fontSize: '0.85rem' }}>
                          {(session.durationHours || 0).toFixed(1)}h · 📸 {session.screenshotCount || 0}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Captures Panel */}
              {activeTab === 'captures' && (
                <div className="screenshot-grid">
                  {employeeShots.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text3)', gridColumn: '1/-1' }}>
                      No screenshots available
                    </div>
                  ) : (
                    employeeShots.map((shot, idx) => (
                      <div key={idx} className="screenshot-card" onClick={() => openImageViewer(idx)}>
                        <img 
                          src={shot.url} 
                          alt={`Screenshot ${idx + 1}`}
                          onError={(e) => { e.target.src = 'https://placehold.co/400x200/1e2535/6b7585?text=No+Preview'; }}
                        />
                        <div className="screenshot-meta">
                          {formatDateTime(shot.timestamp)}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Image Viewer Modal */}
      {viewerOpen && employeeShots.length > 0 && (
        <div className="viewer-overlay" onClick={() => setViewerOpen(false)}>
          <button 
            onClick={() => setViewerOpen(false)}
            style={{
              position: 'absolute',
              top: '20px',
              right: '30px',
              background: 'var(--bg2)',
              border: '1px solid var(--border)',
              padding: '8px 16px',
              borderRadius: '20px',
              cursor: 'pointer',
              color: 'var(--text)',
              zIndex: 1
            }}
          >
            ✕ Close
          </button>
          
          <img 
            className="viewer-img" 
            src={employeeShots[currentShotIndex]?.url} 
            alt="Screenshot"
            onClick={(e) => e.stopPropagation()}
          />
          
          <div className="viewer-controls" onClick={(e) => e.stopPropagation()}>
            <button 
              className="btn btn-ghost" 
              onClick={() => setCurrentShotIndex(prev => (prev - 1 + employeeShots.length) % employeeShots.length)}
            >
              <ChevronLeft size={16} /> Previous
            </button>
            <span style={{ color: 'var(--text3)', fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>
              {currentShotIndex + 1} / {employeeShots.length}
            </span>
            <button 
              className="btn btn-ghost" 
              onClick={() => setCurrentShotIndex(prev => (prev + 1) % employeeShots.length)}
            >
              Next <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default OrgTracker;