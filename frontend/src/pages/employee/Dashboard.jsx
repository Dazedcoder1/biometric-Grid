// src/pages/employee/Dashboard.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { TrendChart } from '../../components/Charts';
import { employeeApi, publicApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const Dashboard = () => {
  const { user } = useAuth();
  const [dashboardData, setDashboardData] = useState({
    check_in: null,
    check_out: null,
    present_days: 0,
  });
  const [todayAttendance, setTodayAttendance] = useState({
    check_in: null,
    check_out: null,
    status: 'absent',
    hours_worked: 0,
    met_min_hours: false,
    is_late: false,
  });
  const [monthlyStats, setMonthlyStats] = useState({
    present_days: 0,
    days_met_min_hours: 0,
    total_hours: 0,
    attendance_percentage: 0,
    total_days_in_month: 30,
    estimated_working_days: 22,
    absent_days: 0,
    late_days: 0,
    on_time_days: 0,
    overtime_hours: 0,
    average_hours_per_day: 0,
    compliance_rate: 0,
  });
  const [upcomingHoliday, setUpcomingHoliday] = useState(null);
  const [pendingLeaves, setPendingLeaves] = useState(0);
  const [leaveStats, setLeaveStats] = useState({
    total: 0,
    pending: 0,
    approved: 0,
    rejected: 0,
  });
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchAllData();
  }, []);

  const fetchSettings = async () => {
    try {
      const tenantId = user?.tenant_id;
      if (!tenantId) {
        console.warn("No tenant_id found, using default settings");
        setSettings({
          office_start_time: "09:00:00",
          office_end_time: "18:00:00",
          late_threshold_minutes: 15,
          min_working_hours: 9.0,
        });
        return;
      }
      
      const data = await publicApi.getTenantSettings(tenantId);
      setSettings(data);
    } catch (err) {
      console.error("Failed to fetch settings:", err);
      setSettings({
        office_start_time: "09:00:00",
        office_end_time: "18:00:00",
        late_threshold_minutes: 15,
        min_working_hours: 9.0,
      });
    }
  };

  const fetchAllData = async () => {
    setLoading(true);
    setError(null);
    try {
      const now = new Date();
      const currentMonth = now.getMonth() + 1;
      const currentYear = now.getFullYear();

      await fetchSettings();

      const [dashboard, today, monthly, upcoming, leaveStatsData, leaveBalance] = await Promise.all([
        employeeApi.getDashboard(),
        employeeApi.getTodayAttendance(),
        employeeApi.getMonthlyStats(currentMonth, currentYear),
        employeeApi.getUpcomingHoliday(),
        employeeApi.getLeaveStats(),
        employeeApi.getLeaveBalance(),
      ]);

      console.log('Dashboard Data:', dashboard);
      console.log('Today Attendance:', today);
      console.log('Monthly Stats:', monthly);

      setDashboardData(dashboard || { check_in: null, check_out: null, present_days: 0 });
      setTodayAttendance(today || { 
        check_in: null, 
        check_out: null, 
        status: 'absent', 
        hours_worked: 0,
        met_min_hours: false,
        is_late: false
      });
      setMonthlyStats(monthly || {
        present_days: 0,
        days_met_min_hours: 0,
        total_hours: 0,
        attendance_percentage: 0,
        total_days_in_month: 30,
        estimated_working_days: 22,
        absent_days: 0,
        late_days: 0,
        on_time_days: 0,
        overtime_hours: 0,
        average_hours_per_day: 0,
        compliance_rate: 0,
      });
      setUpcomingHoliday(upcoming || null);
      setLeaveStats(leaveStatsData || { total: 0, pending: 0, approved: 0, rejected: 0 });
      setPendingLeaves(leaveStatsData?.pending || 0);
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return '--';
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return '--';
    }
  };

  const getWeeklyTrend = () => {
    const presentDays = monthlyStats.present_days || 0;
    const workingDays = monthlyStats.estimated_working_days || 22;
    const percentage = (presentDays / workingDays) * 100;
    return [percentage * 0.8, percentage * 0.9, percentage * 1.0, percentage * 0.95];
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="Dashboard" 
        role="user" 
        label="Employee" 
        abbr="EM" 
        color="#f59e0b" 
        bgColor="rgba(245,158,11,0.15)"
      >
        <div className="card-box" style={{ textAlign: 'center', padding: '4rem' }}>
          <p>Loading dashboard data...</p>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout 
        title="Dashboard" 
        role="user" 
        label="Employee" 
        abbr="EM" 
        color="#f59e0b" 
        bgColor="rgba(245,158,11,0.15)"
      >
        <div className="card-box" style={{ textAlign: 'center', padding: '4rem' }}>
          <p style={{ color: 'var(--red)' }}>Error: {error}</p>
          <button className="btn btn-teal" onClick={fetchAllData} style={{ marginTop: '1rem' }}>
            Retry
          </button>
        </div>
      </DashboardLayout>
    );
  }

  const weeklyTrend = getWeeklyTrend();

  return (
    <DashboardLayout 
      title="Dashboard" 
      role="user" 
      label="Employee" 
      abbr={dashboardData.name ? dashboardData.name.charAt(0).toUpperCase() : 'EM'} 
      color="#f59e0b" 
      bgColor="rgba(245,158,11,0.15)"
    >
      {/* Settings Banner */}
      {settings && (
        <div style={{ 
          marginBottom: '1rem', 
          padding: '0.5rem 1rem', 
          background: 'rgba(245,158,11,0.1)', 
          borderRadius: '10px',
          fontSize: '0.7rem',
          textAlign: 'center',
          display: 'flex',
          justifyContent: 'center',
          gap: '1.5rem',
          flexWrap: 'wrap'
        }}>
          <span>🕘 Office Hours: {settings.office_start_time?.slice(0,5)} - {settings.office_end_time?.slice(0,5)}</span>
          <span>⚠️ Late after: +{settings.late_threshold_minutes} min</span>
          <span>⏱️ Min hours required: {settings.min_working_hours}h</span>
        </div>
      )}

      {/* Top Presence Card */}
      <div className="today-card">
        <div className="today-item">
          <div className="today-val">{todayAttendance.status === 'present' ? 'Present' : 'Absent'}</div>
          <div className="today-lbl">Today Status</div>
        </div>
        <div className="today-item">
          <div className="today-val">{formatTime(todayAttendance.check_in)}</div>
          <div className="today-lbl">Check-in</div>
          {todayAttendance.is_late && todayAttendance.check_in && (
            <div className="today-lbl" style={{ color: 'var(--amber)', fontSize: '0.6rem' }}>(Late)</div>
          )}
        </div>
        <div className="today-item">
          <div className="today-val">{formatTime(todayAttendance.check_out)}</div>
          <div className="today-lbl">Check-out</div>
        </div>
        <div className="today-item">
          <div className="today-val" style={{ color: todayAttendance.met_min_hours ? 'var(--green)' : 'var(--amber)' }}>
            {todayAttendance.hours_worked > 0 ? `${todayAttendance.hours_worked}h` : '--'}
          </div>
          <div className="today-lbl">Valid Hours</div>
          {todayAttendance.check_in && (
            <div className="today-lbl" style={{ fontSize: '0.6rem' }}>
              {todayAttendance.met_min_hours ? '✓ Met requirement' : '✗ Below minimum'}
            </div>
          )}
        </div>
      </div>

      {/* Main Stats Row */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
        <div className="stat-card">
          <div className="stat-label">Monthly Attendance</div>
          <div className="stat-value" style={{ color: 'var(--teal)', fontSize: '1.4rem' }}>
            {monthlyStats.attendance_percentage || 0}%
          </div>
          <div className="stat-sub">
            {monthlyStats.present_days || 0}/{monthlyStats.estimated_working_days || 22} days
          </div>
        </div>
        
        <div className="stat-card">
          <div className="stat-label">Days Met Min Hours</div>
          <div className="stat-value" style={{ color: 'var(--purple)', fontSize: '1.4rem' }}>
            {monthlyStats.days_met_min_hours || 0}
          </div>
          <div className="stat-sub">
            {monthlyStats.compliance_rate || 0}% compliance rate
          </div>
        </div>
        
        <div className="stat-card">
          <div className="stat-label">Present Days</div>
          <div className="stat-value" style={{ color: 'var(--green)', fontSize: '1.4rem' }}>
            {dashboardData.present_days || monthlyStats.present_days || 0}
          </div>
          <div className="stat-sub">This month</div>
        </div>
        
        <div className="stat-card">
          <div className="stat-label">Total Valid Hours</div>
          <div className="stat-value" style={{ color: 'var(--amber)', fontSize: '1.4rem' }}>
            {monthlyStats.total_hours || 0}h
          </div>
          <div className="stat-sub">Within office hours</div>
        </div>
        
        <div className="stat-card">
          <div className="stat-label">Pending Leaves</div>
          <div className="stat-value" style={{ color: 'var(--blue)', fontSize: '1.4rem' }}>
            {pendingLeaves}
          </div>
          <div className="stat-sub">{leaveStats.total || 0} total requests</div>
        </div>
      </div>

      {/* Additional Stats Row */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginTop: '0' }}>
        <div className="stat-card">
          <div className="stat-label">Late Days</div>
          <div className="stat-value" style={{ color: 'var(--amber)', fontSize: '1.2rem' }}>
            {monthlyStats.late_days || 0}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">On Time</div>
          <div className="stat-value" style={{ color: 'var(--green)', fontSize: '1.2rem' }}>
            {monthlyStats.on_time_days || 0}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Average Hours/Day</div>
          <div className="stat-value" style={{ color: 'var(--teal)', fontSize: '1.2rem' }}>
            {monthlyStats.average_hours_per_day || 0}h
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Absent Days</div>
          <div className="stat-value" style={{ color: 'var(--red)', fontSize: '1.2rem' }}>
            {monthlyStats.absent_days || 0}
          </div>
        </div>
      </div>

      {/* Charts and Info Row */}
      <div className="two-col" style={{ marginTop: '1.5rem' }}>
        <div className="card-box">
          <h4>Attendance trend (this month)</h4>
          <TrendChart 
            labels={['Week 1', 'Week 2', 'Week 3', 'Week 4']} 
            vals={weeklyTrend} 
            color="var(--amber)" 
          />
          <div style={{ marginTop: '1rem', fontSize: '0.75rem', color: 'var(--text3)', textAlign: 'center' }}>
            Based on {monthlyStats.present_days || 0} present days out of {monthlyStats.estimated_working_days || 22} working days
          </div>
        </div>
        
        <div className="card-box">
          <h4>Quick info</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="stat-label" style={{ margin: 0 }}>Upcoming holiday</span>
              <span style={{ fontSize: '0.85rem', fontFamily: 'var(--mono)' }}>
                {upcomingHoliday ? `${upcomingHoliday.name || upcomingHoliday.holiday_name} - ${new Date(upcomingHoliday.holiday_date || upcomingHoliday.date).toLocaleDateString()}` : 'None'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="stat-label" style={{ margin: 0 }}>Pending leaves</span>
              <span className="badge pending">{pendingLeaves} pending</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="stat-label" style={{ margin: 0 }}>Last check-in</span>
              <span style={{ fontSize: '0.85rem', fontFamily: 'var(--mono)' }}>
                {formatTime(todayAttendance.check_in)}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="stat-label" style={{ margin: 0 }}>Today's valid hours</span>
              <span style={{ fontSize: '0.85rem', fontFamily: 'var(--mono)', color: todayAttendance.met_min_hours ? 'var(--green)' : 'var(--amber)' }}>
                {todayAttendance.hours_worked || 0}h
                {todayAttendance.check_in && !todayAttendance.met_min_hours && (
                  <span style={{ fontSize: '0.7rem', marginLeft: '4px' }}>(below {settings?.min_working_hours}h)</span>
                )}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Info Card */}
      <div className="card-box" style={{ marginTop: '1rem', background: 'rgba(245,158,11,0.03)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <span style={{ fontSize: '1.2rem' }}>ℹ️</span>
          <span style={{ fontWeight: 500, fontSize: '0.85rem' }}>About Working Hours Calculation</span>
        </div>
        <p style={{ fontSize: '0.7rem', color: 'var(--text3)', lineHeight: 1.5 }}>
          Working hours are calculated based on actual time spent within office hours 
          ({settings?.office_start_time?.slice(0,5)} - {settings?.office_end_time?.slice(0,5)}). 
          Time before office start or after office end is not counted. 
          You need at least <strong>{settings?.min_working_hours || 9} hours</strong> of valid working hours per day to meet the requirement.
        </p>
      </div>
    </DashboardLayout>
  );
};

export default Dashboard;