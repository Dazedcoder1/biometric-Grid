// src/pages/org/Tasks.jsx
import React from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import TaskBoard from '../../components/TaskBoard';
import { orgTaskApi } from '../../services/api';

const Tasks = () => (
  <DashboardLayout
    title="Tasks"
    role="orgadmin"
    label="Department Admin"
    abbr="DA"
    color="#00d4aa"
    bgColor="rgba(0,212,170,0.15)"
  >
    <TaskBoard
      api={orgTaskApi}
      canCreate
      canAssign
      canDelete
    />
  </DashboardLayout>
);

export default Tasks;
