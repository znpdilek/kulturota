import api from './api';

export const placeService = {
  list: (params) => api.get('/places', { params }),
  detail: (id) => api.get(`/places/${id}`),
  getReviews: (id) => api.get(`/places/${id}/reviews`),
  addReview: (id, data) => api.post(`/places/${id}/reviews`, data),
  
  // Fotoğraf Yükleme Servisi
  uploadPhoto: (formData) => api.post('/photos', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  }),
};