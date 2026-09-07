// src/pages/tenant/DeviceCommands.jsx
import React, { useState, useEffect } from 'react';
import { ArrowLeft, Cpu, Users, Fingerprint, Trash2, Send, AlertCircle, CheckCircle, RefreshCw, Search } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const DeviceCommands = () => {
  const { logout } = useAuth();
  const [devices, setDevices] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [selectedDevice, setSelectedDevice] = useState('');
  const [selectedEmployee, setSelectedEmployee] = useState('');
  const [commandType, setCommandType] = useState('enroll');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const [devicesData, employeesData] = await Promise.all([
        tenantApi.getDevices(),
        tenantApi.getAllEmployees(),
      ]);
      setDevices(devicesData || []);
      setEmployees(employeesData || []);
    } catch (err) {
      console.error('Fetch error:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleFireCommand = async () => {
    if (!selectedDevice) {
      setError('Please select a device');
      return;
    }
    if (!selectedEmployee && commandType === 'enroll') {
      setError('Please select an employee');
      return;
    }

    setSubmitting(true);
    setError('');
    setSuccess('');

    try {
      const employee = employees.find(e => e.id === parseInt(selectedEmployee));
      
      if (commandType === 'enroll' && !employee?.finger_id) {
        setError('Selected employee does not have a fingerprint ID assigned');
        setSubmitting(false);
        return;
      }

      const payload = {
        device_id: selectedDevice,
        command: commandType,
        target_id: commandType === 'enroll' ? employee.finger_id : (selectedEmployee || 0)
      };

      const response = await tenantApi.fireCommand(payload);
      setSuccess(`Command "${commandType}" sent successfully to device!`);
      
      // Clear selection after successful command
      setTimeout(() => setSuccess(''), 5000);
    } catch (err) {
      setError(err.message || 'Failed to send command');
      setTimeout(() => setError(''), 5000);
    } finally {
      setSubmitting(false);
    }
  };

  const getAvailableEmployees = () => {
    if (commandType === 'enroll') {
      // For enroll, show employees without fingerprint or with fingerprint
      return employees.filter(e => e.is_active);
    } else {
      // For delete, show employees with fingerprint
      return employees.filter(e => e.finger_id && e.is_active);
    }
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="Device Commands" 
        role="superadmin" 
        label="Tenant Admin" 
        abbr="TA" 
        color="#a855f7" 
        bgColor="rgba(168,85,247,0.15)"
      >
        <div className="skeleton-loader">{/* Loading skeleton */}</div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="Device Commands" 
      role="superadmin" 
      label="Tenant Admin" 
      abbr="TA" 
      color="#a855f7" 
      bgColor="rgba(168,85,247,0.15)"
    >
      <style>{`
        .command-card {
          background: linear-gradient(135deg, var(--bg2), var(--bg3));
          border: 1px solid var(--border);
          border-radius: 16px;
          padding: 1.5rem;
        }
      `}</style>

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card purple">
          <div className="stat-label">Available Devices</div>
          <div className="stat-value">{devices.filter(d => d.status === 'online').length}</div>
          <div className="stat-sub">Online devices ready for commands</div>
        </div>
        <div className="stat-card teal">
          <div className="stat-label">Enrolled Employees</div>
          <div className="stat-value">{employees.filter(e => e.finger_id).length}</div>
          <div className="stat-sub">Have fingerprint assigned</div>
        </div>
        <div className="stat-card amber">
          <div className="stat-label">Pending Enrollment</div>
          <div className="stat-value">{employees.filter(e => !e.finger_id && e.is_active).length}</div>
          <div className="stat-sub">Need fingerprint enrollment</div>
        </div>
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '8px', padding: '12px', marginBottom: '1rem', color: '#f87171', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {success && (
        <div style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', borderRadius: '8px', padding: '12px', marginBottom: '1rem', color: '#4ade80', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CheckCircle size={16} /> {success}
        </div>
      )}

      {/* Command Card */}
      <div className="command-card">
        <h3 style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Cpu size={20} /> Send Device Command
        </h3>
        <p style={{ color: 'var(--text3)', fontSize: '0.85rem', marginBottom: '1.5rem' }}>
          Send fingerprint enrollment or deletion commands to biometric devices
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem' }}>
          {/* Device Selection */}
          <div className="form-group">
            <label className="form-label">Select Device *</label>
            <select 
              className="form-select"
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(e.target.value)}
              style={{ padding: '0.75rem' }}
            >
              <option value="">Choose a device</option>
              {devices.map(device => (
                <option key={device.device_id} value={device.device_id}>
                  {device.device_id} - {device.status === 'online' ? '🟢 Online' : '🔴 Offline'}
                </option>
              ))}
            </select>
            {selectedDevice && (
              <p style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '4px' }}>
                {devices.find(d => d.device_id === selectedDevice)?.status === 'online' 
                  ? 'Device is online and ready' 
                  : 'Device is offline - command will be queued'}
              </p>
            )}
          </div>

          {/* Command Type */}
          <div className="form-group">
            <label className="form-label">Command Type *</label>
            <div style={{ display: 'flex', gap: '1rem', marginTop: '0.25rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input 
                  type="radio" 
                  value="enroll" 
                  checked={commandType === 'enroll'}
                  onChange={(e) => setCommandType(e.target.value)}
                />
                <Fingerprint size={16} /> Enroll Fingerprint
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input 
                  type="radio" 
                  value="delete" 
                  checked={commandType === 'delete'}
                  onChange={(e) => setCommandType(e.target.value)}
                />
                <Trash2 size={16} /> Delete Fingerprint
              </label>
            </div>
          </div>

          {/* Employee Selection */}
          <div className="form-group">
            <label className="form-label">
              {commandType === 'enroll' ? 'Select Employee to Enroll *' : 'Select Employee to Delete *'}
            </label>
            <select 
              className="form-select"
              value={selectedEmployee}
              onChange={(e) => setSelectedEmployee(e.target.value)}
              style={{ padding: '0.75rem' }}
            >
              <option value="">Choose an employee</option>
              {getAvailableEmployees().map(emp => (
                <option key={emp.id} value={emp.id}>
                  {emp.name} ({emp.employee_code}) 
                  {emp.finger_id ? ` - FP:${emp.finger_id}` : ' - Not enrolled'}
                </option>
              ))}
            </select>
            {selectedEmployee && commandType === 'enroll' && (
              <p style={{ fontSize: '0.7rem', color: 'var(--teal)', marginTop: '4px' }}>
                Will enroll fingerprint to slot: {employees.find(e => e.id === parseInt(selectedEmployee))?.finger_id || 'Auto-assigned'}
              </p>
            )}
          </div>
        </div>

        <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" onClick={() => {
            setSelectedDevice('');
            setSelectedEmployee('');
            setCommandType('enroll');
          }}>
            Clear
          </button>
          <button 
            className="btn btn-teal" 
            onClick={handleFireCommand}
            disabled={submitting || !selectedDevice}
            style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            {submitting ? 'Sending...' : <><Send size={16} /> Send Command</>}
          </button>
        </div>
      </div>

      {/* Device Status List */}
      <div className="card-box" style={{ marginTop: '1.5rem' }}>
        <h4 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <RefreshCw size={16} /> Device Status
        </h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.75rem' }}>
          {devices.map(device => (
            <div key={device.device_id} style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0.75rem',
              background: 'var(--bg3)',
              borderRadius: '8px'
            }}>
              <div>
                <div style={{ fontSize: '0.85rem', fontWeight: 500 }}>{device.device_id}</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>
                  Last seen: {device.last_seen ? new Date(device.last_seen).toLocaleTimeString() : 'Never'}
                </div>
              </div>
              <Badge type={device.status === 'online' ? 'online' : 'offline'}>
                {device.status === 'online' ? 'Online' : 'Offline'}
              </Badge>
            </div>
          ))}
        </div>
      </div>

      {/* Instructions */}
      <div className="card-box" style={{ marginTop: '1rem', background: 'rgba(168,85,247,0.05)' }}>
        <h4 style={{ marginBottom: '0.5rem', fontSize: '0.9rem' }}>📋 Instructions</h4>
        <ul style={{ color: 'var(--text3)', fontSize: '0.8rem', marginLeft: '1rem', lineHeight: '1.6' }}>
          <li><strong>Enroll:</strong> Sends command to device to capture employee's fingerprint. Employee must scan finger on device after command is sent.</li>
          <li><strong>Delete:</strong> Removes fingerprint from device. Employee will no longer be able to mark attendance on that device.</li>
          <li>Commands are queued if device is offline and will execute when device reconnects.</li>
          <li>Ensure employee has a fingerprint ID assigned before sending enroll command.</li>
        </ul>
      </div>
    </DashboardLayout>
  );
};

export default DeviceCommands;