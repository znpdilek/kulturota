import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { AlertCircle } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { authService } from '../../services/authService';

const loginSchema = z.object({
  identifier: z.string().min(3, 'E-posta veya kullanıcı adı en az 3 karakter olmalıdır'),
  password: z.string().min(1, 'Şifre zorunludur'),
});

const FIELD_ERROR_MAP = {
  'auth.invalid_credentials': { field: 'identifier', message: 'Böyle bir kullanıcı bulunamadı. Bilgileri kontrol edin.' },
  'auth.invalid_password': { field: 'password', message: 'Girdiğiniz şifre hatalı.' },
};

const LoginPage = () => {
  const login = useAuthStore((state) => state.login);
  const [emailUnverified, setEmailUnverified] = useState(null);
  const [resending, setResending] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(loginSchema), mode: 'onTouched' });

  const onSubmit = async (data) => {
    setEmailUnverified(null);
    try {
      const response = await authService.login(data);
      const tokens = response.data || {};
      login(tokens.access_token, tokens.user || null);
      toast.success('Hoş geldiniz!');
    } catch (error) {
      const problem = error?.response?.data || {};
      const code = problem.code;

      if (code === 'auth.email_not_verified') {
        setEmailUnverified(problem.email || getValues('identifier'));
        toast.error('E-posta doğrulaması gerekiyor.');
        return;
      }

      const mapping = FIELD_ERROR_MAP[code];
      if (mapping) {
        setError(mapping.field, { type: 'server', message: mapping.message });
        toast.error(mapping.message);
        return;
      }

      toast.error(problem.detail || 'Giriş başarısız. Lütfen tekrar deneyin.');
    }
  };

  const handleResend = async () => {
    if (!emailUnverified) return;
    setResending(true);
    try {
      const response = await authService.resendVerification(emailUnverified);
      const link = response.data?.verification_url;
      if (link) {
        toast.success('Yeni doğrulama bağlantısı oluşturuldu.');
        window.open(link, '_blank', 'noopener');
      } else {
        toast.success('Doğrulama maili (varsa) tekrar gönderildi.');
      }
    } catch {
      toast.error('Doğrulama bağlantısı oluşturulamadı.');
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="hidden lg:block bg-stone-800 relative overflow-hidden">
        <img
          src="https://images.unsplash.com/photo-1541432901042-2d8bd64b4a9b?q=80&w=1920&auto=format&fit=crop"
          alt="Antik Doku"
          className="absolute inset-0 w-full h-full object-cover opacity-60 mix-blend-overlay"
        />
        <div className="absolute inset-0 flex items-center justify-center p-12 bg-gradient-to-t from-obsidian/80 to-transparent">
          <div className="text-white max-w-md">
            <h2 className="font-display text-display-xl mb-4 italic">"Geçmişin izini bugünle sürün."</h2>
            <p className="font-body text-stone-300">
              KültürRota ile Türkiye'nin saklı miraslarını keşfetmeye kaldığınız yerden devam edin.
            </p>
          </div>
        </div>
      </div>

      <div className="bg-cream flex items-center justify-center p-8 lg:p-24">
        <div className="w-full max-w-md">
          <h1 className="font-display text-display-lg text-sienna mb-2">Giriş Yap</h1>
          <p className="font-body text-stone-600 mb-8">Hafızayı keşfetmeye hazır mısınız?</p>

          {emailUnverified && (
            <div className="mb-6 bg-amber/10 border border-amber/40 rounded-card p-4 flex gap-3">
              <AlertCircle className="text-amber w-5 h-5 mt-0.5 shrink-0" />
              <div className="flex-grow">
                <p className="font-ui text-sm text-stone-800 font-semibold mb-1">
                  E-postanızı doğrulamanız gerekiyor
                </p>
                <p className="font-ui text-xs text-stone-600 mb-2">
                  <strong>{emailUnverified}</strong> için doğrulama bağlantısı bekleniyor.
                </p>
                <button
                  onClick={handleResend}
                  disabled={resending}
                  type="button"
                  className="font-ui text-sm text-sienna hover:text-amber font-semibold underline disabled:opacity-50"
                >
                  {resending ? 'Gönderiliyor...' : 'Yeniden gönder'}
                </button>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6" noValidate>
            <div>
              <label className="block font-ui text-ui-sm text-stone-800 mb-2">
                E-posta veya Kullanıcı Adı
              </label>
              <input
                {...register('identifier')}
                aria-invalid={!!errors.identifier}
                className={`w-full bg-white border p-3 rounded-card focus:outline-none focus:ring-2 transition-all ${
                  errors.identifier
                    ? 'border-rose-rug focus:ring-rose-rug/20 focus:border-rose-rug'
                    : 'border-stone-200 focus:ring-amber/20 focus:border-amber'
                }`}
                placeholder="zeyne@kulturrota.com"
              />
              {errors.identifier && (
                <p className="text-rose-rug text-ui-xs mt-1" role="alert">
                  {errors.identifier.message}
                </p>
              )}
            </div>

            <div>
              <label className="block font-ui text-ui-sm text-stone-800 mb-2">Şifre</label>
              <input
                {...register('password')}
                type="password"
                aria-invalid={!!errors.password}
                className={`w-full bg-white border p-3 rounded-card focus:outline-none focus:ring-2 transition-all ${
                  errors.password
                    ? 'border-rose-rug focus:ring-rose-rug/20 focus:border-rose-rug'
                    : 'border-stone-200 focus:ring-amber/20 focus:border-amber'
                }`}
                placeholder="••••••••"
              />
              {errors.password && (
                <p className="text-rose-rug text-ui-xs mt-1" role="alert">
                  {errors.password.message}
                </p>
              )}
            </div>

            <button
              disabled={isSubmitting}
              type="submit"
              className="w-full bg-sienna text-white py-4 rounded-organic font-ui font-semibold shadow-card hover:bg-amber transition-all disabled:opacity-50"
            >
              {isSubmitting ? 'Giriş Yapılıyor...' : 'Giriş Yap'}
            </button>
          </form>

          <p className="text-center mt-6 font-ui text-ui-sm text-stone-600">
            Hesabınız yok mu?{' '}
            <Link to="/kayit" className="text-sienna font-semibold hover:underline">
              Kayıt Olun
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
