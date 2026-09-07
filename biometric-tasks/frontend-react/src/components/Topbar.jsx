// src/components/Topbar.jsx
import React, { useState, useEffect, useRef } from 'react';
import { Moon, Sun, Bell, Menu, User, LogOut } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useTheme } from '../context/ThemeContext';
import { employeeApi, notificationsAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

const Topbar = ({ title, userAbbr, bgColor, iconColor, role }) => {
  const { theme, toggleTheme } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [showNotifs, setShowNotifs] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef(null);
  const userMenuRef = useRef(null);

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowNotifs(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setShowUserMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Fetch notifications when dropdown opens or periodically
  useEffect(() => {
    if (showNotifs) {
      fetchNotifications();
    }
  }, [showNotifs]);

  // Fetch unread count periodically
  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const data = await notificationsAPI.getNotifications(20);
      console.log('Notifications:', data);
      setNotifications(data || []);
    } catch (err) {
      console.error('Failed to fetch notifications:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchUnreadCount = async () => {
    try {
      const data = await notificationsAPI.getUnreadCount();
      setUnreadCount(data.count || 0);
    } catch (err) {
      console.error('Failed to fetch unread count:', err);
    }
  };

  const handleMarkAsRead = async (notificationId) => {
    try {
      await notificationsAPI.markNotificationRead(notificationId);
      setNotifications(prev => 
        prev.map(notif => 
          notif.notification_id === notificationId 
            ? { ...notif, is_read: true } 
            : notif
        )
      );
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch (err) {
      console.error('Failed to mark as read:', err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await notificationsAPI.markAllRead();
      setNotifications(prev => 
        prev.map(notif => ({ ...notif, is_read: true }))
      );
      setUnreadCount(0);
    } catch (err) {
      console.error('Failed to mark all as read:', err);
    }
  };

  const handleToggleSidebar = () => {
    const sb = document.getElementById('sidebar');
    const bd = document.getElementById('sb-backdrop');
    if (window.innerWidth <= 768) {
      if (sb) sb.classList.toggle('open');
      if (bd) bd.classList.toggle('visible');
    } else {
      if (sb) sb.classList.toggle('collapsed');
    }
  };

  const handleLogout = () => {
    logout();
  };

  // Get profile path based on role
  const getProfilePath = () => {
    switch (role) {
      case 'superadmin':
        return '/super/profile';
      case 'orgadmin':
        return '/org/profile';
      case 'user':
        return '/emp/profile';
      default:
        return '/';
    }
  };

  // Get display name/abbreviation
  const getDisplayAbbr = () => {
    if (userAbbr) return userAbbr;
    if (user?.name) return user.name.charAt(0).toUpperCase();
    if (user?.email) return user.email.charAt(0).toUpperCase();
    return 'U';
  };

  // Format time without numbers - just relative descriptions
  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffHours < 1) return 'Recent';
    if (diffHours < 2) return 'Earlier today';
    if (diffHours < 6) return 'Earlier today';
    if (diffHours < 12) return 'Earlier today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return 'This week';
    if (diffDays < 14) return 'Last week';
    if (diffDays < 30) return 'This month';
    return 'Earlier';
  };

  const getNotificationIcon = (eventType) => {
    switch (eventType) {
      case 'leave_requested':
      case 'leave_submitted':
        return '📋';
      case 'leave_approved':
      case 'leave_approved_final':
        return '✅';
      case 'leave_rejected':
        return '❌';
      case 'attendance_marked':
        return '⏰';
      case 'late_arrival':
        return '⚠️';
      case 'employee_added':
        return '👥';
      case 'employee_deactivated':
        return '🔴';
      case 'fingerprint_enrolled':
        return '🖐️';
      default:
        return '🔔';
    }
  };

  return (
    <div className="topbar">
      <button 
        className="tb-action-icon tb-hamburger" 
        onClick={(e) => { e.stopPropagation(); handleToggleSidebar(); }}
        style={{ marginRight: '10px', fontSize: '1.4rem' }}
      >
        <Menu size={22} />
      </button>
      <span className="tb-title">{title}</span>

      <div style={{ flex: 1 }}></div>

      <button 
        className="tb-action-icon theme-toggle" 
        onClick={toggleTheme}
        title="Toggle Light/Dark Mode"
      >
        {theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
      </button>

      <div 
        className="tb-notif tb-action-icon" 
        onClick={(e) => { e.stopPropagation(); setShowNotifs(!showNotifs); }}
        ref={dropdownRef}
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <div className="tb-notif-badge" style={{ 
            position: 'absolute', 
            top: '0px', 
            right: '0px',
            width: '16px',
            height: '16px',
            background: '#ef4444',
            borderRadius: '50%',
            fontSize: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white'
          }}>
            {unreadCount > 9 ? '9+' : unreadCount}
          </div>
        )}
        
        {showNotifs && (
          <div className="notif-dropdown" onClick={(e) => e.stopPropagation()}>
            <div className="table-header" style={{ justifyContent: 'space-between', paddingBottom: '0.5rem' }}>
              <span className="table-title">Notifications</span>
              {unreadCount > 0 && (
                <button 
                  className="btn btn-ghost" 
                  onClick={handleMarkAllRead}
                  style={{ fontSize: '0.7rem', padding: '0.2rem 0.5rem' }}
                >
                  Mark all read
                </button>
              )}
            </div>
            
            {loading ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text3)' }}>
                Loading...
              </div>
            ) : notifications.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text3)' }}>
                No notifications
              </div>
            ) : (
              notifications.map((notif) => (
                <div 
                  key={notif.notification_id} 
                  className="notif-item"
                  style={{ 
                    background: notif.is_read ? 'transparent' : 'rgba(0,212,170,0.05)',
                    cursor: 'pointer'
                  }}
                  onClick={() => !notif.is_read && handleMarkAsRead(notif.notification_id)}
                >
                  <div className="notif-dot" style={{ 
                    background: notif.is_read ? 'var(--text3)' : '#00d4aa',
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    marginTop: '5px',
                    flexShrink: 0
                  }}></div>
                  <div style={{ flex: 1 }}>
                    <div className="notif-text" style={{ fontWeight: notif.is_read ? 'normal' : '500' }}>
                      <span style={{ marginRight: '6px' }}>{getNotificationIcon(notif.event_type)}</span>
                      {notif.title || notif.message || notif.entity_name}
                    </div>
                    <div className="notif-time" style={{ marginTop: '4px' }}>
                      {formatTime(notif.created_at)}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* User Menu Dropdown */}
      <div className="user-menu-container" ref={userMenuRef}>
        <div 
          className="avatar" 
          style={{ background: bgColor, color: iconColor, cursor: 'pointer' }}
          onClick={() => setShowUserMenu(!showUserMenu)}
        >
          {getDisplayAbbr()}
        </div>
        
        {showUserMenu && (
          <div className="user-dropdown">
            <div className="user-dropdown-header">
              <div className="user-dropdown-avatar" style={{ background: bgColor, color: iconColor }}>
                {getDisplayAbbr()}
              </div>
              <div className="user-dropdown-info">
                <div className="user-dropdown-name">{user?.name || 'User'}</div>
                <div className="user-dropdown-role">
                  {role === 'superadmin' ? 'Tenant Admin' : role === 'orgadmin' ? 'Org Admin' : 'Employee'}
                </div>
              </div>
            </div>
            <div className="user-dropdown-divider"></div>
            <Link 
              to={getProfilePath()} 
              className="user-dropdown-item" 
              onClick={() => setShowUserMenu(false)}
            >
              <User size={16} />
              <span>Profile</span>
            </Link>
            <button 
              className="user-dropdown-item" 
              onClick={handleLogout}
            >
              <LogOut size={16} />
              <span>Sign Out</span>
            </button>
          </div>
        )}
      </div>

      <style>{`
        .user-menu-container {
          position: relative;
        }
        
        .user-dropdown {
          position: absolute;
          top: calc(100% + 8px);
          right: 0;
          width: 260px;
          background: var(--bg2);
          border: 1px solid var(--border);
          border-radius: 12px;
          box-shadow: 0 10px 25px rgba(0,0,0,0.3);
          z-index: 1000;
          overflow: hidden;
          animation: slideDown 0.2s ease;
        }
        
        @keyframes slideDown {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        
        .user-dropdown-header {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 16px;
          background: var(--bg3);
        }
        
        .user-dropdown-avatar {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1rem;
          font-weight: 600;
        }
        
        .user-dropdown-info {
          flex: 1;
        }
        
        .user-dropdown-name {
          font-size: 0.9rem;
          font-weight: 600;
          color: var(--text);
        }
        
        .user-dropdown-role {
          font-size: 0.7rem;
          color: var(--text3);
          margin-top: 2px;
        }
        
        .user-dropdown-divider {
          height: 1px;
          background: var(--border);
          margin: 4px 0;
        }
        
        .user-dropdown-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 16px;
          color: var(--text2);
          text-decoration: none;
          transition: all 0.2s;
          cursor: pointer;
          background: none;
          border: none;
          width: 100%;
          text-align: left;
          font-size: 0.85rem;
          font-family: inherit;
        }
        
        .user-dropdown-item:hover {
          background: var(--bg3);
          color: var(--text);
        }
        
        .avatar {
          cursor: pointer;
          transition: transform 0.2s;
        }
        
        .avatar:hover {
          transform: scale(1.05);
        }
      `}</style>
    </div>
  );
};

export default Topbar;