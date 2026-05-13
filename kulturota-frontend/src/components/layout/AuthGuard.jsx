import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

const AuthGuard = () => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  // Kullanıcı giriş yapmamışsa login'e at
  if (!isAuthenticated) {
    return <Navigate to="/giris" replace />;
  }

  // Giriş yapmışsa gitmek istediği sayfayı (Outlet) göster
  return <Outlet />;
};

export default AuthGuard;