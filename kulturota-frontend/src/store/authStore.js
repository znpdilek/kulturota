import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const useAuthStore = create(
  // persist: Sayfa yenilense bile (F5) girişin açık kalmasını sağlar
  persist(
    (set) => ({
      accessToken: null,
      user: null,
      isAuthenticated: false,

      // Login fonksiyonunu her duruma karşı korumalı hale getirdik
      login: (tokenData, userData) => {
        // Gelen veri ister string olsun, ister obje; bileti garantili alıyoruz
        const token = typeof tokenData === 'string' ? tokenData : (tokenData?.access_token || tokenData?.accessToken);
        
        set({
          accessToken: token,
          user: userData || null,
          isAuthenticated: true,
        });
      },

      logout: () => {
        set({
          accessToken: null,
          user: null,
          isAuthenticated: false,
        });
      },
    }),
    {
      name: 'kultur-rota-auth', // Tarayıcının yerel hafızasına (localStorage) kaydedilecek isim
    }
  )
);