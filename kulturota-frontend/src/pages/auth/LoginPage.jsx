import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useAuthStore } from '../../store/authStore';
import { authService } from '../../services/authService';
import toast from 'react-hot-toast';

const loginSchema = z.object({
  identifier: z.string().min(3, 'E-posta veya kullanıcı adı en az 3 karakter olmalıdır'),
  password: z.string().min(1, 'Şifre zorunludur'),
});

const LoginPage = () => {
  const login = useAuthStore((state) => state.login);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data) => {
    try {
      const response = await authService.login(data);
      login(response.data.access_token, response.data.user);
      toast.success('Hoş geldiniz!');
    } catch (error) {
      toast.error('Giriş başarısız. Lütfen bilgilerinizi kontrol edin.');
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Sol Panel: Görsel */}
      <div className="hidden lg:block bg-stone-800 relative overflow-hidden">
        <img 
          src="https://images.unsplash.com/photo-1541432901042-2d8bd64b4a9b?q=80&w=1920&auto=format&fit=crop" 
          alt="Antik Doku"
          className="absolute inset-0 w-full h-full object-cover opacity-60 mix-blend-overlay"
        />
        <div className="absolute inset-0 flex items-center justify-center p-12 bg-gradient-to-t from-obsidian/80 to-transparent">
          <div className="text-white max-w-md">
            <h2 className="font-display text-display-xl mb-4 italic">"Geçmişin izini bugünle sürün."</h2>
            <p className="font-body text-stone-300">KültürRota ile Türkiye'nin saklı miraslarını keşfetmeye kaldığınız yerden devam edin.</p>
          </div>
        </div>
      </div>

      {/* Sağ Panel: Form */}
      <div className="bg-cream flex items-center justify-center p-8 lg:p-24">
        <div className="w-full max-w-md">
          <h1 className="font-display text-display-lg text-sienna mb-2">Giriş Yap</h1>
          <p className="font-body text-stone-600 mb-8">Hafızayı keşfetmeye hazır mısınız?</p>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            <div>
              <label className="block font-ui text-ui-sm text-stone-800 mb-2">E-posta veya Kullanıcı Adı</label>
              <input 
                {...register('identifier')}
                className="w-full bg-white border border-stone-200 p-3 rounded-card focus:outline-none focus:ring-2 focus:ring-amber/20 focus:border-amber transition-all"
                placeholder="zeyne@kulturrota.com"
              />
              {errors.identifier && <p className="text-rose-rug text-ui-xs mt-1">{errors.identifier.message}</p>}
            </div>

            <div>
              <label className="block font-ui text-ui-sm text-stone-800 mb-2">Şifre</label>
              <input 
                {...register('password')}
                type="password"
                className="w-full bg-white border border-stone-200 p-3 rounded-card focus:outline-none focus:ring-2 focus:ring-amber/20 focus:border-amber transition-all"
                placeholder="••••••••"
              />
              {errors.password && <p className="text-rose-rug text-ui-xs mt-1">{errors.password.message}</p>}
            </div>

            <button 
              disabled={isSubmitting}
              type="submit"
              className="w-full bg-sienna text-white py-4 rounded-organic font-ui font-semibold shadow-card hover:bg-amber transition-all disabled:opacity-50"
            >
              {isSubmitting ? 'Giriş Yapılıyor...' : 'Giriş Yap'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;