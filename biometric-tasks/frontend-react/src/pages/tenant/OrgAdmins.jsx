// src/pages/tenant/OrgAdmins.jsx
import React, { useState, useEffect } from 'react';
import { ArrowLeft, Plus, Search, RefreshCw, AlertCircle, Mail, Building2, Shield, Trash2, CheckCircle, XCircle, Copy } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import ConfirmationModal from '../../components/ConfirmationModal';
import PersistentToast from '../../components/PersistentToast';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const OrgAdmins = () => {
  const { logout } = useAuth();
  const [view, setView] = useState('list');
  const [orgAdmins, setOrgAdmins] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [formData, setFormData] = useState({ name: '', email: '', dept_id: '' });
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState(null);
  const [lastCreatedCredentials, setLastCreatedCredentials] = useState(null);
  
  // Modal states
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletingAdmin, setDeletingAdmin] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const [adminsData, deptsData] = await Promise.all([
        tenantApi.getOrgAdmins(),
        tenantApi.getDepartments(),
      ]);
      setOrgAdmins(adminsData || []);
      setDepartments(deptsData || []);
    } catch (err) {
      console.error('Fetch error:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const closeToast = () => {
    setToast(null);
    setLastCreatedCredentials(null);
  };

  const copyToClipboard = (text, fieldName) => {
    navigator.clipboard.writeText(text);
    setToast({ 
      message: `📋 ${fieldName} copied to clipboard!`, 
      type: 'info', 
      persistent: false 
    });
  };

  const handleCreateAdmin = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    
    if (!formData.name.trim()) {
      setError('Name is required');
      setSubmitting(false);
      return;
    }
    if (!formData.email.trim()) {
      setError('Email is required');
      setSubmitting(false);
      return;
    }
    if (!formData.dept_id) {
      setError('Please select a department');
      setSubmitting(false);
      return;
    }
    
    try {
      const response = await tenantApi.createOrgAdmin({
        name: formData.name,
        email: formData.email,
        dept_id: parseInt(formData.dept_id),
      });
      
      const credentials = response.credentials;
      setLastCreatedCredentials(credentials);
      
      // Build persistent toast message
      let toastMessage = `✅ Org Admin created successfully!\n\n`;
      toastMessage += `👤 Name: ${credentials.name}\n`;
      toastMessage += `📧 Email: ${credentials.email}\n`;
      toastMessage += `🔑 Password: ${credentials.password}\n\n`;
      toastMessage += `⚠️ Please save these credentials. They will not be shown again.`;
      
      setToast({ 
        message: toastMessage, 
        type: 'success',
        persistent: true
      });
      
      setFormData({ name: '', email: '', dept_id: '' });
      await fetchData();
      
    } catch (err) {
      setError(err.message || 'Failed to create org admin');
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleStatus = async (adminId, currentStatus) => {
    try {
      await tenantApi.updateOrgAdmin(adminId, { is_active: !currentStatus });
      await fetchData();
      setToast({ 
        message: `Org admin ${!currentStatus ? 'activated' : 'deactivated'} successfully`, 
        type: 'success',
        persistent: false
      });
    } catch (err) {
      setError(err.message || 'Failed to update status');
    }
  };

  const handleDeleteClick = (admin) => {
    setDeletingAdmin(admin);
    setShowDeleteModal(true);
  };

  const handleConfirmDelete = async () => {
    if (!deletingAdmin) return;
    setDeleting(true);
    try {
      await tenantApi.deleteOrgAdmin(deletingAdmin.id);
      await fetchData();
      setToast({ 
        message: 'Org admin deactivated successfully', 
        type: 'success',
        persistent: false
      });
      setShowDeleteModal(false);
      setDeletingAdmin(null);
    } catch (err) {
      setError(err.message || 'Failed to delete org admin');
    } finally {
      setDeleting(false);
    }
  };

  // Custom render function for toast content with copy buttons
  const renderToastContent = (message, type) => {
    if (type === 'success' && lastCreatedCredentials) {
      return (
        <div>
          <div style={{ fontWeight: 600, marginBottom: '12px', fontSize: '1rem' }}>
            ✅ Org Admin Created Successfully!
          </div>
          <div style={{ marginBottom: '8px' }}>
            <div style={{ fontSize: '0.8rem', marginBottom: '4px' }}>
              👤 Name: <strong>{lastCreatedCredentials.name}</strong>
            </div>
            <div style={{ fontSize: '0.8rem', marginBottom: '4px' }}>
              📧 Email: <strong>{lastCreatedCredentials.email}</strong>
              <button 
                onClick={() => copyToClipboard(lastCreatedCredentials.email, 'Email')}
                style={{ background: 'none', border: 'none', cursor: 'pointer', marginLeft: '8px', color: 'white', verticalAlign: 'middle' }}
              >
                <Copy size={12} />
              </button>
            </div>
            <div style={{ 
              fontSize: '0.8rem', 
              marginTop: '8px', 
              padding: '8px', 
              background: 'rgba(0,0,0,0.2)', 
              borderRadius: '6px',
              fontFamily: 'monospace'
            }}>
              🔑 Password: <strong style={{ color: '#fbbf24' }}>{lastCreatedCredentials.password}</strong>
              <button 
                onClick={() => copyToClipboard(lastCreatedCredentials.password, 'Password')}
                style={{ background: 'none', border: 'none', cursor: 'pointer', marginLeft: '8px', color: 'white', verticalAlign: 'middle' }}
              >
                <Copy size={12} />
              </button>
            </div>
          </div>
          <div style={{ 
            fontSize: '0.7rem', 
            marginTop: '10px', 
            opacity: 0.8, 
            borderTop: '1px solid rgba(255,255,255,0.2)', 
            paddingTop: '8px' 
          }}>
            ⚠️ Please save these credentials. They will not be shown again.
          </div>
        </div>
      );
    }
    return message;
  };

  const filteredAdmins = orgAdmins.filter(admin =>
    admin.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    admin.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    admin.department_name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const stats = {
    total: orgAdmins.length,
    active: orgAdmins.filter(a => a.is_active).length,
    inactive: orgAdmins.filter(a => !a.is_active).length,
    totalEmployees: orgAdmins.reduce((sum, a) => sum + (a.employee_count || 0), 0),
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="Org Admins" 
        role="superadmin" 
        label="Tenant Admin" 
        abbr="TA" 
        color="#a855f7" 
        bgColor="rgba(168,85,247,0.15)"
      >
        <div className="skeleton-loader" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
          {[1, 2, 3].map(i => <div key={i} style={{ background: 'var(--bg2)', borderRadius: '12px', height: '200px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>)}
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="Organization Administrators" 
      role="superadmin" 
      label="Tenant Admin" 
      abbr="TA" 
      color="#a855f7" 
      bgColor="rgba(168,85,247,0.15)"
    >
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>

      {/* Persistent Toast */}
      {toast && (
        <PersistentToast 
          message={toast.message}
          type={toast.type}
          persistent={toast.persistent}
          onClose={closeToast}
          renderContent={renderToastContent}
        />
      )}
      
      {/* Error Message */}
      {error && (
        <div style={{ 
          background: 'rgba(239,68,68,0.1)', 
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: '8px',
          padding: '12px',
          marginBottom: '1rem',
          color: '#f87171',
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <ConfirmationModal
        isOpen={showDeleteModal}
        onClose={() => { setShowDeleteModal(false); setDeletingAdmin(null); }}
        onConfirm={handleConfirmDelete}
        title="Deactivate Org Admin"
        message={`Are you sure you want to deactivate "${deletingAdmin?.name}"? This will prevent them from accessing the system and managing their department. They can be reactivated later if needed.`}
        confirmText="Deactivate"
        cancelText="Cancel"
        type="danger"
        confirmVariant="danger"
        loading={deleting}
      />

      {view === 'list' && (
        <>
          {/* Stats Cards */}
          <div className="stats-grid">
            <div className="stat-card purple">
              <div className="stat-label">Total Org Admins</div>
              <div className="stat-value">{stats.total}</div>
              <div className="stat-sub">Department managers</div>
            </div>
            <div className="stat-card green">
              <div className="stat-label">Active</div>
              <div className="stat-value">{stats.active}</div>
              <div className="stat-sub">Currently active</div>
            </div>
            <div className="stat-card red">
              <div className="stat-label">Inactive</div>
              <div className="stat-value">{stats.inactive}</div>
              <div className="stat-sub">Deactivated accounts</div>
            </div>
            <div className="stat-card teal">
              <div className="stat-label">Managed Employees</div>
              <div className="stat-value">{stats.totalEmployees}</div>
              <div className="stat-sub">Across departments</div>
            </div>
          </div>

          {/* Controls */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
            <div style={{ display: 'flex', gap: '0.5rem', flex: 1, maxWidth: '300px' }}>
              <div className="input-wrap" style={{ flex: 1, position: 'relative' }}>
                <Search size={16} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)' }} />
                <input 
                  type="text" 
                  className="form-input" 
                  placeholder="Search by name, email, department..." 
                  style={{ paddingLeft: '32px' }}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
              <button className="btn btn-ghost" onClick={fetchData} title="Refresh">
                <RefreshCw size={16} />
              </button>
            </div>
            <button className="btn btn-teal" onClick={() => setView('add')}>
              <Plus size={16} style={{ marginRight: '6px' }} />
              Add Org Admin
            </button>
          </div>

          {/* Admins Grid */}
          {filteredAdmins.length === 0 ? (
            <div className="card-box" style={{ textAlign: 'center', padding: '3rem' }}>
              <Shield size={48} style={{ color: 'var(--text3)', marginBottom: '1rem' }} />
              <p style={{ color: 'var(--text3)' }}>No organization administrators found</p>
              <button className="btn btn-teal" onClick={() => setView('add')} style={{ marginTop: '1rem' }}>
                Add your first org admin
              </button>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
              {filteredAdmins.map(admin => (
                <div key={admin.id} style={{
                  background: 'var(--bg2)',
                  border: `1px solid ${admin.is_active ? 'var(--border)' : 'rgba(239,68,68,0.3)'}`,
                  borderRadius: '12px',
                  padding: '1.25rem',
                  opacity: admin.is_active ? 1 : 0.7
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div style={{
                        width: '48px',
                        height: '48px',
                        borderRadius: '12px',
                        background: admin.is_active ? 'rgba(168,85,247,0.15)' : 'rgba(239,68,68,0.1)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}>
                        <Shield size={24} style={{ color: admin.is_active ? '#a855f7' : '#ef4444' }} />
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '1rem' }}>{admin.name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text3)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Mail size={12} /> {admin.email}
                        </div>
                      </div>
                    </div>
                    <Badge type={admin.is_active ? 'active' : 'inactive'}>
                      {admin.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                  
                  <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '8px', 
                    padding: '0.75rem 0',
                    borderTop: '1px solid var(--border)',
                    borderBottom: '1px solid var(--border)',
                    marginBottom: '0.75rem'
                  }}>
                    <Building2 size={14} style={{ color: 'var(--text3)' }} />
                    <span style={{ fontSize: '0.85rem' }}>{admin.department_name || 'No department'}</span>
                    <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--text3)' }}>
                      {admin.employee_count || 0} employees managed
                    </span>
                  </div>
                  
                  <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                    <button 
                      className="btn btn-ghost" 
                      onClick={() => handleToggleStatus(admin.id, admin.is_active)}
                      style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                    >
                      {admin.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                    <button 
                      className="btn btn-red" 
                      onClick={() => handleDeleteClick(admin)}
                      style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                    >
                      <Trash2 size={12} style={{ marginRight: '4px' }} /> Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {view === 'add' && (
        <div>
          <div style={{ marginBottom: '1.5rem' }}>
            <button className="btn btn-ghost" onClick={() => setView('list')} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ArrowLeft size={18} /> Back to Org Admins
            </button>
          </div>
          
          <div className="card-box" style={{ maxWidth: '500px' }}>
            <h4 style={{ marginBottom: '0.5rem' }}>Add Organization Administrator</h4>
            <p style={{ fontSize: '0.8rem', color: 'var(--text3)', marginBottom: '1.5rem' }}>
              Org admins can manage employees, view attendance, and approve leaves for their department.
              A strong password will be auto-generated and shown in a persistent popup after creation.
            </p>
            
            <form onSubmit={handleCreateAdmin}>
              <div className="form-group">
                <label className="form-label">Full Name *</label>
                <input 
                  className="form-input" 
                  placeholder="e.g., John Doe"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                />
              </div>
              
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Email Address *</label>
                <input 
                  type="email"
                  className="form-input" 
                  placeholder="admin@department.com"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  required
                />
                <p style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '4px' }}>
                  This will be used as username for login
                </p>
              </div>
              
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Department *</label>
                <select 
                  className="form-select"
                  value={formData.dept_id}
                  onChange={(e) => setFormData({ ...formData, dept_id: e.target.value })}
                  required
                >
                  <option value="">Select a department</option>
                  {departments.filter(d => d.is_active).map(dept => (
                    <option key={dept.department_id} value={dept.department_id}>
                      {dept.department_name}
                    </option>
                  ))}
                </select>
                <p style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '4px' }}>
                  The org admin will manage this department
                </p>
              </div>
              
              <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem' }}>
                <button type="submit" className="btn btn-teal" disabled={submitting}>
                  {submitting ? 'Creating...' : 'Create Org Admin'}
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setView('list')}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default OrgAdmins;