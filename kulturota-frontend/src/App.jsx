import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import Navbar from './components/layout/Navbar';
import AuthGuard from './components/layout/AuthGuard';
import ExplorePage from './pages/explore/ExplorePage';
import RouteBuilderPage from './pages/route/RouteBuilderPage'; // Eklemeyi unuttuğu sayfa
import { useAuthStore } from './store/authStore';
import MyRoutesPage from './pages/route/MyRoutesPage';
import RouteDetailPage from './pages/route/RouteDetailPage';
import PlaceDetailPage from './pages/explore/PlaceDetailPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});

const HomePage = () => (
  <div className="min-h-[calc(100vh-5rem)] bg-cream flex flex-col items-center justify-center p-6">
    <div className="bg-sand p-10 rounded-organic shadow-card border border-stone-200 text-center max-w-2xl">
      <h1 className="text-display-xl font-display text-sienna mb-4">Anadolu'nun Hafızasını Keşfet</h1>
      <p className="text-body-lg text-stone-600 mb-8">
        Kültürel miras mekanlarını keşfet, kendi rotanı çiz, deneyimini paylaş.
      </p>
    </div>
  </div>
);

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

              {/* Rota Oluşturucuyu Tekrar Tanıttık */}
              <Route element={<AuthGuard />}>
                <Route path="/rota-olustur" element={<RouteBuilderPage />} />
                <Route path="/rotalarim" element={<MyRoutesPage />} />
                <Route path="/mekanlar/:id" element={<PlaceDetailPage />} />
                {/* YENİ EKLENEN DETAY SAYFASI */}
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