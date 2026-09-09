// src/pages/tenant/Departments.jsx
import React, { useState, useEffect } from 'react';
import { ArrowLeft, Plus, Search, RefreshCw, AlertCircle, Building2, Users, UserCog, Trash2, Edit2, Save, X } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import ConfirmationModal from '../../components/ConfirmationModal';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const Departments = () => {
  const { logout } = useAuth();
  const [view, setView] = useState('list');
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [formData, setFormData] = useState({ department_name: '' });
  const [submitting, setSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  
  // Edit state
  const [editingDept, setEditingDept] = useState(null);
  const [editName, setEditName] = useState('');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletingDept, setDeletingDept] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchDepartments();
  }, []);

  const fetchDepartments = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await tenantApi.getDepartments();
      setDepartments(data || []);
    } catch (err) {
      console.error('Fetch departments error:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load departments');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateDept = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    
    if (!formData.department_name.trim()) {
      setError('Department name is required');
      setSubmitting(false);
      return;
    }
    
    try {
      await tenantApi.createDepartment(formData);
      setSuccessMessage('Department created successfully!');
      setFormData({ department_name: '' });
      await fetchDepartments();
      setView('list');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      setError(err.message || 'Failed to create department');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdateDept = async () => {
    if (!editingDept) return;
    if (!editName.trim()) {
      setError('Department name cannot be empty');
      return;
    }

    setSubmitting(true);
    try {
      await tenantApi.updateDepartment(editingDept.department_id, { department_name: editName });
      setSuccessMessage('Department updated successfully!');
      setEditingDept(null);
      setEditName('');
      await fetchDepartments();
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      setError(err.message || 'Failed to update department');
      setTimeout(() => setError(''), 3000);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteDept = async () => {
    if (!deletingDept) return;
    setDeleting(true);
    try {
      await tenantApi.deleteDepartment(deletingDept.department_id);
      setSuccessMessage('Department deleted successfully!');
      setShowDeleteModal(false);
      setDeletingDept(null);
      await fetchDepartments();
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      setError(err.message || 'Failed to delete department');
      setTimeout(() => setError(''), 3000);
    } finally {
      setDeleting(false);
    }
  };

  const startEdit = (dept) => {
    setEditingDept(dept);
    setEditName(dept.department_name);
  };

  const cancelEdit = () => {
    setEditingDept(null);
    setEditName('');
    setError('');
  };

  const openDeleteModal = (dept) => {
    setDeletingDept(dept);
    setShowDeleteModal(true);
  };

  const filteredDepts = departments.filter(dept =>
    dept.department_name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const stats = {
    total: departments.length,
    active: departments.filter(d => d.is_active).length,
    totalEmployees: departments.reduce((sum, d) => sum + (d.employee_count || 0), 0),
    totalOrgAdmins: departments.reduce((sum, d) => sum + (d.org_admin_count || 0), 0)
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="Departments" 
        role="superadmin" 
        label="Tenant Admin" 
        abbr="TA" 
        color="#a855f7" 
        bgColor="rgba(168,85,247,0.15)"
      >
        <div className="skeleton-loader" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
          {[1, 2, 3, 4].map(i => <div key={i} style={{ background: 'var(--bg2)', borderRadius: '12px', height: '180px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>)}
        </div>
        <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }`}</style>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="Departments" 
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
        .edit-input {
          background: var(--bg3);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 6px 10px;
          font-size: 0.85rem;
          color: var(--text);
          width: 100%;
        }
        .edit-input:focus {
          outline: none;
          border-color: var(--teal);
        }
      `}</style>

      {successMessage && (
        <div style={{
          position: 'fixed', bottom: '24px', right: '24px',
          background: 'rgba(34,197,94,0.95)', color: 'white',
          padding: '12px 20px', borderRadius: '8px', zIndex: 1000,
          animation: 'slideIn 0.3s ease'
        }}>
          {successMessage}
        </div>
      )}

      <ConfirmationModal
        isOpen={showDeleteModal}
        onClose={() => { setShowDeleteModal(false); setDeletingDept(null); }}
        onConfirm={handleDeleteDept}
        title="Delete Department"
        message={`Are you sure you want to delete department "${deletingDept?.department_name}"? This will remove all associated employees, org admins, and data. This action cannot be undone.`}
        confirmText="Delete Department"
        cancelText="Cancel"
        type="danger"
        confirmVariant="danger"
        loading={deleting}
      />

      {view === 'list' && (
        <>
          {/* Stats Cards */}
          <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
            <div className="stat-card purple">
              <div className="stat-label">Total Departments</div>
              <div className="stat-value">{stats.total}</div>
              <div className="stat-sub">Across organization</div>
            </div>
            <div className="stat-card green">
              <div className="stat-label">Active</div>
              <div className="stat-value">{stats.active}</div>
              <div className="stat-sub">Currently operational</div>
            </div>
            <div className="stat-card teal">
              <div className="stat-label">Total Employees</div>
              <div className="stat-value">{stats.totalEmployees}</div>
              <div className="stat-sub">Across all departments</div>
            </div>
            <div className="stat-card blue">
              <div className="stat-label">Org Admins</div>
              <div className="stat-value">{stats.totalOrgAdmins}</div>
              <div className="stat-sub">Department managers</div>
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
                  placeholder="Search departments..." 
                  style={{ paddingLeft: '32px' }}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
              <button className="btn btn-ghost" onClick={fetchDepartments} title="Refresh">
                <RefreshCw size={16} />
              </button>
            </div>
            <button className="btn btn-teal" onClick={() => setView('add')}>
              <Plus size={16} style={{ marginRight: '6px' }} />
              New Department
            </button>
          </div>

          {error && (
            <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '8px', padding: '12px', marginBottom: '1rem', color: '#f87171', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertCircle size={16} /> {error}
            </div>
          )}

          {/* Departments Grid */}
          {filteredDepts.length === 0 ? (
            <div className="card-box" style={{ textAlign: 'center', padding: '3rem' }}>
              <Building2 size={48} style={{ color: 'var(--text3)', marginBottom: '1rem' }} />
              <p style={{ color: 'var(--text3)' }}>No departments found</p>
              <button className="btn btn-teal" onClick={() => setView('add')} style={{ marginTop: '1rem' }}>
                Create your first department
              </button>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
              {filteredDepts.map(dept => (
                <div key={dept.department_id} style={{
                  background: 'var(--bg2)',
                  border: `1px solid ${dept.is_active ? 'var(--border)' : 'rgba(239,68,68,0.3)'}`,
                  borderRadius: '12px',
                  padding: '1.25rem',
                  transition: 'all 0.2s'
                }}>
                  {editingDept?.department_id === dept.department_id ? (
                    // Edit Mode
                    <div>
                      <div style={{ marginBottom: '1rem' }}>
                        <input
                          type="text"
                          className="edit-input"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          autoFocus
                          placeholder="Department name"
                        />
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button 
                          className="btn btn-teal" 
                          onClick={handleUpdateDept}
                          disabled={submitting}
                          style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                        >
                          <Save size={12} /> Save
                        </button>
                        <button 
                          className="btn btn-ghost" 
                          onClick={cancelEdit}
                          style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                        >
                          <X size={12} /> Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    // View Mode
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                        <div>
                          <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.25rem' }}>{dept.department_name}</h3>
                          <span style={{ fontSize: '0.7rem', fontFamily: 'var(--mono)', color: 'var(--text3)' }}>
                            ID: {dept.department_id}
                          </span>
                        </div>
                        <Badge type={dept.is_active ? 'active' : 'inactive'}>
                          {dept.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </div>
                      
                      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', padding: '0.5rem 0', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
                        <div style={{ flex: 1, textAlign: 'center' }}>
                          <Users size={14} style={{ color: 'var(--text3)', marginBottom: '4px' }} />
                          <div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>Employees</div>
                          <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{dept.employee_count || 0}</div>
                        </div>
                        <div style={{ flex: 1, textAlign: 'center' }}>
                          <UserCog size={14} style={{ color: 'var(--text3)', marginBottom: '4px' }} />
                          <div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>Org Admins</div>
                          <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{dept.org_admin_count || 0}</div>
                        </div>
                      </div>
                      
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button 
                          className="btn btn-ghost" 
                          onClick={() => startEdit(dept)}
                          style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                        >
                          <Edit2 size={12} /> Edit
                        </button>
                        <button 
                          className="btn btn-red" 
                          onClick={() => openDeleteModal(dept)}
                          style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                        >
                          <Trash2 size={12} /> Delete
                        </button>
                      </div>
                    </>
                  )}
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
              <ArrowLeft size={18} /> Back to Departments
            </button>
          </div>
          
          <div className="card-box" style={{ maxWidth: '500px' }}>
            <h4 style={{ marginBottom: '0.5rem' }}>Create New Department</h4>
            <p style={{ fontSize: '0.8rem', color: 'var(--text3)', marginBottom: '1.5rem' }}>
              Departments help organize employees and assign department admins
            </p>
            
            <form onSubmit={handleCreateDept}>
              <div className="form-group">
                <label className="form-label">Department Name *</label>
                <input 
                  className="form-input" 
                  placeholder="e.g., Engineering, Human Resources, Sales"
                  value={formData.department_name}
                  onChange={(e) => setFormData({ ...formData, department_name: e.target.value })}
                  required
                />
              </div>
              
              <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem' }}>
                <button type="submit" className="btn btn-teal" disabled={submitting}>
                  {submitting ? 'Creating...' : 'Create Department'}
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

export default Departments;