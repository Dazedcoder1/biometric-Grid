// src/pages/org/Employees.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, Plus, RefreshCw, AlertCircle, CheckCircle, Eye, Fingerprint, Mail, Building2, User, Trash2, X, Edit2 } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import ConfirmationModal from '../../components/ConfirmationModal';
import { orgApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { Calendar } from 'lucide-react';
import PersistentToast from '../../components/PersistentToast';


function Toast({ message, type = 'success', onClose }) {
  const [toast, setToast] = useState(null); 
  useEffect(() => {
    const t = setTimeout(onClose, 3500);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div className="toast-notification" style={{
      position: 'fixed', bottom: '24px', right: '24px', zIndex: 9999,
      display: 'flex', alignItems: 'center', gap: '12px',
      background: type === 'success' ? 'rgba(0,212,170,0.95)' : 'rgba(239,68,68,0.95)',
      border: `1px solid ${type === 'success' ? 'rgba(0,212,170,0.5)' : 'rgba(239,68,68,0.5)'}`,
      borderRadius: '12px', padding: '12px 20px', color: 'white', fontSize: '0.9rem',
      backdropFilter: 'blur(8px)', boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
      animation: 'slideInRight 0.3s ease'
    }}>
      {type === 'success' ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
      {message}
    </div>
  );
}

// Premium Employee Detail Modal Component
const EmployeeDetailModal = ({ employee, onClose, onEdit }) => {
  if (!employee) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="employee-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose}>
          <X size={20} />
        </button>
        
        <div className="modal-header">
          <div className="modal-avatar">
            <User size={36} />
          </div>
          <div className="modal-title-section">
            <h3>{employee.name}</h3>
            <p>{employee.employee_code || 'No employee code'}</p>
          </div>
          <Badge type={employee.is_active ? 'active' : 'inactive'}>
            {employee.is_active ? 'Active' : 'Inactive'}
          </Badge>
        </div>
        
        <div className="modal-body">
          <div className="info-grid">
            <div className="info-item">
              <div className="info-label"><Mail size={14} /> Email</div>
              <div className="info-value">{employee.email || 'Not provided'}</div>
            </div>
            <div className="info-item">
              <div className="info-label"><Building2 size={14} /> Department</div>
              <div className="info-value">{employee.department_name || 'Not assigned'}</div>
            </div>
            <div className="info-item">
              <div className="info-label"><Fingerprint size={14} /> Fingerprint ID</div>
              <div className="info-value">
                {employee.finger_id ? (
                  <span style={{ color: 'var(--teal)', fontFamily: 'var(--mono)' }}>
                    FP-{String(employee.finger_id).padStart(3, '0')}
                  </span>
                ) : (
                  <span style={{ color: 'var(--text3)' }}>Not enrolled</span>
                )}
              </div>
            </div>
            <div className="info-item">
              <div className="info-label"><Calendar size={14} /> Joined</div>
              <div className="info-value">
                {employee.created_at ? new Date(employee.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) : 'N/A'}
              </div>
            </div>
          </div>
        </div>
        
        <div className="modal-footer">
          <button className="btn btn-teal" onClick={() => { onClose(); onEdit(employee); }} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Edit2 size={16} /> Edit Employee
          </button>
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
      
      <style>{`
        .employee-modal {
          background: var(--bg2);
          border: 1px solid var(--border);
          border-radius: 24px;
          max-width: 500px;
          width: 90%;
          position: relative;
          animation: modalSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          overflow: hidden;
        }
        @keyframes modalSlideIn {
          from {
            opacity: 0;
            transform: scale(0.95) translateY(-10px);
          }
          to {
            opacity: 1;
            transform: scale(1) translateY(0);
          }
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
        .modal-avatar {
          width: 64px;
          height: 64px;
          background: rgba(0,212,170,0.1);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--teal);
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
        }
        .info-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
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
        .modal-footer {
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

// Edit Employee Modal Component
const EditEmployeeModal = ({ isOpen, onClose, employee, onSuccess, departments }) => {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    employee_code: '',
    finger_id: '',
    dept_id: ''
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const { logout } = useAuth();

  useEffect(() => {
    if (employee && isOpen) {
      setFormData({
        name: employee.name || '',
        email: employee.email || '',
        employee_code: employee.employee_code || '',
        finger_id: employee.finger_id || '',
        dept_id: employee.department_id || ''
      });
    }
  }, [employee, isOpen]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');

    const updateData = {};
    if (formData.name !== employee.name) updateData.name = formData.name;
    if (formData.email !== employee.email) updateData.email = formData.email;
    if (formData.employee_code !== employee.employee_code) updateData.employee_code = formData.employee_code;
    if (formData.finger_id !== employee.finger_id && formData.finger_id) updateData.finger_id = parseInt(formData.finger_id);
    if (formData.dept_id !== employee.department_id && formData.dept_id) updateData.dept_id = parseInt(formData.dept_id);

    if (Object.keys(updateData).length === 0) {
      setError('No changes to update');
      setSubmitting(false);
      return;
    }

    try {
      await orgApi.updateEmployee(employee.id, updateData);
      onSuccess();
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to update employee');
      if (err?.response?.status === 401) logout();
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen || !employee) return null;

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
          <h3>Edit Employee</h3>
          <p>Update employee information</p>
        </div>
        
        <form onSubmit={handleSubmit}>
          <div className="edit-modal-body">
            {error && (
              <div className="error-message">
                <AlertCircle size={16} /> {error}
              </div>
            )}
            
            <div className="form-group">
              <label className="form-label">Full Name</label>
              <input 
                className="form-input" 
                placeholder="Employee name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>
            
            <div className="form-group">
              <label className="form-label">Email</label>
              <input 
                type="email"
                className="form-input" 
                placeholder="employee@company.com"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>
            
            <div className="form-group">
              <label className="form-label">Employee Code</label>
              <input 
                className="form-input" 
                placeholder="Employee code"
                value={formData.employee_code}
                onChange={(e) => setFormData({ ...formData, employee_code: e.target.value })}
              />
            </div>
            
            <div className="form-group">
              <label className="form-label">Fingerprint ID</label>
              <input 
                type="number"
                className="form-input" 
                placeholder="Finger ID (1-127)"
                value={formData.finger_id}
                onChange={(e) => setFormData({ ...formData, finger_id: e.target.value })}
                min="1"
                max="127"
              />
              <p className="form-hint">Leave empty to keep current fingerprint assignment</p>
            </div>
            
            <div className="form-group">
              <label className="form-label">Department</label>
              <select 
                className="form-select"
                value={formData.dept_id}
                onChange={(e) => setFormData({ ...formData, dept_id: e.target.value })}
              >
                <option value="">Select a department</option>
                {departments.filter(d => d.is_active).map(dept => (
                  <option key={dept.department_id} value={dept.department_id}>
                    {dept.department_name}
                  </option>
                ))}
              </select>
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
          max-width: 500px;
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

const Employees = () => {
  const { logout } = useAuth();
  const [view, setView] = useState('list');
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [slots, setSlots] = useState({ available: [] });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState(null);
  const [apiError, setApiError] = useState('');
  const [form, setForm] = useState({ name: '', employee_code: '', password: '', finger_id: '' });
  const [formErr, setFormErr] = useState('');
  
  const [showDeactivateModal, setShowDeactivateModal] = useState(false);
  const [deactivatingEmp, setDeactivatingEmp] = useState(null);
  const [deactivating, setDeactivating] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    setApiError('');
    try {
      const [empRes, slotRes, deptRes] = await Promise.all([
        orgApi.getEmployees(),
        orgApi.getAvailableSlots(),
        orgApi.getDepartments ? orgApi.getDepartments() : Promise.resolve([]),
      ]);
      setEmployees(empRes || []);
      setSlots(slotRes || { available: [] });
      setDepartments(deptRes || []);
    } catch (err) {
      if (err?.response?.status === 401) { logout(); return; }
      setApiError('Failed to load employees');
    } finally {
      setLoading(false);
    }
  }, [logout]);

  useEffect(() => { fetchEmployees(); }, [fetchEmployees]);

  const handleDeactivateConfirm = async () => {
    if (!deactivatingEmp) return;
    setDeactivating(true);
    try {
      await orgApi.deleteEmployee(deactivatingEmp.id);
      setToast({ message: `${deactivatingEmp.name} deactivated successfully.`, type: 'success' });
      fetchEmployees();
      setShowDeactivateModal(false);
      setDeactivatingEmp(null);
    } catch (err) {
      setToast({ message: err?.response?.data?.detail || 'Failed to deactivate.', type: 'error' });
    } finally {
      setDeactivating(false);
    }
  };



const handleAdd = async (e) => {
  e.preventDefault();
  setFormErr('');
  if (!form.name.trim()) { setFormErr('Full name is required.'); return; }
  setSubmitting(true);
  try {
    const payload = {
      name: form.name.trim(),
      employee_code: form.employee_code.trim() || undefined,
      password: form.password.trim() || undefined,
      finger_id: form.finger_id ? parseInt(form.finger_id, 10) : undefined,
    };
    const res = await orgApi.createEmployee(payload);
    const creds = res?.credentials;
    
    // Build the toast message with password
    let toastMessage = `✅ ${creds?.name} added successfully!\n`;
    toastMessage += `📋 Employee Code: ${creds?.employee_code}\n`;
    if (creds?.finger_id) {
      toastMessage += `🖐️ Fingerprint ID: ${creds?.finger_id}\n`;
    }
    if (creds?.password) {
      toastMessage += `🔑 Password: ${creds?.password}\n`;
    }
    
    // Set toast (will NOT auto-dismiss)
    setToast({ 
      message: toastMessage, 
      type: 'success'
    });
    
    setForm({ name: '', employee_code: '', password: '', finger_id: '' });
    setView('list');
    fetchEmployees();
  } catch (err) {
    setFormErr(err?.response?.data?.detail || 'Failed to add employee.');
  } finally {
    setSubmitting(false);
  }
};


  const handleUpdateSuccess = () => {
    setToast({ message: 'Employee updated successfully!', type: 'success' });
    fetchEmployees();
    setShowEditModal(false);
    setSelectedEmployee(null);
  };

  const openDeactivateModal = (emp) => {
    setDeactivatingEmp(emp);
    setShowDeactivateModal(true);
  };

  const openDetailModal = (emp) => {
    setSelectedEmployee(emp);
    setShowDetailModal(true);
  };

  const closeToast = () => {
    setToast(null);
  };
  

  const openEditModal = (emp) => {
    setSelectedEmployee(emp);
    setShowEditModal(true);
    setShowDetailModal(false);
  };

  if (loading) {
    return (
      <DashboardLayout title="All Employees" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
        <div className="skeleton-loader" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
          {[1,2,3,4,5,6].map(i => <div key={i} style={{ background: 'var(--bg2)', borderRadius: '16px', height: '200px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>)}
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="All Employees" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .employee-card { transition: all 0.2s; }
        .employee-card:hover { transform: translateY(-2px); border-color: var(--teal); }
      `}</style>

      {/* Toast */}
    {toast && (
      <PersistentToast 
        message={toast.message} 
        type={toast.type} 
        onClose={closeToast}
      />
    )}

      <ConfirmationModal
        isOpen={showDeactivateModal}
        onClose={() => { setShowDeactivateModal(false); setDeactivatingEmp(null); }}
        onConfirm={handleDeactivateConfirm}
        title="Deactivate Employee"
        message={`Are you sure you want to deactivate "${deactivatingEmp?.name}"? This will remove their fingerprint slot and prevent them from marking attendance.`}
        confirmText="Deactivate"
        cancelText="Cancel"
        type="danger"
        confirmVariant="danger"
        loading={deactivating}
      />

      {showDetailModal && selectedEmployee && (
        <EmployeeDetailModal 
          employee={selectedEmployee} 
          onClose={() => setShowDetailModal(false)}
          onEdit={openEditModal}
        />
      )}

      {showEditModal && selectedEmployee && (
        <EditEmployeeModal 
          isOpen={showEditModal}
          onClose={() => { setShowEditModal(false); setSelectedEmployee(null); }}
          employee={selectedEmployee}
          onSuccess={handleUpdateSuccess}
          departments={departments}
        />
      )}

      {view === 'list' && (
        <div>
          {apiError && (
            <div className="error-banner" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '12px', padding: '14px 18px', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '12px', color: '#f87171' }}>
              <AlertCircle size={18} /> {apiError}
              <button onClick={fetchEmployees} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#f87171', cursor: 'pointer' }}><RefreshCw size={16} /> Retry</button>
            </div>
          )}

          <div className="table-wrap">
            <div className="table-header">
              <span className="table-title">Employee Registry {!loading && <span style={{ fontSize: '0.75rem', color: 'var(--text3)', marginLeft: '8px' }}>({employees.length} records)</span>}</span>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button className="btn btn-ghost" onClick={fetchEmployees} disabled={loading}><RefreshCw size={14} /> Refresh</button>
                <button className="btn btn-teal" onClick={() => setView('add')}><Plus size={16} /> Add Employee</button>
              </div>
            </div>
            <table style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>Emp Code</th>
                  <th>Name</th>
                  <th>Department</th>
                  <th>FP Slot</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {employees.length === 0 ? (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>
                      No employees found. Add your first employee!
                    </td>
                  </tr>
                ) : (
                  employees.map((emp) => (
                    <tr key={emp.id}>
                      <td style={{ fontFamily: 'var(--mono)' }}>{emp.employee_code ?? '—'}</td>
                      <td style={{ fontWeight: 500 }}>{emp.name}</td>
                      <td>{emp.department_name || '—'}</td>
                      <td style={{ fontFamily: 'var(--mono)' }}>
                        {emp.finger_id ? `FP-${String(emp.finger_id).padStart(3, '0')}` : <span style={{ color: 'var(--text3)' }}>Not enrolled</span>}
                      </td>
                      <td><Badge type={emp.is_active ? 'active' : 'inactive'}>{emp.is_active ? 'Active' : 'Inactive'}</Badge></td>
                      <td>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button className="btn btn-ghost" onClick={() => openDetailModal(emp)} style={{ padding: '6px 12px' }} title="View Details">
                            <Eye size={14} /> View
                          </button>
                          <button className="btn btn-teal" onClick={() => openEditModal(emp)} style={{ padding: '6px 12px' }} title="Edit Employee">
                            <Edit2 size={14} /> Edit
                          </button>
                          <button className="btn btn-red" onClick={() => openDeactivateModal(emp)} disabled={!emp.is_active} style={{ padding: '6px 12px' }} title="Deactivate">
                            <Trash2 size={14} /> Deactivate
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {view === 'add' && (
        <div>
          <div style={{ marginBottom: '1.5rem' }}>
            <button className="btn btn-ghost" onClick={() => { setView('list'); setFormErr(''); }}>
              <ArrowLeft size={18} /> Back to Employees
            </button>
          </div>
          <div className="card-box" style={{ maxWidth: '600px' }}>
            <h4 style={{ marginBottom: '0.5rem' }}>Add New Employee</h4>
            <p style={{ color: 'var(--text3)', fontSize: '0.8rem', marginBottom: '1.5rem' }}>
              Leave fields blank to auto-generate. Credentials will be shown after saving.
            </p>
            {formErr && (
              <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '10px', padding: '12px', marginBottom: '1rem', color: '#f87171' }}>
                <AlertCircle size={15} /> {formErr}
              </div>
            )}
            <form onSubmit={handleAdd}>
              <div className="form-grid">
                <div className="form-group">
                  <label className="form-label">Full Name *</label>
                  <input className="form-input" placeholder="e.g., Aarav Kumar" value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} disabled={submitting} required />
                </div>
                <div className="form-group">
                  <label className="form-label">Employee Code <span style={{ color: 'var(--text3)' }}>(auto)</span></label>
                  <input className="form-input" placeholder="Leave blank to auto-generate" value={form.employee_code} onChange={(e) => setForm(f => ({ ...f, employee_code: e.target.value }))} disabled={submitting} />
                </div>
                <div className="form-group">
                  <label className="form-label">Password <span style={{ color: 'var(--text3)' }}>(auto)</span></label>
                  <input type="text" className="form-input" placeholder="Min 8 chars, auto-generated if blank" value={form.password} onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))} disabled={submitting} />
                </div>
                <div className="form-group">
                  <label className="form-label">Fingerprint Slot <span style={{ color: 'var(--text3)' }}>(auto)</span></label>
                  <select className="form-select" value={form.finger_id} onChange={(e) => setForm(f => ({ ...f, finger_id: e.target.value }))} disabled={submitting}>
                    <option value="">Auto-assign next free slot</option>
                    {slots.available?.slice(0, 30).map((fp) => (
                      <option key={fp} value={fp}>Slot {fp}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem' }}>
                <button type="submit" className="btn btn-teal" disabled={submitting}>
                  {submitting ? 'Creating...' : 'Register Employee'}
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => { setView('list'); setFormErr(''); }} disabled={submitting}>
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

export default Employees;