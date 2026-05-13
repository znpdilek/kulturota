import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Link, useNavigate } from 'react-router-dom';
import { authService } from '../../services/authService';
import { useAuthStore } from '../../store/authStore';
import toast from 'react-hot-toast';

// 18+ yaş kontrolü için yardımcı fonksiyon (PRD 5.2.2)
const isOver18 = (dateString) => {
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
  email: z.string().email('Geçerli bir e-posta adresi giriniz'),
  username: z.string()
    .min(3, 'En az 3 karakter')
    .max(30, 'En fazla 30 karakter')
    .regex(/^[a-zA-Z0-9_]+$/, 'Sadece harf, rakam ve alt çizgi kullanılabilir'),
  password: z.string().min(10, 'Şifre en az 10 karakter olmalıdır'),
  birth_date: z.string().refine(isOver18, { message: 'Kayıt olmak için 18 yaşından büyük olmalısınız' }),
  kvkk_approved: z.literal(true, { errorMap: () => ({ message: 'KVKK metnini onaylamanız zorunludur' }) })
});

const RegisterPage = () => {
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (data) => {
    try {
      const payload = {
        email: data.email,
        username: data.username,
        password: data.password,
        birth_date: data.birth_date,
        kvkk_consent: data.kvkk_approved // İŞTE EKSİK OLAN ANAHTAR!
      };
      
      const response = await authService.register(payload);
      
      // ... (kodun geri kalanı aynı)
      const loginResponse = await authService.login({
        identifier: data.email,
        password: data.password
      });
      
      login(loginResponse.data.access_token, loginResponse.data.user);
      toast.success('Hesabınız başarıyla oluşturuldu!');
      navigate('/');
    } catch (error) {
      // 🕵️‍♂️ İŞTE AJANIMIZ BURADA: FastAPI'nin hatasını doğrudan konsola basıyoruz
      console.error("🕵️‍♂️ BACKEND'DEN GELEN HATA DETAYI:", error.response?.data);
      
      toast.error('Kayıt reddedildi! Lütfen F12 Console sekmesine bakın.');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-cream">
      <div className="w-full max-w-lg bg-sand p-8 md:p-12 rounded-organic shadow-card border border-stone-200">
        <div className="text-center mb-8">
          <h1 className="font-display text-display-lg text-sienna mb-2">Kayıt Ol</h1>
          <p className="font-body text-stone-600">KültürRota topluluğuna katılın.</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          <div>
            <label className="block font-ui text-ui-sm text-stone-800 mb-1">E-posta</label>
            <input 
              {...register('email')}
              type="email"
              className="w-full bg-white border border-stone-200 p-3 rounded-card focus:outline-none focus:ring-2 focus:ring-amber/20 focus:border-amber transition-all"
            />
            {errors.email && <p className="text-rose-rug text-ui-xs mt-1">{errors.email.message}</p>}
          </div>

          <div>
            <label className="block font-ui text-ui-sm text-stone-800 mb-1">Kullanıcı Adı</label>
            <input 
              {...register('username')}
              className="w-full bg-white border border-stone-200 p-3 rounded-card focus:outline-none focus:ring-2 focus:ring-amber/20 focus:border-amber transition-all"
            />
            {errors.username && <p className="text-rose-rug text-ui-xs mt-1">{errors.username.message}</p>}
          </div>

          <div>
            <label className="block font-ui text-ui-sm text-stone-800 mb-1">Şifre</label>
            <input 
              {...register('password')}
              type="password"
              className="w-full bg-white border border-stone-200 p-3 rounded-card focus:outline-none focus:ring-2 focus:ring-amber/20 focus:border-amber transition-all"
            />
            {errors.password && <p className="text-rose-rug text-ui-xs mt-1">{errors.password.message}</p>}
          </div>

          <div>
            <label className="block font-ui text-ui-sm text-stone-800 mb-1">Doğum Tarihi</label>
            <input 
              {...register('birth_date')}
              type="date"
              className="w-full bg-white border border-stone-200 p-3 rounded-card focus:outline-none focus:ring-2 focus:ring-amber/20 focus:border-amber transition-all"
            />
            {errors.birth_date && <p className="text-rose-rug text-ui-xs mt-1">{errors.birth_date.message}</p>}
          </div>

          <div className="pt-2">
            <label className="flex items-start gap-3 cursor-pointer">
              <input 
                type="checkbox" 
                {...register('kvkk_approved')}
                className="mt-1 w-4 h-4 text-sienna border-stone-300 rounded focus:ring-sienna"
              />
              <span className="font-ui text-ui-sm text-stone-600">
                <a href="#" className="text-sienna underline">KVKK Aydınlatma Metnini</a> okudum ve onaylıyorum.
              </span>
            </label>
            {errors.kvkk_approved && <p className="text-rose-rug text-ui-xs mt-1">{errors.kvkk_approved.message}</p>}
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
          Zaten hesabınız var mı? <Link to="/giris" className="text-sienna font-semibold hover:underline">Giriş Yapın</Link>
        </p>
      </div>
    </div>
  );
};

export default RegisterPage;