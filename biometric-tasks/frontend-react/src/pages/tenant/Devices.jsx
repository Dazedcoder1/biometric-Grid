// src/pages/tenant/Devices.jsx
import React, { useState, useEffect } from 'react';
import { 
  Cpu, 
  Wifi, 
  WifiOff, 
  RefreshCw, 
  AlertCircle, 
  Clock, 
  Search, 
  ChevronRight,
  Plus,
  Edit2,
  Trash2,
  X,
  Key,
  Hash,
  Activity,
  Server,
  CheckCircle,
  AlertTriangle,
  Power,
  PowerOff
} from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import ConfirmationModal from '../../components/ConfirmationModal';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

// Premium Device Detail Modal
const DeviceDetailModal = ({ device, onClose }) => {
  const [recentCommands, setRecentCommands] = useState([]);
  const [loading, setLoading] = useState(false);
  const { logout } = useAuth();

  useEffect(() => {
    if (device) {
      fetchDeviceDetails();
    }
  }, [device]);

  const fetchDeviceDetails = async () => {
    setLoading(true);
    try {
      const data = await tenantApi.getDeviceDetails(device.device_id);
      setRecentCommands(data.recent_commands || []);
    } catch (err) {
      console.error("Failed to fetch device details:", err);
      if (err?.response?.status === 401) logout();
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return 'Never';
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const getCommandStatusColor = (status) => {
    if (!status) return 'pending';
    if (status === 'SUCCESS') return 'active';
    if (status === 'FAILED') return 'rejected';
    return 'pending';
  };

  if (!device) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="device-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose}>
          <X size={20} />
        </button>
        
        <div className="modal-header">
          <div className={`modal-icon ${device.status === 'online' ? 'online' : 'offline'}`}>
            {device.status === 'online' ? <Wifi size={28} /> : <WifiOff size={28} />}
          </div>
          <div className="modal-title-section">
            <h3>{device.device_id}</h3>
            <p>ID: {device.id}</p>
          </div>
          <Badge type={device.status === 'online' ? 'online' : 'offline'}>
            {device.status === 'online' ? 'Online' : 'Offline'}
          </Badge>
        </div>
        
        <div className="modal-body">
          <div className="info-grid">
            <div className="info-item">
              <div className="info-label"><Server size={14} /> Device ID</div>
              <div className="info-value">{device.device_id}</div>
            </div>
            <div className="info-item">
              <div className="info-label"><Key size={14} /> Secret Key</div>
              <div className="info-value" style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>
                {device.secret_key ? '••••••••' : 'Not set'}
              </div>
            </div>
            <div className="info-item">
              <div className="info-label"><Clock size={14} /> Last Seen</div>
              <div className="info-value">{formatTime(device.last_seen)}</div>
            </div>
            <div className="info-item">
              <div className="info-label"><Activity size={14} /> Status</div>
              <div className="info-value">
                {device.status === 'online' ? (
                  <span style={{ color: '#22c55e', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <CheckCircle size={14} /> Active and connected
                  </span>
                ) : (
                  <span style={{ color: '#f87171', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <AlertTriangle size={14} /> Not responding
                  </span>
                )}
              </div>
            </div>
          </div>

          {recentCommands.length > 0 && (
            <div className="commands-section">
              <h4>Recent Commands</h4>
              <div className="commands-list">
                {recentCommands.map((cmd, idx) => (
                  <div key={idx} className="command-item">
                    <div className="command-details">
                      <span className="command-name">{cmd.command}</span>
                      {cmd.target_id && <span className="command-target">Target: {cmd.target_id}</span>}
                    </div>
                    <div className="command-status">
                      <Badge type={getCommandStatusColor(cmd.status)}>
                        {cmd.status || 'PENDING'}
                      </Badge>
                      <span className="command-time">{formatTime(cmd.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {loading && (
            <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--text3)' }}>
              Loading commands...
            </div>
          )}
        </div>
        
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
      
      <style>{`
        .device-modal {
          background: var(--bg2);
          border: 1px solid var(--border);
          border-radius: 24px;
          max-width: 550px;
          width: 90%;
          position: relative;
          animation: modalSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          overflow: hidden;
        }
        @keyframes modalSlideIn {
          from { opacity: 0; transform: scale(0.95) translateY(-10px); }
          to { opacity: 1; transform: scale(1) translateY(0); }
        }
        .modal-close-btn {
          position: absolute;
          top: 16px;
          right: 16px;
          background: var(--bg3);
          border: none;
          color: var(--text2);
          cursor: pointer;
          padding: 6px;
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
          z-index: 10;
        }
        .modal-close-btn:hover {
          background: var(--bg4);
          color: var(--text);
        }
        .modal-header {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 24px 24px 20px 24px;
          border-bottom: 1px solid var(--border);
          background: linear-gradient(135deg, var(--bg2), var(--bg3));
        }
        .modal-icon {
          width: 56px;
          height: 56px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .modal-icon.online {
          background: rgba(34,197,94,0.1);
          color: #22c55e;
        }
        .modal-icon.offline {
          background: rgba(239,68,68,0.1);
          color: #f87171;
        }
        .modal-title-section h3 {
          font-size: 1.2rem;
          font-weight: 600;
          margin-bottom: 4px;
        }
        .modal-title-section p {
          font-size: 0.75rem;
          color: var(--text3);
          font-family: var(--mono);
        }
        .modal-body {
          padding: 20px 24px;
          max-height: 500px;
          overflow-y: auto;
        }
        .info-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
          margin-bottom: 20px;
        }
        .info-item {
          background: var(--bg3);
          border-radius: 12px;
          padding: 12px;
        }
        .info-label {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.7rem;
          color: var(--text3);
          font-family: var(--mono);
          margin-bottom: 8px;
        }
        .info-value {
          font-size: 0.9rem;
          font-weight: 500;
          color: var(--text);
        }
        .commands-section h4 {
          font-size: 0.9rem;
          font-weight: 600;
          margin-bottom: 12px;
          padding-bottom: 8px;
          border-bottom: 1px solid var(--border);
        }
        .commands-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .command-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 10px;
          background: var(--bg3);
          border-radius: 10px;
          flex-wrap: wrap;
          gap: 8px;
        }
        .command-details {
          display: flex;
          gap: 12px;
          align-items: center;
        }
        .command-name {
          font-family: var(--mono);
          font-size: 0.8rem;
          font-weight: 500;
          text-transform: uppercase;
        }
        .command-target {
          font-size: 0.7rem;
          color: var(--text3);
        }
        .command-status {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .command-time {
          font-size: 0.65rem;
          color: var(--text3);
          font-family: var(--mono);
        }
        .modal-footer {
          padding: 16px 24px 24px 24px;
          border-top: 1px solid var(--border);
          display: flex;
          justify-content: flex-end;
        }
      `}</style>
    </div>
  );
};

// Add Device Modal
const AddDeviceModal = ({ isOpen, onClose, onSuccess }) => {
  const [formData, setFormData] = useState({ device_id: '', secret_key: '' });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const { logout } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    
    if (!formData.device_id.trim()) {
      setError('Device ID is required');
      setSubmitting(false);
      return;
    }
    if (!formData.secret_key.trim() || formData.secret_key.length < 8) {
      setError('Secret key must be at least 8 characters');
      setSubmitting(false);
      return;
    }
    
    try {
      await tenantApi.createDevice(formData);
      setFormData({ device_id: '', secret_key: '' });
      onSuccess();
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to add device');
      if (err?.response?.status === 401) logout();
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="add-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose}>
          <X size={20} />
        </button>
        
        <div className="add-modal-header">
          <div className="add-modal-icon">
            <Cpu size={28} />
          </div>
          <h3>Add New Device</h3>
          <p>Register a biometric device to your organization</p>
        </div>
        
        <form onSubmit={handleSubmit}>
          <div className="add-modal-body">
            {error && (
              <div className="error-message">
                <AlertCircle size={16} /> {error}
              </div>
            )}
            
            <div className="form-group">
              <label className="form-label"><Hash size={14} /> Device ID *</label>
              <input 
                className="form-input" 
                placeholder="e.g., FP-001, DEVICE-01"
                value={formData.device_id}
                onChange={(e) => setFormData({ ...formData, device_id: e.target.value })}
                required
              />
              <p className="form-hint">Unique identifier for this device</p>
            </div>
            
            <div className="form-group">
              <label className="form-label"><Key size={14} /> Secret Key *</label>
              <input 
                type="text" 
                className="form-input" 
                placeholder="Minimum 8 characters"
                value={formData.secret_key}
                onChange={(e) => setFormData({ ...formData, secret_key: e.target.value })}
                required
                minLength={8}
              />
              <p className="form-hint">Secret key for device authentication (min 8 chars)</p>
            </div>
          </div>
          
          <div className="add-modal-footer">
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-teal" disabled={submitting}>
              {submitting ? 'Adding...' : 'Add Device'}
            </button>
          </div>
        </form>
      </div>
      
      <style>{`
        .add-modal {
          background: var(--bg2);
          border: 1px solid var(--border);
          border-radius: 24px;
          max-width: 450px;
          width: 90%;
          position: relative;
          animation: modalSlideIn 0.3s ease;
        }
        .add-modal-header {
          text-align: center;
          padding: 24px 24px 16px 24px;
          border-bottom: 1px solid var(--border);
        }
        .add-modal-icon {
          width: 56px;
          height: 56px;
          background: rgba(168,85,247,0.1);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 12px;
          color: #a855f7;
        }
        .add-modal-header h3 {
          font-size: 1.3rem;
          font-weight: 600;
          margin-bottom: 4px;
        }
        .add-modal-header p {
          font-size: 0.8rem;
          color: var(--text3);
        }
        .add-modal-body {
          padding: 20px 24px;
        }
        .error-message {
          background: rgba(239,68,68,0.1);
          border: 1px solid rgba(239,68,68,0.3);
          border-radius: 10px;
          padding: 10px 12px;
          margin-bottom: 16px;
          color: #f87171;
          font-size: 0.85rem;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .form-hint {
          font-size: 0.7rem;
          color: var(--text3);
          margin-top: 4px;
        }
        .add-modal-footer {
          padding: 16px 24px 24px 24px;
          border-top: 1px solid var(--border);
          display: flex;
          gap: 12px;
          justify-content: flex-end;
        }
      `}</style>
    </div>
  );
};

// Edit Device Modal
const EditDeviceModal = ({ isOpen, onClose, device, onSuccess }) => {
  const [formData, setFormData] = useState({ device_id: '', secret_key: '' });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const { logout } = useAuth();

  useEffect(() => {
    if (device) {
      setFormData({
        device_id: device.device_id || '',
        secret_key: ''
      });
    }
  }, [device]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    
    const updateData = {};
    if (formData.device_id && formData.device_id !== device.device_id) {
      updateData.device_id = formData.device_id;
    }
    if (formData.secret_key && formData.secret_key.length >= 8) {
      updateData.secret_key = formData.secret_key;
    }
    
    if (Object.keys(updateData).length === 0) {
      setError('No changes to update');
      setSubmitting(false);
      return;
    }
    
    try {
      await tenantApi.updateDevice(device.device_id, updateData);
      onSuccess();
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to update device');
      if (err?.response?.status === 401) logout();
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen || !device) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="edit-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose}>
          <X size={20} />
        </button>
        
        <div className="edit-modal-header">
          <div className="edit-modal-icon">
            <Edit2 size={28} />
          </div>
          <h3>Edit Device</h3>
          <p>Update device information</p>
        </div>
        
        <form onSubmit={handleSubmit}>
          <div className="edit-modal-body">
            {error && (
              <div className="error-message">
                <AlertCircle size={16} /> {error}
              </div>
            )}
            
            <div className="form-group">
              <label className="form-label"><Hash size={14} /> Device ID</label>
              <input 
                className="form-input" 
                placeholder="New Device ID (optional)"
                value={formData.device_id}
                onChange={(e) => setFormData({ ...formData, device_id: e.target.value })}
              />
              <p className="form-hint">Current: <strong>{device.device_id}</strong></p>
            </div>
            
            <div className="form-group">
              <label className="form-label"><Key size={14} /> Secret Key</label>
              <input 
                type="text" 
                className="form-input" 
                placeholder="New secret key (optional, min 8 chars)"
                value={formData.secret_key}
                onChange={(e) => setFormData({ ...formData, secret_key: e.target.value })}
                minLength={8}
              />
              <p className="form-hint">Leave empty to keep current secret key</p>
            </div>
          </div>
          
          <div className="edit-modal-footer">
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-teal" disabled={submitting}>
              {submitting ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
      
      <style>{`
        .edit-modal {
          background: var(--bg2);
          border: 1px solid var(--border);
          border-radius: 24px;
          max-width: 450px;
          width: 90%;
          position: relative;
          animation: modalSlideIn 0.3s ease;
        }
        .edit-modal-header {
          text-align: center;
          padding: 24px 24px 16px 24px;
          border-bottom: 1px solid var(--border);
        }
        .edit-modal-icon {
          width: 56px;
          height: 56px;
          background: rgba(0,212,170,0.1);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 12px;
          color: var(--teal);
        }
        .edit-modal-header h3 {
          font-size: 1.3rem;
          font-weight: 600;
          margin-bottom: 4px;
        }
        .edit-modal-header p {
          font-size: 0.8rem;
          color: var(--text3);
        }
        .edit-modal-body {
          padding: 20px 24px;
        }
        .edit-modal-footer {
          padding: 16px 24px 24px 24px;
          border-top: 1px solid var(--border);
          display: flex;
          gap: 12px;
          justify-content: flex-end;
        }
      `}</style>
    </div>
  );
};

// Main Devices Component
const Devices = () => {
  const { logout } = useAuth();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [stats, setStats] = useState({ total: 0, online: 0, offline: 0 });
  
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchDevices();
    fetchDeviceStatus();
    
    const interval = setInterval(() => {
      fetchDevices();
      fetchDeviceStatus();
    }, 30000);
    
    return () => clearInterval(interval);
  }, []);

  const fetchDevices = async () => {
    try {
      const data = await tenantApi.getDevices();
      setDevices(data || []);
      setError('');
    } catch (err) {
      console.error('Fetch devices error:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load devices');
    } finally {
      setLoading(false);
    }
  };

  const fetchDeviceStatus = async () => {
    try {
      const data = await tenantApi.getDeviceStatus();
      setStats(data || { total: 0, online: 0, offline: 0 });
    } catch (err) {
      console.error('Device status fetch error:', err);
    }
  };

  const handleDeleteDevice = async () => {
    if (!selectedDevice) return;
    setDeleting(true);
    try {
      await tenantApi.deleteDevice(selectedDevice.device_id);
      setSuccess('Device deleted successfully!');
      setShowDeleteModal(false);
      setSelectedDevice(null);
      await fetchDevices();
      await fetchDeviceStatus();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.message || 'Failed to delete device');
      setTimeout(() => setError(''), 3000);
    } finally {
      setDeleting(false);
    }
  };

  const isDeviceActuallyOnline = (device) => {
    if (device.status !== 'online') return false;
    if (!device.last_seen) return false;
    const lastSeen = new Date(device.last_seen);
    const now = new Date();
    const diffMinutes = (now - lastSeen) / 60000;
    return diffMinutes < 2;
  };

  const formatLastSeen = (timestamp) => {
    if (!timestamp) return 'Never';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hr ago`;
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  };

  const filteredDevices = devices.filter(device =>
    device.device_id?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) {
    return (
      <DashboardLayout 
        title="Devices" 
        role="superadmin"
        label="Tenant Admin" 
        abbr="TA" 
        color="#a855f7" 
        bgColor="rgba(168,85,247,0.15)"
      >
        <div className="skeleton-loader" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
          {[1, 2, 3, 4].map(i => <div key={i} style={{ background: 'var(--bg2)', borderRadius: '16px', height: '180px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>)}
        </div>
        <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }`}</style>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="Devices" 
      role="superadmin"
      label="Tenant Admin" 
      abbr="TA" 
      color="#a855f7" 
      bgColor="rgba(168,85,247,0.15)"
    >
      <style>{`
        .device-card { transition: all 0.2s; cursor: pointer; }
        .device-card:hover { transform: translateY(-2px); border-color: var(--teal); }
        .success-toast {
          position: fixed;
          bottom: 24px;
          right: 24px;
          background: rgba(34,197,94,0.95);
          color: white;
          padding: 12px 20px;
          border-radius: 12px;
          z-index: 1000;
          animation: slideIn 0.3s ease;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
      `}</style>

      {success && <div className="success-toast"><CheckCircle size={18} /> {success}</div>}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', gap: '1rem', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '0.5rem', flex: 1, maxWidth: '300px' }}>
          <div className="input-wrap" style={{ flex: 1, position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)' }} />
            <input 
              type="text" 
              className="form-input" 
              placeholder="Search by Device ID..." 
              style={{ paddingLeft: '32px' }}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <button className="btn btn-ghost" onClick={() => { fetchDevices(); fetchDeviceStatus(); }} title="Refresh">
            <RefreshCw size={16} />
          </button>
        </div>
        <button className="btn btn-teal" onClick={() => setShowAddModal(true)}>
          <Plus size={16} style={{ marginRight: '6px' }} />
          Add Device
        </button>
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '12px', padding: '12px 16px', marginBottom: '1rem', color: '#f87171', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertCircle size={16} /> {error}
          <button onClick={() => setError('')} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#f87171', cursor: 'pointer' }}>Dismiss</button>
        </div>
      )}

      {filteredDevices.length === 0 ? (
        <div className="card-box" style={{ textAlign: 'center', padding: '3rem' }}>
          <Cpu size={48} style={{ color: 'var(--text3)', marginBottom: '1rem' }} />
          <p style={{ color: 'var(--text3)' }}>No devices found</p>
          <button className="btn btn-teal" onClick={() => setShowAddModal(true)} style={{ marginTop: '1rem' }}>
            Add your first device
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
          {filteredDevices.map(device => {
            const actuallyOnline = isDeviceActuallyOnline(device);
            const displayStatus = actuallyOnline ? 'online' : 'offline';
            
            return (
              <div key={device.device_id} className="device-card" style={{
                background: 'var(--bg2)',
                border: `1px solid ${displayStatus === 'online' ? 'rgba(34,197,94,0.3)' : 'var(--border)'}`,
                borderRadius: '16px',
                padding: '1.25rem'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: '14px',
                      background: displayStatus === 'online' ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}>
                      {displayStatus === 'online' ? <Wifi size={24} style={{ color: '#22c55e' }} /> : <WifiOff size={24} style={{ color: '#ef4444' }} />}
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '1rem' }}>{device.device_id}</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>ID: {device.id}</div>
                    </div>
                  </div>
                  <Badge type={displayStatus === 'online' ? 'online' : 'offline'}>
                    {displayStatus === 'online' ? 'Online' : 'Offline'}
                  </Badge>
                </div>
                
                <div style={{ marginBottom: '1rem', padding: '0.75rem 0', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', color: 'var(--text3)' }}>
                    <Clock size={14} />
                    Last seen: {formatLastSeen(device.last_seen)}
                    {!actuallyOnline && device.status === 'online' && (
                      <span style={{ color: '#f97316', marginLeft: 'auto', fontSize: '0.7rem' }}>
                        ⚠️ Stale
                      </span>
                    )}
                  </div>
                </div>
                
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button 
                    className="btn btn-ghost" 
                    style={{ flex: 1, fontSize: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
                    onClick={() => {
                      setSelectedDevice(device);
                      setShowDetailModal(true);
                    }}
                  >
                    <Activity size={14} /> View Details
                  </button>
                  <button 
                    className="btn btn-ghost" 
                    style={{ padding: '6px 12px' }}
                    onClick={() => {
                      setSelectedDevice(device);
                      setShowEditModal(true);
                    }}
                    title="Edit Device"
                  >
                    <Edit2 size={14} />
                  </button>
                  <button 
                    className="btn btn-red" 
                    style={{ padding: '6px 12px' }}
                    onClick={() => {
                      setSelectedDevice(device);
                      setShowDeleteModal(true);
                    }}
                    title="Delete Device"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modals */}
      <AddDeviceModal 
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSuccess={() => { fetchDevices(); fetchDeviceStatus(); }}
      />

      <EditDeviceModal 
        isOpen={showEditModal}
        onClose={() => { setShowEditModal(false); setSelectedDevice(null); }}
        device={selectedDevice}
        onSuccess={() => { fetchDevices(); fetchDeviceStatus(); }}
      />

      <ConfirmationModal
        isOpen={showDeleteModal}
        onClose={() => { setShowDeleteModal(false); setSelectedDevice(null); }}
        onConfirm={handleDeleteDevice}
        title="Delete Device"
        message={`Are you sure you want to delete device "${selectedDevice?.device_id}"? This action cannot be undone.`}
        confirmText="Delete"
        cancelText="Cancel"
        type="danger"
        confirmVariant="danger"
        loading={deleting}
      />

      {showDetailModal && selectedDevice && (
        <DeviceDetailModal 
          device={selectedDevice} 
          onClose={() => { setShowDetailModal(false); setSelectedDevice(null); }}
        />
      )}
    </DashboardLayout>
  );
};

export default Devices;