// src/pages/tenant/Settings.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { Save, AlertCircle, CheckCircle, Clock, Calendar, AlertTriangle, RefreshCw, Briefcase } from 'lucide-react';

const TenantSettings = () => {
  const { logout } = useAuth();
  const [settings, setSettings] = useState({
    office_start_time: '09:00:00',
    office_end_time: '18:00:00',
    late_threshold_minutes: 15,
    working_days: '1,2,3,4,5',
    min_working_hours: 9.0
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const data = await tenantApi.getSettings();
      console.log("Fetched tenant settings:", data);
      if (data) {
        setSettings({
          office_start_time: data.office_start_time || '09:00:00',
          office_end_time: data.office_end_time || '18:00:00',
          late_threshold_minutes: data.late_threshold_minutes ?? 15,
          working_days: data.working_days || '1,2,3,4,5',
          min_working_hours: data.min_working_hours ?? 9.0
        });
      }
    } catch (err) {
      console.error('Failed to fetch settings:', err);
      if (err?.response?.status === 401) logout();
      setMessage({ type: 'error', text: 'Failed to load settings. Using defaults.' });
      setTimeout(() => setMessage(null), 3000);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    
    const payload = {
      office_start_time: settings.office_start_time,
      office_end_time: settings.office_end_time,
      late_threshold_minutes: Number(settings.late_threshold_minutes),
      working_days: settings.working_days,
      min_working_hours: Number(settings.min_working_hours)
    };
    
    console.log("Sending payload to backend:", payload);
    
    try {
      await tenantApi.updateSettings(payload);
      setMessage({ type: 'success', text: 'Organization settings saved successfully!' });
      setTimeout(() => setMessage(null), 3000);
      await fetchSettings();
    } catch (err) {
      console.error('Failed to save settings:', err);
      setMessage({ type: 'error', text: err.message || 'Failed to save settings' });
      setTimeout(() => setMessage(null), 3000);
    } finally {
      setSaving(false);
    }
  };

  // Format time for display (remove seconds for input field)
  const formatTimeForInput = (timeStr) => {
    if (!timeStr) return '09:00';
    return timeStr.slice(0, 5);
  };

  // Format time with seconds for storage
  const formatTimeWithSeconds = (timeStr) => {
    if (!timeStr) return '09:00:00';
    if (timeStr.length === 8) return timeStr;
    return `${timeStr}:00`;
  };

  // Get working days display
  const getWorkingDaysDisplay = () => {
    const dayMap = {
      1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat', 7: 'Sun'
    };
    const days = settings.working_days.split(',').map(d => d.trim());
    return days.map(d => dayMap[d]).join(', ');
  };

  if (loading) {
    return (
      <DashboardLayout
        title="Organization Settings"
        role="superadmin"
        label="Tenant Admin"
        abbr="TA"
        color="#a855f7"
        bgColor="rgba(168,85,247,0.15)"
      >
        <div style={{ maxWidth: '560px', margin: '0 auto' }}>
          <div style={{ background: 'var(--bg2)', borderRadius: '16px', height: '500px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>
        </div>
        <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }`}</style>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      title="Organization Settings"
      role="superadmin"
      label="Tenant Admin"
      abbr="TA"
      color="#a855f7"
      bgColor="rgba(168,85,247,0.15)"
    >
      <style>{`
        .settings-card { max-width: 560px; margin: 0 auto; }
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        .info-box {
          background: rgba(168,85,247,0.05);
          border: 1px solid rgba(168,85,247,0.15);
          border-radius: 12px;
          padding: 1rem;
          margin-top: 1rem;
        }
      `}</style>

      {message && (
        <div style={{ position: 'fixed', bottom: '24px', right: '24px', zIndex: 1000, animation: 'slideIn 0.3s ease' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            background: message.type === 'success' ? 'rgba(34,197,94,0.95)' : 'rgba(239,68,68,0.95)',
            padding: '12px 20px',
            borderRadius: '12px',
            color: 'white'
          }}>
            {message.type === 'success' ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
            {message.text}
          </div>
        </div>
      )}

      <div className="card-box settings-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
          <h4 style={{ margin: 0 }}>Organization Settings</h4>
          <button className="btn btn-ghost" onClick={fetchSettings} style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
            <RefreshCw size={14} style={{ marginRight: '4px' }} /> Refresh
          </button>
        </div>
        <p style={{ color: 'var(--text3)', fontSize: '0.8rem', marginBottom: '1.5rem' }}>
          Configure attendance rules and working hours for your entire organization. These settings apply to all departments.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Office Start Time */}
          <div className="form-group">
            <label className="form-label">
              <Clock size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'middle' }} />
              Office Start Time
            </label>
            <input
              className="form-input"
              type="time"
              value={formatTimeForInput(settings.office_start_time)}
              onChange={(e) => setSettings({ 
                ...settings, 
                office_start_time: formatTimeWithSeconds(e.target.value)
              })}
            />
            <p style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '4px' }}>
              Employees are expected to check-in by this time
            </p>
          </div>

          {/* Office End Time */}
          <div className="form-group">
            <label className="form-label">
              <Clock size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'middle' }} />
              Office End Time
            </label>
            <input
              className="form-input"
              type="time"
              value={formatTimeForInput(settings.office_end_time)}
              onChange={(e) => setSettings({ 
                ...settings, 
                office_end_time: formatTimeWithSeconds(e.target.value)
              })}
            />
            <p style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '4px' }}>
              Standard end of working day
            </p>
          </div>

          {/* Late Threshold */}
          <div className="form-group">
            <label className="form-label">
              <AlertTriangle size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'middle' }} />
              Late Threshold (minutes)
            </label>
            <input
              className="form-input"
              type="number"
              min="0"
              max="120"
              value={settings.late_threshold_minutes}
              onChange={(e) => setSettings({ 
                ...settings, 
                late_threshold_minutes: parseInt(e.target.value) || 0 
              })}
            />
            <p style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '4px' }}>
              Employees arriving after this many minutes past start time are marked late
            </p>
          </div>

          {/* Minimum Working Hours - NEW */}
          <div className="form-group">
            <label className="form-label">
              <Briefcase size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'middle' }} />
              Minimum Working Hours (per day)
            </label>
            <input
              className="form-input"
              type="number"
              min="0.5"
              max="24"
              step="0.5"
              value={settings.min_working_hours}
              onChange={(e) => setSettings({ 
                ...settings, 
                min_working_hours: parseFloat(e.target.value) 
              })}
            />
            <p style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '4px' }}>
              Employees must work at least this many hours to be marked as compliant
            </p>
          </div>

          {/* Working Days */}
          <div className="form-group">
            <label className="form-label">
              <Calendar size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'middle' }} />
              Working Days
            </label>
            <input
              className="form-input"
              placeholder="e.g., 1,2,3,4,5"
              value={settings.working_days}
              onChange={(e) => setSettings({ ...settings, working_days: e.target.value })}
            />
            <p style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '4px' }}>
              1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat, 7=Sun<br />
              Current: {getWorkingDaysDisplay()}
            </p>
          </div>
        </div>

        {/* Preview Section */}
        <div className="info-box">
          <div style={{ fontWeight: 500, marginBottom: '0.75rem', color: 'var(--text)', fontSize: '0.85rem' }}>
            Current Configuration Preview
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', fontSize: '0.8rem' }}>
            <div>🕘 Start: <strong>{settings.office_start_time?.slice(0, 5)}</strong></div>
            <div>🕕 End: <strong>{settings.office_end_time?.slice(0, 5)}</strong></div>
            <div>⚠️ Late after: <strong>{settings.late_threshold_minutes} min</strong></div>
            <div>⏱️ Min hours: <strong>{settings.min_working_hours} hours</strong></div>
            <div>📅 Work days: <strong>{getWorkingDaysDisplay()}</strong></div>
          </div>
          <div style={{ 
            marginTop: '0.75rem', 
            paddingTop: '0.75rem', 
            borderTop: '1px solid rgba(168,85,247,0.15)',
            fontSize: '0.7rem',
            color: 'var(--text3)'
          }}>
            <AlertCircle size={12} style={{ display: 'inline', marginRight: '4px' }} />
            These rules apply to attendance calculations across all departments
          </div>
        </div>

        {/* Save Button */}
        <div style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid var(--border)' }}>
          <button
            className="btn btn-teal"
            onClick={handleSave}
            disabled={saving}
            style={{ width: '100%', padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
          >
            <Save size={16} /> {saving ? 'Saving...' : 'Save Organization Settings'}
          </button>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default TenantSettings;