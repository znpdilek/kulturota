import api from './api';

export const routeService = {
  create: (data) => api.post('/routes', data),
  list: () => api.get('/routes'),
  detail: (id) => api.get(`/routes/${id}`),
  // Rotaya mekan ekleme servisi
  addStop: (routeId, data) => api.post(`/routes/${routeId}/stops`, data),
  getStops: (routeId) => api.get(`/routes/${routeId}/stops`),
};