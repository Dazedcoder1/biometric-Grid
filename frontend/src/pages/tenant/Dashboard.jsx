// src/pages/tenant/Dashboard.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { TrendChart, BarChart } from '../../components/Charts';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { 
  Building2, 
  Cpu, 
  Users, 
  Activity, 
  Calendar, 
  AlertCircle,
  TrendingUp,
  Clock,
  CheckCircle,
  RefreshCw,
  ChevronRight
} from 'lucide-react';

const TenantDashboard = () => {
  const { logout } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dashboardData, setDashboardData] = useState({
    organization: '',
    departments: { total: 0, active: 0 },
    users: { org_admins: 0, active_employees: 0, enrolled_employees: 0 },
    attendance_today: { present: 0, on_time: 0, late: 0 },
    recent_activity: []
  });
  const [deviceStatus, setDeviceStatus] = useState({ total: 0, online: 0, offline: 0 });
  const [departmentDistribution, setDepartmentDistribution] = useState([]);
  const [weeklyTrend, setWeeklyTrend] = useState([0, 0, 0, 0, 0, 0, 0]);

  useEffect(() => {
    fetchDashboardData();
    fetchDeviceStatus();
    fetchDepartmentDistribution();
    fetchWeeklyTrend();
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(() => {
      fetchDashboardData();
      fetchDeviceStatus();
    }, 30000);
    
    return () => clearInterval(interval);
  }, []);

  const fetchDashboardData = async () => {
    try {
      const data = await tenantApi.getDashboard();
      setDashboardData(data);
      setError('');
    } catch (err) {
      console.error('Dashboard fetch error:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  };

  const fetchDeviceStatus = async () => {
    try {
      const data = await tenantApi.getDeviceStatus();
      setDeviceStatus(data || { total: 0, online: 0, offline: 0 });
    } catch (err) {
      console.error('Device status fetch error:', err);
    }
  };

  const fetchDepartmentDistribution = async () => {
    try {
      const data = await tenantApi.getDepartments();
      const distribution = data.slice(0, 5).map(dept => ({
        name: dept.department_name,
        count: dept.employee_count || 0
      }));
      setDepartmentDistribution(distribution);
    } catch (err) {
      console.error('Department distribution fetch error:', err);
    }
  };

  const fetchWeeklyTrend = async () => {
    try {
      // Get last 7 days attendance data
      const promises = [];
      const today = new Date();
      for (let i = 6; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(today.getDate() - i);
        const dateStr = date.toISOString().split('T')[0];
        promises.push(
          tenantApi.getAttendanceByDate(dateStr).catch(() => [])
        );
      }
      
      const results = await Promise.all(promises);
      const trend = results.map(dayData => {
        const present = dayData.filter(record => record.status === 'present').length;
        const total = dayData.length || 1;
        return Math.round((present / total) * 100);
      });
      setWeeklyTrend(trend);
    } catch (err) {
      console.error('Weekly trend fetch error:', err);
    }
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return '--';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  const getAttendancePercentage = () => {
    const total = dashboardData.users.active_employees || 1;
    const present = dashboardData.attendance_today.present || 0;
    return ((present / total) * 100).toFixed(1);
  };

  const getChartData = () => {
    const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    return { labels, vals: weeklyTrend };
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="Command Center" 
        role="superadmin" 
        label="Tenant Admin" 
        abbr="TA" 
        color="#a855f7" 
        bgColor="rgba(168,85,247,0.15)"
      >
        <div className="skeleton-loader">
          {[1, 2, 3, 4, 5, 6].map(i => <div key={i} className="skeleton-card"></div>)}
        </div>
      </DashboardLayout>
    );
  }

  const { labels, vals } = getChartData();

  return (
    <DashboardLayout 
      title="Command Center" 
      role="superadmin" 
      label="Tenant Admin" 
      abbr="TA" 
      color="#a855f7" 
      bgColor="rgba(168,85,247,0.15)"
    >
      <style>{`
        .stat-card { transition: transform 0.2s, box-shadow 0.2s; }
        .stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
        .skeleton-card { background: var(--bg2); border-radius: 12px; height: 120px; animation: pulse 1.5s ease-in-out infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .trend-up { color: #22c55e; }
        .trend-down { color: #ef4444; }
        .activity-timeline { position: relative; padding-left: 20px; }
        .activity-timeline::before { content: ''; position: absolute; left: 6px; top: 0; bottom: 0; width: 2px; background: var(--border); }
        .activity-item { position: relative; margin-bottom: 1rem; padding-left: 1rem; }
        .activity-item::before { content: ''; position: absolute; left: -20px; top: 8px; width: 8px; height: 8px; border-radius: 50%; background: var(--teal); }
      `}</style>

      {/* Error Banner */}
      {error && (
        <div className="error-banner" style={{
          background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: '10px',
          padding: '12px 16px',
          marginBottom: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          color: '#f87171'
        }}>
          <AlertCircle size={18} />
          {error}
          <button onClick={fetchDashboardData} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#f87171', cursor: 'pointer' }}>
            <RefreshCw size={16} />
          </button>
        </div>
      )}

      {/* Welcome Section */}
      <div className="welcome-section" style={{
        background: 'linear-gradient(135deg, var(--bg2), var(--bg3))',
        border: '1px solid var(--border)',
        borderRadius: '16px',
        padding: '1.5rem',
        marginBottom: '1.5rem'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.25rem' }}>
              Welcome back, {dashboardData.organization || 'Administrator'}
            </h2>
            <p style={{ color: 'var(--text3)', fontSize: '0.85rem' }}>
              Here's what's happening with your organization today
            </p>
          </div>
          <div className="date-badge" style={{
            background: 'var(--bg4)',
            padding: '0.5rem 1rem',
            borderRadius: '8px',
            fontFamily: 'var(--mono)',
            fontSize: '0.8rem'
          }}>
            {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
        <div className="stat-card purple">
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Building2 size={14} /> Total Departments
          </div>
          <div className="stat-value">{dashboardData.departments?.total || 0}</div>
          <div className="stat-sub">
            <span className="trend-up">↑ {dashboardData.departments?.active || 0} active</span>
          </div>
        </div>

        <div className="stat-card teal">
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Users size={14} /> Total Employees
          </div>
          <div className="stat-value">{dashboardData.users?.active_employees || 0}</div>
          <div className="stat-sub">
            {dashboardData.users?.enrolled_employees || 0} fingerprint enrolled
          </div>
        </div>

        <div className="stat-card green">
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <CheckCircle size={14} /> Present Today
          </div>
          <div className="stat-value">{dashboardData.attendance_today?.present || 0}</div>
          <div className="stat-sub">
            {getAttendancePercentage()}% attendance rate
          </div>
        </div>

        <div className="stat-card amber">
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Clock size={14} /> Late Arrivals
          </div>
          <div className="stat-value">{dashboardData.attendance_today?.late || 0}</div>
          <div className="stat-sub">
            {dashboardData.attendance_today?.on_time || 0} on time
          </div>
        </div>

        <div className="stat-card blue">
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Cpu size={14} /> Devices
          </div>
          <div className="stat-value">{deviceStatus.total || 0}</div>
          <div className="stat-sub">
            <span className="trend-up">{deviceStatus.online || 0} online</span>
            {deviceStatus.offline > 0 && <span className="trend-down"> · {deviceStatus.offline} offline</span>}
          </div>
        </div>

        <div className="stat-card purple">
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Activity size={14} /> Org Admins
          </div>
          <div className="stat-value">{dashboardData.users?.org_admins || 0}</div>
          <div className="stat-sub">Department managers</div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="two-col">
        <div className="card-box">
          <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem' }}>
            <TrendingUp size={18} /> Weekly Attendance Trend
          </h4>
          <TrendChart labels={labels} vals={vals} color="#a855f7" />
          <p style={{ fontSize: '0.75rem', color: 'var(--text3)', marginTop: '0.75rem', textAlign: 'center' }}>
            Last 7 days attendance percentage
          </p>
        </div>

        <div className="card-box">
          <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem' }}>
            <Building2 size={18} /> Department Distribution
          </h4>
          {departmentDistribution.length === 0 ? (
            <p style={{ textAlign: 'center', color: 'var(--text3)', padding: '2rem' }}>
              No departments yet
            </p>
          ) : (
            <BarChart 
              labels={departmentDistribution.map(d => d.name.length > 10 ? d.name.substring(0, 8) + '…' : d.name)} 
              colors={['#a855f7', '#a855f7', '#a855f7', '#a855f7', '#a855f7']} 
              vals={departmentDistribution.map(d => d.count)} 
            />
          )}
        </div>
      </div>

      {/* Activity Timeline */}
      <div className="card-box">
        <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem' }}>
          <Activity size={18} /> Recent Activity
        </h4>
        <div className="activity-timeline">
          {dashboardData.recent_activity?.length === 0 ? (
            <p style={{ textAlign: 'center', color: 'var(--text3)', padding: '2rem' }}>
              No recent activity
            </p>
          ) : (
            dashboardData.recent_activity?.slice(0, 10).map((activity, idx) => (
              <div key={idx} className="activity-item">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div>
                    <div style={{ fontWeight: 500, fontSize: '0.85rem' }}>
                      {activity.name || activity.employee_name || 'System'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text3)' }}>
                      {activity.department_name && `${activity.department_name} · `}
                      {activity.record_type === 'IN' ? 'Checked In' : activity.record_type === 'OUT' ? 'Checked Out' : 'Attendance marked'}
                    </div>
                  </div>
                  <div style={{ fontSize: '0.7rem', fontFamily: 'var(--mono)', color: 'var(--text3)' }}>
                    {formatTime(activity.timestamp)}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="quick-actions" style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '1rem',
        marginTop: '1rem'
      }}>
        <button className="btn btn-teal" onClick={() => window.location.href = '/super/departments'} style={{ padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
          Manage Departments <ChevronRight size={16} />
        </button>
        <button className="btn btn-teal" onClick={() => window.location.href = '/super/devices'} style={{ padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
          Manage Devices <ChevronRight size={16} />
        </button>
        <button className="btn btn-teal" onClick={() => window.location.href = '/super/holidays'} style={{ padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
          Manage Holidays <ChevronRight size={16} />
        </button>
        <button className="btn btn-teal" onClick={() => window.location.href = '/super/org-admins'} style={{ padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
          Manage Org Admins <ChevronRight size={16} />
        </button>
      </div>
    </DashboardLayout>
  );
};

export default TenantDashboard;