import api from './api';

export const authService = {
  login: (data) => api.post('/auth/login', data),
  register: (data) => api.post('/auth/register', data), // Bu satırı ekledik
  getMe: () => api.get('/users/me'),
};