import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import VerifyEmailPage from './pages/auth/VerifyEmailPage';
import Navbar from './components/layout/Navbar';
import AuthGuard from './components/layout/AuthGuard';
import ExplorePage from './pages/explore/ExplorePage';
import RouteBuilderPage from './pages/route/RouteBuilderPage';
import { useAuthStore } from './store/authStore';
import MyRoutesPage from './pages/route/MyRoutesPage';
import RouteDetailPage from './pages/route/RouteDetailPage';
import PlaceDetailPage from './pages/explore/PlaceDetailPage';
import HomePage from './pages/HomePage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});

function App() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Toaster position="top-right" />
        <div className="flex flex-col min-h-screen">
          <Navbar />
          <main className="flex-grow">
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/kesfet" element={<ExplorePage />} />

              <Route path="/giris" element={!isAuthenticated ? <LoginPage /> : <Navigate to="/" />} />
              <Route path="/kayit" element={!isAuthenticated ? <RegisterPage /> : <Navigate to="/" />} />
              <Route path="/dogrula" element={<VerifyEmailPage />} />

              <Route element={<AuthGuard />}>
                <Route path="/rota-olustur" element={<RouteBuilderPage />} />
                <Route path="/rotalarim" element={<MyRoutesPage />} />
                <Route path="/mekanlar/:id" element={<PlaceDetailPage />} />
                <Route path="/rotalar/:id" element={<RouteDetailPage />} />
              </Route>
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
