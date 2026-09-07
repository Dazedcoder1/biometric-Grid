// src/pages/tenant/Tasks.jsx
import React from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import TaskBoard from '../../components/TaskBoard';
import { tenantTaskApi } from '../../services/api';

const Tasks = () => (
  <DashboardLayout
    title="Tasks"
    role="superadmin"
    label="Tenant Admin"
    abbr="TA"
    color="#a855f7"
    bgColor="rgba(168,85,247,0.15)"
  >
    <TaskBoard
      api={tenantTaskApi}
      canCreate
      canAssign
      canDelete
    />
  </DashboardLayout>
);

export default Tasks;
