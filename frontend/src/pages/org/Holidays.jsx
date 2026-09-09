// src/pages/org/Holidays.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { orgApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { RefreshCw, AlertCircle, Calendar, Gift, ChevronRight } from 'lucide-react';

const Holidays = () => {
  const { logout } = useAuth();
  const [holidays, setHolidays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => { fetchHolidays(); }, []);

  const fetchHolidays = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await orgApi.getHolidays();
      setHolidays(data || []);
    } catch (err) {
      if (err?.response?.status === 401) logout();
      setError("Failed to load holidays");
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
  };

  const getDay = (dateStr) => {
    if (!dateStr) return "";
    return new Date(dateStr).toLocaleDateString('en-US', { weekday: 'long' });
  };

  const upcomingHolidays = holidays.filter(h => new Date(h.holiday_date || h.date) >= new Date()).slice(0, 3);
  const pastHolidays = holidays.filter(h => new Date(h.holiday_date || h.date) < new Date());

  if (loading) {
    return (
      <DashboardLayout title="Holidays" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
        <div className="skeleton-loader">{/* Loading skeleton */}</div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Holidays" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      <style>{`
        .holiday-card { transition: all 0.2s; }
        .holiday-card:hover { transform: translateY(-2px); border-color: var(--teal); }
      `}</style>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
        <button className="btn btn-ghost" onClick={fetchHolidays}><RefreshCw size={16} /> Refresh</button>
      </div>

      {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '12px', padding: '12px 16px', marginBottom: '1rem', color: '#f87171', display: 'flex', alignItems: 'center', gap: '8px' }}><AlertCircle size={16} /> {error}</div>}

      {upcomingHolidays.length > 0 && (
        <div className="card-box" style={{ marginBottom: '1.5rem', background: 'linear-gradient(135deg, rgba(0,212,170,0.05), transparent)' }}>
          <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem' }}><Gift size={18} /> Upcoming Holidays</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem' }}>
            {upcomingHolidays.map(h => (
              <div key={h.holiday_id || h.id} className="holiday-card" style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: '12px', padding: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div><div style={{ fontWeight: 600 }}>{h.name || h.holiday_name}</div><div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>{formatDate(h.holiday_date || h.date)} · {getDay(h.holiday_date || h.date)}</div></div>
                <ChevronRight size={16} style={{ color: 'var(--text3)' }} />
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="table-wrap">
        <div className="table-header"><span className="table-title"><Calendar size={16} /> All Holidays ({new Date().getFullYear()})</span></div>
        {holidays.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>No holidays found for this year</div>
        ) : (
          <table style={{ width: '100%' }}>
            <thead>
              <tr><th>Holiday</th><th>Date</th><th>Day</th><th>Description</th></tr>
            </thead>
            <tbody>
              {holidays.map(h => (
                <tr key={h.holiday_id || h.id}>
                  <td style={{ fontWeight: 500 }}>{h.name || h.holiday_name}</td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>{formatDate(h.holiday_date || h.date)}</td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>{getDay(h.holiday_date || h.date)}</td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--text2)' }}>{h.description || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </DashboardLayout>
  );
};

export default Holidays;