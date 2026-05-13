import axios from 'axios';
import { useAuthStore } from '../store/authStore';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 10000,
});

// İstek gönderilmeden önce bilet yapıştırıcı (Interceptor)
api.interceptors.request.use((config) => {
  // Hafızadan bilet olabilecek tüm ihtimalleri deniyoruz
  const state = useAuthStore.getState();
  const token = state.token || state.accessToken; 
  
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
    console.log("✈️ İstek gönderiliyor, bilet yapıştırıldı.");
  } else {
    console.warn("⚠️ Dikkat: Hafızada bilet (token) bulunamadı!");
  }
  return config;
});

// Yanıt geldiğinde hata yönetimi
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    // Sadece bilet geçersizse (401) giriş sayfasına at
    if (err.response?.status === 401) {
      console.error("🚫 Bilet geçersiz (401). Giriş sayfasına yönlendiriliyorsunuz.");
      useAuthStore.getState().logout();
      window.location.href = '/giris';
    }
    return Promise.reject(err);
  }
);

export default api;