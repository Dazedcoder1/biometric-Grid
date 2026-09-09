import os

files = {
    'src/pages/tenant/Devices.jsx': ('Devices (Global)', 'superadmin', 'Tenant Admin', 'TA', '#a855f7', 'rgba(168,85,247,0.15)'),
    'src/pages/tenant/Activity.jsx': ('Activity Log', 'superadmin', 'Tenant Admin', 'TA', '#a855f7', 'rgba(168,85,247,0.15)'),
    'src/pages/tenant/Settings.jsx': ('System Settings', 'superadmin', 'Tenant Admin', 'TA', '#a855f7', 'rgba(168,85,247,0.15)'),
    'src/pages/employee/Attendance.jsx': ('Attendance List', 'user', 'Employee', 'EM', '#f59e0b', 'rgba(245,158,11,0.15)'),
    'src/pages/employee/Holidays.jsx': ('Holidays', 'user', 'Employee', 'EM', '#f59e0b', 'rgba(245,158,11,0.15)'),
    'src/pages/org/Employees.jsx': ('All Employees', 'orgadmin', 'Department Admin', 'DA', '#00d4aa', 'rgba(0,212,170,0.15)'),
    'src/pages/org/Attendance.jsx': ('Attendance List', 'orgadmin', 'Department Admin', 'DA', '#00d4aa', 'rgba(0,212,170,0.15)'),
    'src/pages/org/Today.jsx': ('Today Attendance', 'orgadmin', 'Department Admin', 'DA', '#00d4aa', 'rgba(0,212,170,0.15)'),
    'src/pages/org/Leaves.jsx': ('Leave Requests', 'orgadmin', 'Department Admin', 'DA', '#00d4aa', 'rgba(0,212,170,0.15)'),
    'src/pages/org/ReportAtt.jsx': ('Attendance Report', 'orgadmin', 'Department Admin', 'DA', '#00d4aa', 'rgba(0,212,170,0.15)'),
    'src/pages/org/ReportLeave.jsx': ('Leave Report', 'orgadmin', 'Department Admin', 'DA', '#00d4aa', 'rgba(0,212,170,0.15)'),
    'src/pages/org/Devices.jsx': ('Devices', 'orgadmin', 'Department Admin', 'DA', '#00d4aa', 'rgba(0,212,170,0.15)'),
    'src/pages/org/Settings.jsx': ('Settings', 'orgadmin', 'Department Admin', 'DA', '#00d4aa', 'rgba(0,212,170,0.15)'),
    'src/pages/org/Activity.jsx': ('Activity Log', 'orgadmin', 'Department Admin', 'DA', '#00d4aa', 'rgba(0,212,170,0.15)')
}

for path, (title, role, label, abbr, color, bgColor) in files.items():
    content = f"""import React from 'react';
import PlaceholderPage from '../../components/PlaceholderPage';

const Page = () => (
    <PlaceholderPage 
        title='{title}' 
        role='{role}' 
        label='{label}' 
        abbr='{abbr}' 
        color='{color}' 
        bgColor='{bgColor}' 
    />
);

export default Page;
"""
    # Ensure directory exists just in case
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
print("Successfully fixed encodings for all sub-pages.")
