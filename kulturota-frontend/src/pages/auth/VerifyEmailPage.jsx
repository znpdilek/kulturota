import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { authService } from '../../services/authService';
import { useAuthStore } from '../../store/authStore';

const VerifyEmailPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const [status, setStatus] = useState('verifying');
  const [errorMessage, setErrorMessage] = useState('');
  const triggered = useRef(false);

  useEffect(() => {
    const token = searchParams.get('token');
    if (!token) {
      setStatus('error');
      setErrorMessage('Doğrulama bağlantısı eksik.');
      return;
    }
    if (triggered.current) return;
    triggered.current = true;

    (async () => {
      try {
        const response = await authService.verifyEmail(token);
        const data = response.data || {};
        login(data.access_token, data.user || null);
        setStatus('success');
        toast.success('E-postanız doğrulandı, hoş geldiniz!');
        setTimeout(() => navigate('/', { replace: true }), 1200);
      } catch (error) {
        const detail = error?.response?.data?.detail || 'Doğrulama başarısız oldu.';
        setStatus('error');
        setErrorMessage(detail);
        toast.error(detail);
      }
    })();
  }, [searchParams, login, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-cream">
      <div className="w-full max-w-md bg-sand p-10 rounded-organic shadow-card border border-stone-200 text-center">
        {status === 'verifying' && (
          <>
            <Loader2 className="w-12 h-12 text-sienna animate-spin mx-auto mb-4" />
            <h1 className="font-display text-2xl text-sienna mb-2">Hesabınız doğrulanıyor...</h1>
            <p className="font-body text-stone-600">Bir saniye, sizi içeri alıyoruz.</p>
          </>
        )}
        {status === 'success' && (
          <>
            <CheckCircle className="w-14 h-14 text-turquoise mx-auto mb-4" />
            <h1 className="font-display text-2xl text-sienna mb-2">Doğrulama tamamlandı!</h1>
            <p className="font-body text-stone-600">Ana sayfaya yönlendiriliyorsunuz...</p>
          </>
        )}
        {status === 'error' && (
          <>
            <XCircle className="w-14 h-14 text-rose-rug mx-auto mb-4" />
            <h1 className="font-display text-2xl text-sienna mb-2">Doğrulama başarısız</h1>
            <p className="font-body text-stone-700 mb-6">{errorMessage}</p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Link
                to="/kayit"
                className="inline-flex items-center justify-center gap-2 bg-sienna text-white px-5 py-2.5 rounded-organic font-ui font-semibold hover:bg-amber transition-all"
              >
                Yeniden kayıt ol
              </Link>
              <Link
                to="/giris"
                className="inline-flex items-center justify-center gap-2 bg-white border border-stone-200 text-stone-700 px-5 py-2.5 rounded-organic font-ui font-semibold hover:border-amber transition-all"
              >
                Giriş sayfası
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default VerifyEmailPage;
