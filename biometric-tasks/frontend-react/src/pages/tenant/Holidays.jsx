// src/pages/tenant/Holidays.jsx
import React, { useState, useEffect } from 'react';
import { ArrowLeft, Plus, Trash2, Calendar as CalendarIcon, Search, RefreshCw, AlertCircle } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import ConfirmationModal from '../../components/ConfirmationModal';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const Holidays = () => {
  const { logout } = useAuth();
  const [view, setView] = useState('list');
  const [holidays, setHolidays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [formData, setFormData] = useState({ name: '', holiday_date: '', description: '' });
  const [submitting, setSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  
  // Modal states
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletingHoliday, setDeletingHoliday] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchHolidays();
  }, [selectedYear]);

  const fetchHolidays = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await tenantApi.getHolidays(selectedYear);
      setHolidays(data || []);
    } catch (err) {
      console.error('Fetch holidays error:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load holidays');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateHoliday = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    
    try {
      await tenantApi.createHoliday(formData);
      setSuccessMessage('Holiday created successfully!');
      setFormData({ name: '', holiday_date: '', description: '' });
      await fetchHolidays();
      setView('list');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      setError(err.message || 'Failed to create holiday');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteClick = (holiday) => {
    setDeletingHoliday(holiday);
    setShowDeleteModal(true);
  };

  const handleConfirmDelete = async () => {
    if (!deletingHoliday) return;
    setDeleting(true);
    try {
      await tenantApi.deleteHoliday(deletingHoliday.holiday_id);
      await fetchHolidays();
      setSuccessMessage('Holiday deleted successfully!');
      setShowDeleteModal(false);
      setDeletingHoliday(null);
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      setError(err.message || 'Failed to delete holiday');
      setTimeout(() => setError(''), 3000);
    } finally {
      setDeleting(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '--';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
  };

  const getDayOfWeek = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { weekday: 'long' });
  };

  const filteredHolidays = holidays.filter(holiday =>
    holiday.name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const holidaysByMonth = filteredHolidays.reduce((acc, holiday) => {
    const month = new Date(holiday.holiday_date).toLocaleDateString('en-US', { month: 'long' });
    if (!acc[month]) acc[month] = [];
    acc[month].push(holiday);
    return acc;
  }, {});

  const years = [new Date().getFullYear() - 1, new Date().getFullYear(), new Date().getFullYear() + 1];

  if (loading) {
    return (
      <DashboardLayout 
        title="Holidays" 
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
      title="Holidays" 
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

      {/* Delete Confirmation Modal */}
      <ConfirmationModal
        isOpen={showDeleteModal}
        onClose={() => { setShowDeleteModal(false); setDeletingHoliday(null); }}
        onConfirm={handleConfirmDelete}
        title="Delete Holiday"
        message={`Are you sure you want to delete "${deletingHoliday?.name}" on ${formatDate(deletingHoliday?.holiday_date)}? This action cannot be undone.`}
        confirmText="Delete Holiday"
        cancelText="Cancel"
        type="danger"
        confirmVariant="danger"
        loading={deleting}
      />

      {view === 'list' && (
        <>
          {/* Stats Card */}
          <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
            <div className="stat-card purple">
              <div className="stat-label">Total Holidays</div>
              <div className="stat-value">{holidays.length}</div>
              <div className="stat-sub">For {selectedYear}</div>
            </div>
            <div className="stat-card teal">
              <div className="stat-label">Upcoming</div>
              <div className="stat-value">
                {holidays.filter(h => new Date(h.holiday_date) >= new Date()).length}
              </div>
              <div className="stat-sub">Next 30 days</div>
            </div>
            <div className="stat-card amber">
              <div className="stat-label">Calendar View</div>
              <div className="stat-value" style={{ fontSize: '1rem' }}>
                {Object.keys(holidaysByMonth).length} months
              </div>
              <div className="stat-sub">With holidays</div>
            </div>
          </div>

          {/* Controls */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <select 
                className="form-select" 
                value={selectedYear} 
                onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                style={{ width: '100px' }}
              >
                {years.map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <div className="input-wrap" style={{ position: 'relative' }}>
                  <Search size={16} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)' }} />
                  <input 
                    type="text" 
                    className="form-input" 
                    placeholder="Search holidays..." 
                    style={{ paddingLeft: '32px', width: '200px' }}
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                  />
                </div>
                <button className="btn btn-ghost" onClick={fetchHolidays} title="Refresh">
                  <RefreshCw size={16} />
                </button>
              </div>
            </div>
            <button className="btn btn-teal" onClick={() => setView('add')}>
              <Plus size={16} style={{ marginRight: '6px' }} />
              Add Holiday
            </button>
          </div>

          {error && (
            <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '8px', padding: '12px', marginBottom: '1rem', color: '#f87171', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertCircle size={16} /> {error}
            </div>
          )}

          {/* Holidays by Month */}
          {Object.keys(holidaysByMonth).length === 0 ? (
            <div className="card-box" style={{ textAlign: 'center', padding: '3rem' }}>
              <CalendarIcon size={48} style={{ color: 'var(--text3)', marginBottom: '1rem' }} />
              <p style={{ color: 'var(--text3)' }}>No holidays found for {selectedYear}</p>
              <button className="btn btn-teal" onClick={() => setView('add')} style={{ marginTop: '1rem' }}>
                Add your first holiday
              </button>
            </div>
          ) : (
            Object.entries(holidaysByMonth).map(([month, monthHolidays]) => (
              <div key={month} style={{ marginBottom: '2rem' }}>
                <div style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem', paddingBottom: '0.5rem', borderBottom: '2px solid var(--border)', color: 'var(--teal)' }}>
                  {month}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem' }}>
                  {monthHolidays.map(holiday => (
                    <div key={holiday.holiday_id} style={{
                      background: 'var(--bg2)',
                      border: '1px solid var(--border)',
                      borderRadius: '10px',
                      padding: '1rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{holiday.name}</div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '4px' }}>
                          {formatDate(holiday.holiday_date)} · {getDayOfWeek(holiday.holiday_date)}
                        </div>
                        {holiday.description && (
                          <div style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '4px' }}>
                            {holiday.description}
                          </div>
                        )}
                      </div>
                      <button 
                        className="btn btn-red" 
                        onClick={() => handleDeleteClick(holiday)}
                        style={{ padding: '4px 8px' }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </>
      )}

      {view === 'add' && (
        <div>
          <div style={{ marginBottom: '1.5rem' }}>
            <button className="btn btn-ghost" onClick={() => setView('list')} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ArrowLeft size={18} /> Back to Holidays
            </button>
          </div>
          
          <div className="card-box" style={{ maxWidth: '500px' }}>
            <h4 style={{ marginBottom: '0.5rem' }}>Add New Holiday</h4>
            <p style={{ fontSize: '0.8rem', color: 'var(--text3)', marginBottom: '1.5rem' }}>
              Holidays will be visible to all employees and affect attendance calculations
            </p>
            
            <form onSubmit={handleCreateHoliday}>
              <div className="form-group">
                <label className="form-label">Holiday Name *</label>
                <input 
                  className="form-input" 
                  placeholder="e.g., Independence Day, Diwali, Christmas"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                />
              </div>
              
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Date *</label>
                <input 
                  type="date" 
                  className="form-input" 
                  value={formData.holiday_date}
                  onChange={(e) => setFormData({ ...formData, holiday_date: e.target.value })}
                  required
                />
              </div>
              
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Description (Optional)</label>
                <textarea 
                  className="form-input" 
                  rows="3"
                  placeholder="Additional information about this holiday..."
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                />
              </div>
              
              <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem' }}>
                <button type="submit" className="btn btn-teal" disabled={submitting}>
                  {submitting ? 'Creating...' : 'Create Holiday'}
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

export default Holidays;