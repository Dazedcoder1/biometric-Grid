// src/pages/employee/Profile.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { profileAPI } from '../../services/api';
import { employeeApi } from '../../services/api';
const Profile = () => {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  
  // Edit form state
  const [editData, setEditData] = useState({
    name: '',
    email: '',
  });
  
  // Password change state
  const [passwordData, setPasswordData] = useState({
    old_password: '',
    new_password: '',
  });

  useEffect(() => {
    fetchProfile();
  }, []);

  const fetchProfile = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await profileAPI.getProfile();
      setProfile(data);
      setEditData({
        name: data.name || '',
        email: data.email || '',
      });
    } catch (err) {
      console.error('Failed to fetch profile:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    
    try {
      const result = await profileAPI.updateProfile(editData);
      setSuccess('Profile updated successfully!');
      await fetchProfile();
      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      console.error('Failed to update profile:', err);
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    
    try {
      await profileAPI.changePassword(passwordData);
      setSuccess('Password changed successfully!');
      setPasswordData({ old_password: '', new_password: '' });
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      console.error('Failed to change password:', err);
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const getInitials = (name) => {
    if (!name) return 'U';
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="My Profile" 
        role="user" 
        label="Employee" 
        abbr="EM" 
        color="#f59e0b" 
        bgColor="rgba(245,158,11,0.15)"
      >
        <div className="card-box" style={{ textAlign: 'center', padding: '4rem' }}>
          <p>Loading profile...</p>
        </div>
      </DashboardLayout>
    );
  }

  if (!profile) {
    return (
      <DashboardLayout 
        title="My Profile" 
        role="user" 
        label="Employee" 
        abbr="EM" 
        color="#f59e0b" 
        bgColor="rgba(245,158,11,0.15)"
      >
        <div className="card-box" style={{ textAlign: 'center', padding: '4rem' }}>
          <p style={{ color: 'var(--red)' }}>Failed to load profile</p>
          <button className="btn btn-teal" onClick={fetchProfile}>Retry</button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="My Profile" 
      role="user" 
      label="Employee" 
      abbr={getInitials(profile.name)} 
      color="#f59e0b" 
      bgColor="rgba(245,158,11,0.15)"
    >
      <div className="card-box" style={{ maxWidth: '560px' }}>
        {/* Error/Success Messages */}
        {error && (
          <div style={{ 
            background: 'rgba(239,68,68,0.1)', 
            border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: '8px',
            padding: '0.75rem',
            marginBottom: '1rem',
            color: '#f87171'
          }}>
            {error}
          </div>
        )}
        
        {success && (
          <div style={{ 
            background: 'rgba(34,197,94,0.1)', 
            border: '1px solid rgba(34,197,94,0.3)',
            borderRadius: '8px',
            padding: '0.75rem',
            marginBottom: '1rem',
            color: '#4ade80'
          }}>
            {success}
          </div>
        )}

        {/* Profile Header */}
        <div className="profile-header" style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', marginBottom: '1.5rem' }}>
          <div className="profile-av" style={{ 
            background: 'rgba(245,158,11,0.15)', 
            color: 'var(--amber)',
            width: '80px',
            height: '80px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '1.8rem',
            fontWeight: 700
          }}>
            {getInitials(profile.name)}
          </div>
          <div>
            <div style={{ fontSize: '1.4rem', fontWeight: 600 }}>{profile.name}</div>
            <div style={{ color: 'var(--text3)', fontSize: '0.9rem', marginTop: '3px' }}>
              {profile.employee_code || 'No ID'} · {profile.department_name || 'No Department'}
            </div>
            <span className={`badge ${profile.is_active ? 'active' : 'inactive'}`} style={{ marginTop: '8px', display: 'inline-flex' }}>
              {profile.is_active ? 'active' : 'inactive'}
            </span>
          </div>
        </div>

        <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1.5rem' }}>
          {/* Read-only Info */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '2rem' }}>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text3)', fontFamily: 'var(--mono)', marginBottom: '4px', textTransform: 'uppercase' }}>
                Employee ID
              </div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: '0.9rem' }}>
                {profile.employee_code || 'N/A'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text3)', fontFamily: 'var(--mono)', marginBottom: '4px', textTransform: 'uppercase' }}>
                Fingerprint ID
              </div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: '0.9rem' }}>
                {profile.finger_id || 'Not registered'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text3)', fontFamily: 'var(--mono)', marginBottom: '4px', textTransform: 'uppercase' }}>
                Department
              </div>
              <div style={{ fontSize: '0.9rem' }}>
                {profile.department_name || 'N/A'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text3)', fontFamily: 'var(--mono)', marginBottom: '4px', textTransform: 'uppercase' }}>
                Role
              </div>
              <div style={{ fontSize: '0.9rem', textTransform: 'capitalize' }}>
                {profile.role || 'Employee'}
              </div>
            </div>
          </div>

          {/* Edit Profile Form */}
          <h4 style={{ marginBottom: '1rem' }}>Edit Info</h4>
          <form onSubmit={handleUpdateProfile}>
            <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Full Name</label>
                <input 
                  className="form-input" 
                  value={editData.name}
                  onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input 
                  className="form-input" 
                  type="email"
                  value={editData.email}
                  onChange={(e) => setEditData({ ...editData, email: e.target.value })}
                  required
                />
              </div>
            </div>
            <button 
              type="submit" 
              className="btn btn-teal" 
              style={{ marginTop: '1rem', width: '100%', padding: '0.8rem' }}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </form>

          {/* Change Password Form */}
          <h4 style={{ marginTop: '1.5rem', marginBottom: '1rem' }}>Change Password</h4>
          <form onSubmit={handleChangePassword}>
            <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Current Password</label>
                <input 
                  className="form-input" 
                  type="password" 
                  placeholder="••••••••" 
                  value={passwordData.old_password}
                  onChange={(e) => setPasswordData({ ...passwordData, old_password: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">New Password</label>
                <input 
                  className="form-input" 
                  type="password" 
                  placeholder="••••••••" 
                  value={passwordData.new_password}
                  onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })}
                  required
                />
              </div>
            </div>
            <button 
              type="submit" 
              className="btn btn-teal" 
              style={{ marginTop: '1rem', width: '100%', padding: '0.8rem' }}
              disabled={saving}
            >
              {saving ? 'Updating...' : 'Change Password'}
            </button>
          </form>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Profile;