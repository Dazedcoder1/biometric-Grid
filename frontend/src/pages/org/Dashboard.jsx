// src/pages/org/Dashboard.jsx
import React, { useEffect, useState } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { TrendChart } from '../../components/Charts';
import { orgApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { 
  Users, 
  Calendar, 
  Clock, 
  TrendingUp, 
  UserCheck,
  UserX,
  AlertCircle,
  RefreshCw,
  Briefcase,
  Gift,
  ChevronRight,
  User
} from 'lucide-react';

const OrgDash = () => {
  const { logout, user } = useAuth();
  const [dashboardData, setDashboardData] = useState(null);
  const [trendData, setTrendData] = useState([0, 0, 0, 0, 0, 0, 0]);
  const [todayLeaves, setTodayLeaves] = useState([]);
  const [holidays, setHolidays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastRefreshed, setLastRefreshed] = useState(new Date());

  useEffect(() => {
    fetchDashboard();
    const interval = setInterval(() => {
      fetchDashboard();
    }, 60000);
    return () => clearInterval(interval);
  }, []);

  const fetchDashboard = async () => {
    setLoading(true);
    setError("");
    try {
      const [dash, leavesData, holidayData] = await Promise.all([
        orgApi.getDashboard(),
        orgApi.getLeaveRequests(),
        orgApi.getUpcomingHolidays(5),
      ]);

      setDashboardData(dash);
      setHolidays(holidayData || []);

      const today = new Date().toISOString().split("T")[0];
      const todaysLeave = (leavesData || []).filter(l =>
        l.start_date <= today && l.end_date >= today && l.status === "approved"
      );
      setTodayLeaves(todaysLeave);

      // Fetch last 7 days attendance trend
      const last7days = [];
      const todayDate = new Date();
      for (let i = 6; i >= 0; i--) {
        const d = new Date();
        d.setDate(todayDate.getDate() - i);
        const formatted = d.toISOString().split("T")[0];
        try {
          const res = await orgApi.getAttendanceByDate(formatted);
          const presentCount = (res || []).filter(a => a.status === "present").length;
          last7days.push(presentCount);
        } catch {
          last7days.push(0);
        }
      }
      setTrendData(last7days);
      setLastRefreshed(new Date());
    } catch (err) {
      console.error("Dashboard fetch error:", err);
      if (err?.response?.status === 401) {
        logout();
      } else {
        setError(err.message || "Failed to load dashboard");
      }
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "--";
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const formatTimeAgo = () => {
    const diff = Math.floor((new Date() - lastRefreshed) / 1000);
    if (diff < 60) return `${diff} seconds ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)} minutes ago`;
    return `${Math.floor(diff / 3600)} hours ago`;
  };

  // Get admin name from user context
  const getAdminName = () => {
    if (user?.name) return user.name;
    if (dashboardData?.admin_name) return dashboardData.admin_name;
    return "Admin";
  };

  if (loading && !dashboardData) {
    return (
      <DashboardLayout title="Dashboard" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
        <div className="skeleton-loader" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} style={{ background: 'var(--bg2)', borderRadius: '16px', height: '120px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>
          ))}
        </div>
        <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }`}</style>
      </DashboardLayout>
    );
  }

  const stats = dashboardData || {
    department: user?.department_name || 'Department',
    admin_name: user?.name || 'Admin',
    employees: { total: 0, active: 0, enrolled: 0 },
    attendance_today: { present: 0, absent: 0, late: 0, on_time: 0 },
    pending_leaves: 0,
  };

  const attendancePct = stats.employees.total > 0
    ? Math.round((stats.attendance_today.present / stats.employees.total) * 100)
    : 0;

  const adminName = getAdminName();

  return (
    <DashboardLayout title="Dashboard" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      <style>{`
        .stat-card { transition: all 0.2s; cursor: pointer; }
        .stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
        .welcome-section { background: linear-gradient(135deg, var(--bg2), var(--bg3)); border: 1px solid var(--border); border-radius: 20px; }
        .activity-timeline { position: relative; padding-left: 20px; }
        .activity-timeline::before { content: ''; position: absolute; left: 6px; top: 0; bottom: 0; width: 2px; background: linear-gradient(to bottom, var(--teal), transparent); }
        .activity-item { position: relative; margin-bottom: 1rem; padding-left: 1rem; }
        .activity-item::before { content: ''; position: absolute; left: -20px; top: 8px; width: 8px; height: 8px; border-radius: 50%; background: var(--teal); box-shadow: 0 0 0 2px rgba(0,212,170,0.2); }
        .refresh-indicator { font-size: 0.7rem; color: var(--text3); font-family: var(--mono); }
      `}</style>

      {error && (
        <div className="error-banner" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '12px', padding: '14px 18px', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '12px', color: '#f87171' }}>
          <AlertCircle size={18} />
          <span style={{ flex: 1 }}>{error}</span>
          <button onClick={fetchDashboard} style={{ background: 'none', border: 'none', color: '#f87171', cursor: 'pointer' }}>
            <RefreshCw size={16} /> Retry
          </button>
        </div>
      )}

      <div className="welcome-section" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 600, marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                background: 'rgba(0,212,170,0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <User size={20} style={{ color: '#00d4aa' }} />
              </div>
              Welcome back, {adminName}!
            </h2>
            <p style={{ color: 'var(--text3)', fontSize: '0.85rem' }}>
              Managing <strong>{stats.department || 'your department'}</strong> · Here's your department's attendance overview
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="date-badge" style={{ background: 'var(--bg4)', padding: '0.5rem 1rem', borderRadius: '10px', fontFamily: 'var(--mono)', fontSize: '0.75rem', marginBottom: '0.25rem' }}>
              {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
            </div>
            <div className="refresh-indicator">
              Updated {formatTimeAgo()} <RefreshCw size={10} style={{ display: 'inline', marginLeft: '4px', cursor: 'pointer' }} onClick={fetchDashboard} />
            </div>
          </div>
        </div>
      </div>

      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
        <div className="stat-card teal">
          <div className="stat-label"><Users size={14} /> Total Employees</div>
          <div className="stat-value">{stats.employees.total || 0}</div>
          <div className="stat-sub">{stats.employees.active || 0} active</div>
        </div>
        <div className="stat-card green">
          <div className="stat-label"><UserCheck size={14} /> Present Today</div>
          <div className="stat-value">{stats.attendance_today.present || 0}</div>
          <div className="stat-sub">{attendancePct}% of workforce</div>
        </div>
        <div className="stat-card red">
          <div className="stat-label"><UserX size={14} /> Absent Today</div>
          <div className="stat-value">{stats.attendance_today.absent || 0}</div>
          <div className="stat-sub">{stats.attendance_today.late || 0} late arrivals</div>
        </div>
        <div className="stat-card amber">
          <div className="stat-label"><Clock size={14} /> On Time</div>
          <div className="stat-value">{stats.attendance_today.on_time || 0}</div>
          <div className="stat-sub">Arrived on schedule</div>
        </div>
        <div className="stat-card blue">
          <div className="stat-label"><Briefcase size={14} /> Pending Leaves</div>
          <div className="stat-value">{stats.pending_leaves || 0}</div>
          <div className="stat-sub">Awaiting approval</div>
        </div>
        <div className="stat-card purple">
          <div className="stat-label"><TrendingUp size={14} /> Fingerprint Enrolled</div>
          <div className="stat-value">{stats.employees.enrolled || 0}</div>
          <div className="stat-sub">{stats.employees.total > 0 ? Math.round((stats.employees.enrolled / stats.employees.total) * 100) : 0}% completion</div>
        </div>
      </div>

      <div className="two-col">
        <div className="card-box">
          <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem' }}>
            <TrendingUp size={18} /> Attendance Trend (Last 7 Days)
          </h4>
          <TrendChart labels={['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']} vals={trendData} color="#00d4aa" />
          <p style={{ fontSize: '0.7rem', color: 'var(--text3)', textAlign: 'center', marginTop: '0.75rem' }}>Number of employees present each day</p>
        </div>

        <div className="card-box">
          <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem' }}>
            <Calendar size={18} /> Today's Overview
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
            <div style={{ textAlign: 'center', padding: '0.75rem', background: 'var(--bg3)', borderRadius: '12px' }}>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#22c55e' }}>{stats.attendance_today.present || 0}</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>Present</div>
            </div>
            <div style={{ textAlign: 'center', padding: '0.75rem', background: 'var(--bg3)', borderRadius: '12px' }}>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f59e0b' }}>{stats.attendance_today.late || 0}</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>Late</div>
            </div>
          </div>
          <div style={{ height: '4px', background: 'var(--bg3)', borderRadius: '2px', overflow: 'hidden' }}>
            <div style={{ width: `${attendancePct}%`, height: '100%', background: 'linear-gradient(90deg, var(--teal), var(--teal2))', borderRadius: '2px' }}></div>
          </div>
          <p style={{ fontSize: '0.7rem', color: 'var(--text3)', textAlign: 'center', marginTop: '0.5rem' }}>{attendancePct}% attendance rate today</p>
        </div>
      </div>

      <div className="two-col">
        <div className="card-box">
          <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem' }}>
            <Briefcase size={18} /> Employees on Leave Today
          </h4>
          {todayLeaves.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text3)' }}>No employees on leave today</div>
          ) : (
            <div className="activity-timeline">
              {todayLeaves.map(l => (
                <div key={l.leave_id} className="activity-item">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div>
                      <span style={{ fontWeight: 500 }}>{l.employee_name}</span>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text3)', marginLeft: '8px' }}>{l.leave_type} leave</span>
                    </div>
                    <div style={{ fontSize: '0.7rem', fontFamily: 'var(--mono)', color: 'var(--text3)' }}>Returns {formatDate(l.end_date)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card-box">
          <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem' }}>
            <Gift size={18} /> Upcoming Holidays
          </h4>
          {holidays.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text3)' }}>No upcoming holidays</div>
          ) : (
            <div className="activity-timeline">
              {holidays.map(h => (
                <div key={h.holiday_id || h.id} className="activity-item">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div>
                      <span style={{ fontWeight: 500 }}>{h.name || h.holiday_name}</span>
                    </div>
                    <div style={{ fontSize: '0.7rem', fontFamily: 'var(--mono)', color: 'var(--teal)' }}>{formatDate(h.holiday_date || h.date)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="quick-actions" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginTop: '1rem' }}>
        <button className="btn btn-teal" onClick={() => window.location.href = '/org/employees'} style={{ padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
          Manage Employees <ChevronRight size={16} />
        </button>
        <button className="btn btn-teal" onClick={() => window.location.href = '/org/leaves'} style={{ padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
          Review Leaves <ChevronRight size={16} />
        </button>
        <button className="btn btn-teal" onClick={() => window.location.href = '/org/attendance'} style={{ padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
          View Attendance <ChevronRight size={16} />
        </button>
      </div>
    </DashboardLayout>
  );
};

export default OrgDash;