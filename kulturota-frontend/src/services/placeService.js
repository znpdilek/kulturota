import api from './api';

export const placeService = {
  list: (params) => api.get('/places', { params }),
  detail: (id) => api.get(`/places/${id}`),
  getReviews: (id, params) => api.get(`/places/${id}/reviews`, { params }),
  addReview: (id, data) => api.post(`/places/${id}/reviews`, data),

  getPhotos: (id, params) => api.get(`/places/${id}/photos`, { params }),
  uploadPhoto: (formData) =>
    api.post('/photos', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
};
