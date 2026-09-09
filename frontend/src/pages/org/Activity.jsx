// src/pages/org/Activity.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { orgApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { RefreshCw, AlertCircle, Activity as ActivityIcon, User, Clock, Calendar, Filter } from 'lucide-react';

const Activity = () => {
  const { logout } = useAuth();
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");

  useEffect(() => { fetchActivities(); }, []);

  const fetchActivities = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await orgApi.getActivityLog();
      setActivities(data || []);
    } catch (err) {
      if (err?.response?.status === 401) logout();
      setError("Failed to load activity log");
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hr ago`;
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  };

  const getActivityIcon = (type) => {
    if (type?.includes('leave')) return '📋';
    if (type?.includes('attendance')) return '⏰';
    if (type?.includes('employee')) return '👥';
    return '🔔';
  };

  const filteredActivities = filter === "all" ? activities : activities.filter(a => a.event_type === filter);

  if (loading) {
    return (
      <DashboardLayout title="Activity Log" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
        <div className="skeleton-loader">{/* Loading skeleton */}</div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Activity Log" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      <style>{`
        .activity-timeline { position: relative; padding-left: 24px; }
        .activity-timeline::before { content: ''; position: absolute; left: 8px; top: 0; bottom: 0; width: 2px; background: linear-gradient(to bottom, var(--teal), var(--purple), transparent); }
        .activity-item { position: relative; margin-bottom: 1rem; padding: 0.75rem; background: var(--bg2); border-radius: 12px; border: 1px solid var(--border); transition: all 0.2s; }
        .activity-item:hover { transform: translateX(4px); border-color: var(--teal); }
        .activity-item::before { content: ''; position: absolute; left: -20px; top: 18px; width: 8px; height: 8px; border-radius: 50%; background: var(--teal); box-shadow: 0 0 0 3px rgba(0,212,170,0.2); }
      `}</style>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}><ActivityIcon size={20} /> Department Activity Feed</h3>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <Filter size={14} style={{ color: 'var(--text3)' }} />
          <select className="form-select" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: '140px', padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}>
            <option value="all">All Activity</option>
            <option value="leave">Leaves</option>
            <option value="attendance">Attendance</option>
            <option value="employee">Employees</option>
          </select>
          <button className="btn btn-ghost" onClick={fetchActivities} style={{ padding: '0.4rem 0.8rem' }}><RefreshCw size={14} /> Refresh</button>
        </div>
      </div>

      {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '12px', padding: '12px 16px', marginBottom: '1rem', color: '#f87171', display: 'flex', alignItems: 'center', gap: '8px' }}><AlertCircle size={16} /> {error}</div>}

      <div className="activity-timeline">
        {filteredActivities.length === 0 ? (
          <div className="card-box" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>No activity found</div>
        ) : (
          filteredActivities.map((a, idx) => (
            <div key={idx} className="activity-item">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '1.2rem' }}>{getActivityIcon(a.event_type)}</span>
                  <div>
                    <div style={{ fontWeight: 500, fontSize: '0.9rem' }}>{a.title || a.message || a.event_type?.replace('_', ' ') || 'Activity'}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text3)', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                      <User size={10} /> {a.actor_name || a.actor || 'System'}
                    </div>
                  </div>
                </div>
                <div style={{ fontSize: '0.7rem', fontFamily: 'var(--mono)', color: 'var(--text3)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={10} /> {formatTime(a.created_at || a.timestamp)}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </DashboardLayout>
  );
};

export default Activity;