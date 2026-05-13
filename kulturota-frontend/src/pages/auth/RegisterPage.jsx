import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Mail, CheckCircle, ExternalLink } from 'lucide-react';
import { authService } from '../../services/authService';

const isOver18 = (dateString) => {
  if (!dateString) return false;
  const today = new Date();
  const birthDate = new Date(dateString);
  let age = today.getFullYear() - birthDate.getFullYear();
  const m = today.getMonth() - birthDate.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
    age--;
  }
  return age >= 18;
};

const registerSchema = z.object({
  email: z.string().min(1, 'E-posta zorunludur').email('Geçerli bir e-posta adresi giriniz'),
  username: z
    .string()
    .min(3, 'Kullanıcı adı en az 3 karakter olmalıdır')
    .max(30, 'Kullanıcı adı en fazla 30 karakter olabilir')
    .regex(/^[a-zA-Z0-9_]+$/, 'Sadece harf, rakam ve alt çizgi kullanılabilir'),
  password: z
    .string()
    .min(6, 'Şifre en az 6 karakter olmalıdır')
    .max(128, 'Şifre en fazla 128 karakter olabilir'),
  birth_date: z
    .string()
    .min(1, 'Doğum tarihinizi giriniz')
    .refine(isOver18, { message: 'Kayıt olmak için 18 yaşından büyük olmalısınız' }),
  kvkk_approved: z.literal(true, { errorMap: () => ({ message: 'KVKK metnini onaylamanız zorunludur' }) }),
});

// Backend ProblemDetails.code → react-hook-form alanı eşlemesi.
const ERROR_FIELD_MAP = {
  'auth.email_taken': { field: 'email', message: 'Bu e-posta adresi zaten kayıtlı.' },
  'auth.username_taken': { field: 'username', message: 'Bu kullanıcı adı zaten alınmış.' },
  'auth.underage': { field: 'birth_date', message: 'Kayıt için 18 yaşından büyük olmalısınız.' },
  'auth.weak_password': { field: 'password', message: 'Şifre yeterince güçlü değil.' },
};

const RegisterPage = () => {
  const navigate = useNavigate();
  const [pendingVerification, setPendingVerification] = useState(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(registerSchema), mode: 'onTouched' });

  const onSubmit = async (data) => {
    try {
      const payload = {
        email: data.email,
        username: data.username,
        password: data.password,
        birth_date: data.birth_date,
        kvkk_consent: data.kvkk_approved,
      };

      const response = await authService.register(payload);
      setPendingVerification(response.data);
      toast.success('Kayıt başarılı! E-posta doğrulama bağlantısı oluşturuldu.');
    } catch (error) {
      const problem = error?.response?.data || {};
      const code = problem.code;
      const detail = problem.detail || 'Beklenmeyen bir hata oluştu.';

      const mapping = ERROR_FIELD_MAP[code];
      if (mapping) {
        setError(mapping.field, { type: 'server', message: mapping.message });
        toast.error(mapping.message);
        return;
      }

      // Pydantic 422 — alan bazlı hatalar
      if (problem.status === 422 && Array.isArray(problem.errors)) {
        let mapped = false;
        for (const err of problem.errors) {
          const loc = err?.loc || [];
          const fieldName = loc[loc.length - 1];
          if (
            fieldName &&
            ['email', 'username', 'password', 'birth_date'].includes(fieldName)
          ) {
            setError(fieldName, { type: 'server', message: err.msg });
            mapped = true;
          }
        }
        if (mapped) {
          toast.error('Lütfen formdaki hataları düzeltin.');
          return;
        }
      }

      toast.error(detail);
    }
  };

  if (pendingVerification) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-cream">
        <div className="w-full max-w-lg bg-sand p-8 md:p-12 rounded-organic shadow-card border border-stone-200 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-turquoise/10 rounded-full mb-6">
            <Mail className="text-turquoise" size={32} />
          </div>
          <h1 className="font-display text-display-lg text-sienna mb-3">E-postanızı doğrulayın</h1>
          <p className="font-body text-stone-700 mb-6 leading-relaxed">
            <strong>{pendingVerification.email}</strong> adresine bir doğrulama
            bağlantısı gönderdik. Hesabınızı aktif etmek ve KültürRota'ya giriş
            yapmak için bağlantıya tıklayın.
          </p>

          <div className="bg-white border border-stone-200 rounded-card p-4 text-left mb-6">
            <p className="font-ui text-xs text-stone-500 mb-2 uppercase tracking-wider">
              Demo modu — doğrulama bağlantısı
            </p>
            <a
              href={`/dogrula?token=${pendingVerification.verification_token}`}
              className="text-sienna hover:text-amber font-ui text-sm break-all inline-flex items-start gap-2"
            >
              <ExternalLink size={16} className="mt-0.5 shrink-0" />
              {pendingVerification.verification_url}
            </a>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to={`/dogrula?token=${pendingVerification.verification_token}`}
              className="inline-flex items-center justify-center gap-2 bg-sienna text-white px-6 py-3 rounded-organic font-ui font-semibold shadow-card hover:bg-amber transition-all"
            >
              <CheckCircle size={18} /> Hesabımı doğrula
            </Link>
            <Link
              to="/giris"
              className="inline-flex items-center justify-center gap-2 bg-white border border-stone-200 text-stone-700 px-6 py-3 rounded-organic font-ui font-semibold hover:border-amber transition-all"
            >
              Giriş sayfasına dön
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-cream">
      <div className="w-full max-w-lg bg-sand p-8 md:p-12 rounded-organic shadow-card border border-stone-200">
        <div className="text-center mb-8">
          <h1 className="font-display text-display-lg text-sienna mb-2">Kayıt Ol</h1>
          <p className="font-body text-stone-600">KültürRota topluluğuna katılın.</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
          <div>
            <label className="block font-ui text-ui-sm text-stone-800 mb-1">E-posta</label>
            <input
              {...register('email')}
              type="email"
              autoComplete="email"
              aria-invalid={!!errors.email}
              className={`w-full bg-white border p-3 rounded-card focus:outline-none focus:ring-2 transition-all ${
                errors.email
                  ? 'border-rose-rug focus:ring-rose-rug/20 focus:border-rose-rug'
                  : 'border-stone-200 focus:ring-amber/20 focus:border-amber'
              }`}
            />
            {errors.email && (
              <p className="text-rose-rug text-ui-xs mt-1" role="alert">
                {errors.email.message}
              </p>
            )}
          </div>

          <div>
            <label className="block font-ui text-ui-sm text-stone-800 mb-1">Kullanıcı Adı</label>
            <input
              {...register('username')}
              autoComplete="username"
              aria-invalid={!!errors.username}
              className={`w-full bg-white border p-3 rounded-card focus:outline-none focus:ring-2 transition-all ${
                errors.username
                  ? 'border-rose-rug focus:ring-rose-rug/20 focus:border-rose-rug'
                  : 'border-stone-200 focus:ring-amber/20 focus:border-amber'
              }`}
            />
            {errors.username ? (
              <p className="text-rose-rug text-ui-xs mt-1" role="alert">
                {errors.username.message}
              </p>
            ) : (
              <p className="text-stone-500 text-ui-xs mt-1">
                3-30 karakter; harf, rakam ve alt çizgi.
              </p>
            )}
          </div>

          <div>
            <label className="block font-ui text-ui-sm text-stone-800 mb-1">Şifre</label>
            <input
              {...register('password')}
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.password}
              className={`w-full bg-white border p-3 rounded-card focus:outline-none focus:ring-2 transition-all ${
                errors.password
                  ? 'border-rose-rug focus:ring-rose-rug/20 focus:border-rose-rug'
                  : 'border-stone-200 focus:ring-amber/20 focus:border-amber'
              }`}
            />
            {errors.password ? (
              <p className="text-rose-rug text-ui-xs mt-1" role="alert">
                {errors.password.message}
              </p>
            ) : (
              <p className="text-stone-500 text-ui-xs mt-1">En az 6 karakter giriniz.</p>
            )}
          </div>

          <div>
            <label className="block font-ui text-ui-sm text-stone-800 mb-1">Doğum Tarihi</label>
            <input
              {...register('birth_date')}
              type="date"
              aria-invalid={!!errors.birth_date}
              className={`w-full bg-white border p-3 rounded-card focus:outline-none focus:ring-2 transition-all ${
                errors.birth_date
                  ? 'border-rose-rug focus:ring-rose-rug/20 focus:border-rose-rug'
                  : 'border-stone-200 focus:ring-amber/20 focus:border-amber'
              }`}
            />
            {errors.birth_date && (
              <p className="text-rose-rug text-ui-xs mt-1" role="alert">
                {errors.birth_date.message}
              </p>
            )}
          </div>

          <div className="pt-2">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                {...register('kvkk_approved')}
                className="mt-1 w-4 h-4 text-sienna border-stone-300 rounded focus:ring-sienna"
              />
              <span className="font-ui text-ui-sm text-stone-600">
                <a href="#" className="text-sienna underline">
                  KVKK Aydınlatma Metnini
                </a>{' '}
                okudum ve onaylıyorum.
              </span>
            </label>
            {errors.kvkk_approved && (
              <p className="text-rose-rug text-ui-xs mt-1" role="alert">
                {errors.kvkk_approved.message}
              </p>
            )}
          </div>

          <button
            disabled={isSubmitting}
            type="submit"
            className="w-full bg-sienna text-white py-4 mt-4 rounded-organic font-ui font-semibold shadow-card hover:bg-amber transition-all disabled:opacity-50"
          >
            {isSubmitting ? 'Hesap Oluşturuluyor...' : 'Hesap Oluştur'}
          </button>
        </form>

        <p className="text-center mt-6 font-ui text-ui-sm text-stone-600">
          Zaten hesabınız var mı?{' '}
          <Link to="/giris" className="text-sienna font-semibold hover:underline">
            Giriş Yapın
          </Link>
        </p>
      </div>
    </div>
  );
};

export default RegisterPage;
