// src/pages/org/Devices.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import { orgApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { RefreshCw, AlertCircle, Cpu, Wifi, WifiOff, Clock, Activity, Server } from 'lucide-react';

const Devices = () => {
  const { logout } = useAuth();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [stats, setStats] = useState({ total: 0, online: 0, offline: 0 });

  useEffect(() => {
    fetchDevices();
    fetchDeviceStatus();
  }, []);

  const fetchDevices = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await orgApi.getDevices();
      setDevices(data || []);
    } catch (err) {
      if (err?.response?.status === 401) logout();
      setError("Failed to load devices");
    } finally {
      setLoading(false);
    }
  };

  const fetchDeviceStatus = async () => {
    try {
      const data = await orgApi.getDeviceStatus();
      setStats(data || { total: 0, online: 0, offline: 0 });
    } catch (err) {
      console.error("Device status fetch error:", err);
    }
  };

  const formatLastSeen = (timestamp) => {
    if (!timestamp) return "Never";
    const diff = (new Date() - new Date(timestamp)) / 1000 / 60;
    if (diff < 1) return "Just now";
    if (diff < 60) return `${Math.floor(diff)} min ago`;
    if (diff < 1440) return `${Math.floor(diff / 60)} hrs ago`;
    return new Date(timestamp).toLocaleDateString();
  };

  const onlinePercent = stats.total > 0 ? ((stats.online / stats.total) * 100).toFixed(0) : 0;

  return (
    <DashboardLayout title="Devices" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      <style>{`
        .device-card { transition: all 0.2s; cursor: pointer; }
        .device-card:hover { transform: translateY(-2px); border-color: var(--teal); }
      `}</style>

      <div className="stats-grid">
        <div className="stat-card purple"><div className="stat-label"><Server size={14} /> Total Devices</div><div className="stat-value">{stats.total}</div><div className="stat-sub">Registered devices</div></div>
        <div className="stat-card green"><div className="stat-label"><Wifi size={14} /> Online</div><div className="stat-value">{stats.online}</div><div className="stat-sub">{onlinePercent}% of total</div></div>
        <div className="stat-card red"><div className="stat-label"><WifiOff size={14} /> Offline</div><div className="stat-value">{stats.offline}</div><div className="stat-sub">Needs attention</div></div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
        <button className="btn btn-ghost" onClick={() => { fetchDevices(); fetchDeviceStatus(); }}><RefreshCw size={16} /> Refresh</button>
      </div>

      {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '12px', padding: '12px 16px', marginBottom: '1rem', color: '#f87171', display: 'flex', alignItems: 'center', gap: '8px' }}><AlertCircle size={16} /> {error}</div>}

      {loading ? (
        <div className="skeleton-loader" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
          {[1,2,3].map(i => <div key={i} style={{ background: 'var(--bg2)', borderRadius: '16px', height: '160px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>)}
        </div>
      ) : devices.length === 0 ? (
        <div className="card-box" style={{ textAlign: 'center', padding: '4rem' }}><Cpu size={48} style={{ color: 'var(--text3)', marginBottom: '1rem' }} /><p style={{ color: 'var(--text3)' }}>No devices found</p></div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
          {devices.map(device => (
            <div key={device.device_id || device.id} className="device-card" style={{ background: 'var(--bg2)', border: `1px solid ${device.status === 'online' ? 'rgba(34,197,94,0.3)' : 'var(--border)'}`, borderRadius: '16px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ width: '44px', height: '44px', borderRadius: '12px', background: device.status === 'online' ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {device.status === 'online' ? <Wifi size={22} style={{ color: '#22c55e' }} /> : <WifiOff size={22} style={{ color: '#ef4444' }} />}
                  </div>
                  <div><div style={{ fontWeight: 600, fontSize: '1rem' }}>{device.device_id || device.id}</div><div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>Biometric Scanner</div></div>
                </div>
                <Badge type={device.status === 'online' ? 'online' : 'offline'}>{device.status === 'online' ? 'Online' : 'Offline'}</Badge>
              </div>
              <div style={{ padding: '0.75rem 0', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Clock size={14} style={{ color: 'var(--text3)' }} />
                <span style={{ fontSize: '0.75rem', color: 'var(--text3)' }}>Last seen: {formatLastSeen(device.last_seen)}</span>
                {device.status === 'online' && <Activity size={14} style={{ color: '#22c55e', marginLeft: 'auto' }} />}
              </div>
              <button className="btn btn-ghost" style={{ width: '100%', fontSize: '0.75rem' }}>View Details →</button>
            </div>
          ))}
        </div>
      )}
    </DashboardLayout>
  );
};

export default Devices;