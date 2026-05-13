import { create } from 'zustand';

export const useRouteStore = create((set) => ({
  routeStops: [], // Seçilen mekanların listesi
  
  // Mekan ekle (Eğer zaten ekliyse ekleme)
  addStop: (place) => set((state) => {
    if (state.routeStops.some(stop => stop.id === place.id)) return state;
    return { routeStops: [...state.routeStops, place] };
  }),
  
  // Mekanı rotadan çıkar
  removeStop: (placeId) => set((state) => ({
    routeStops: state.routeStops.filter(stop => stop.id !== placeId)
  })),
  
  // Rotayı tamamen temizle
  clearRoute: () => set({ routeStops: [] }),
}));