import React from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

const Navbar = () => {
  const { isAuthenticated, user, logout } = useAuthStore();

  return (
    <nav className="bg-cream border-b border-stone-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-20 items-center">
          {/* Logo */}
          <Link to="/" className="font-display text-2xl text-sienna font-bold tracking-wide">
            KültürRota
          </Link>

          {/* Menü Linkleri */}
          <div className="hidden md:flex space-x-8">
            <Link to="/kesfet" className="font-ui text-stone-600 hover:text-sienna transition-colors">Keşfet</Link>
            
            {/* Rota Oluştur Linki: Sadece giriş yapmış kullanıcılar görebilir */}
            {isAuthenticated && (
              <Link to="/rota-olustur" className="font-ui text-sienna font-medium hover:text-amber transition-colors">Rota Oluştur</Link>
            )}
            
            {isAuthenticated && (
              <Link to="/rotalarim" className="font-ui text-stone-600 hover:text-sienna transition-colors">Rotalarım</Link>
            )}
          </div>

          {/* Giriş / Profil Aksiyonları */}
          <div className="flex items-center space-x-4">
            {isAuthenticated ? (
              <div className="flex items-center gap-4">
                <span className="font-ui text-sm text-stone-800">
                  Merhaba, {user?.username || 'Gezgin'}
                </span>
                <button 
                  onClick={logout}
                  className="font-ui text-sm text-rose-rug hover:underline"
                >
                  Çıkış
                </button>
              </div>
            ) : (
              <>
                <Link to="/giris" className="font-ui text-sm font-medium text-stone-600 hover:text-sienna">Giriş Yap</Link>
                <Link to="/kayit" className="font-ui text-sm font-medium bg-sienna text-white px-5 py-2.5 rounded-organic hover:bg-amber transition-all shadow-card">Kayıt Ol</Link>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;