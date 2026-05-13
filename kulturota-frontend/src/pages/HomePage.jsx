import React from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Compass,
  Sparkles,
  Map as MapIcon,
  Camera,
  Loader2,
  ArrowRight,
  Star,
  Award,
} from 'lucide-react';
import { placeService } from '../services/placeService';
import { getCategoryConfig } from '../constants/categories';
import { useAuthStore } from '../store/authStore';

const resolvePlaceName = (place) => {
  if (!place) return 'İsimsiz Mekan';
  if (typeof place.isim === 'object') return place.isim?.tr || place.isim?.en || 'İsimsiz Mekan';
  return place.isim || place.name || 'İsimsiz Mekan';
};

const resolveCategory = (place) => {
  if (!place) return null;
  if (Array.isArray(place.kategori) && place.kategori.length > 0) return place.kategori[0];
  return place.kategori || place.category || null;
};

const extractItems = (response) => {
  const data = response?.data;
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if (Array.isArray(data.items)) return data.items;
  if (Array.isArray(data.data)) return data.data;
  return [];
};

const FeatureCard = ({ icon: Icon, title, description, to }) => (
  <Link
    to={to}
    className="group bg-white p-6 rounded-organic shadow-card border border-stone-100 hover:shadow-card-hover hover:border-amber transition-all flex flex-col"
  >
    <div className="w-12 h-12 rounded-full bg-sand flex items-center justify-center mb-4 group-hover:bg-amber/20 transition-colors">
      <Icon className="text-sienna" size={24} />
    </div>
    <h3 className="font-display text-xl text-obsidian mb-2 group-hover:text-sienna transition-colors">
      {title}
    </h3>
    <p className="font-body text-stone-600 text-sm leading-relaxed flex-grow">{description}</p>
    <div className="mt-4 flex items-center gap-1 text-sienna group-hover:text-amber font-ui text-sm font-semibold">
      Devam et <ArrowRight size={16} />
    </div>
  </Link>
);

const PlaceMiniCard = ({ place, badge }) => {
  const name = resolvePlaceName(place);
  const rawCategory = resolveCategory(place);
  const categoryConfig = getCategoryConfig(rawCategory);
  return (
    <Link
      to={`/mekanlar/${place.id}`}
      className="group bg-white rounded-organic shadow-card border border-stone-100 overflow-hidden hover:shadow-card-hover hover:border-amber transition-all flex flex-col"
    >
      <div className="relative h-40 bg-sand">
        {place.kapak_foto_url || place.image_url ? (
          <img
            src={place.kapak_foto_url || place.image_url}
            alt={name}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-4xl opacity-40">
            🏛️
          </div>
        )}
        {badge && (
          <span className="absolute top-3 left-3 bg-white/95 backdrop-blur px-2.5 py-1 rounded-badge font-ui text-xs text-sienna shadow-card">
            {badge}
          </span>
        )}
        {place.unesco && (
          <span className="absolute top-3 right-3 bg-turquoise text-white px-2 py-1 rounded-badge font-ui text-[10px] inline-flex items-center gap-1">
            <Award size={12} /> UNESCO
          </span>
        )}
      </div>
      <div className="p-4 flex flex-col flex-grow">
        <span
          className="inline-flex w-max text-[10px] font-ui px-2 py-0.5 rounded-badge uppercase tracking-wider text-white mb-2 whitespace-nowrap"
          style={{ backgroundColor: categoryConfig.color }}
        >
          {categoryConfig.label}
        </span>
        <h3 className="font-display text-base text-obsidian leading-tight line-clamp-2 group-hover:text-sienna transition-colors">
          {name}
        </h3>
        {place.kalite_skoru != null && (
          <div className="mt-2 flex items-center gap-1 text-amber text-xs font-ui">
            <Star size={14} fill="currentColor" />
            <span>{Number(place.kalite_skoru).toFixed(2)} / 1.00</span>
          </div>
        )}
      </div>
    </Link>
  );
};

const PlaceSection = ({ title, subtitle, places, isLoading, badge }) => (
  <section className="mb-12">
    <div className="flex items-end justify-between mb-5">
      <div>
        <h2 className="font-display text-2xl md:text-3xl text-obsidian">{title}</h2>
        {subtitle && <p className="font-body text-stone-600 text-sm mt-1">{subtitle}</p>}
      </div>
      <Link
        to="/kesfet"
        className="hidden sm:inline-flex items-center gap-1 font-ui text-sm text-sienna hover:text-amber font-semibold"
      >
        Tümünü Keşfet <ArrowRight size={16} />
      </Link>
    </div>
    {isLoading ? (
      <div className="flex items-center justify-center h-40 text-sienna">
        <Loader2 className="w-8 h-8 animate-spin" />
      </div>
    ) : places.length === 0 ? (
      <p className="font-ui text-stone-500 text-sm italic">Henüz veri yok.</p>
    ) : (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {places.map((place) => (
          <PlaceMiniCard key={place.id} place={place} badge={badge} />
        ))}
      </div>
    )}
  </section>
);

const HomePage = () => {
  const { user, isAuthenticated } = useAuthStore();

  const popularQuery = useQuery({
    queryKey: ['places', 'popular'],
    queryFn: () => placeService.list({ limit: 8 }),
  });
  const recentQuery = useQuery({
    queryKey: ['places', 'recent'],
    queryFn: () => placeService.list({ limit: 4, offset: 8 }),
  });
  const unescoQuery = useQuery({
    queryKey: ['places', 'unesco'],
    queryFn: () => placeService.list({ unesco: true, limit: 4 }),
  });

  const popularPlaces = extractItems(popularQuery.data);
  const recentPlaces = extractItems(recentQuery.data);
  const unescoPlaces = extractItems(unescoQuery.data);

  return (
    <div className="min-h-[calc(100vh-5rem)] bg-cream">
      {/* HERO */}
      <section className="relative overflow-hidden bg-gradient-to-br from-sand via-cream to-sand border-b border-stone-200">
        <div className="absolute inset-0 opacity-20 pointer-events-none">
          <div className="absolute -top-32 -right-32 w-96 h-96 bg-amber/30 rounded-full blur-3xl" />
          <div className="absolute -bottom-40 -left-40 w-[28rem] h-[28rem] bg-turquoise/30 rounded-full blur-3xl" />
        </div>
        <div className="relative max-w-6xl mx-auto px-6 py-16 md:py-24 text-center">
          {isAuthenticated && (
            <p className="font-ui text-stone-600 mb-3">
              Hoş geldin, <span className="text-sienna font-semibold">{user?.username || 'gezgin'}</span> 👋
            </p>
          )}
          <h1 className="font-display text-display-xl md:text-5xl text-sienna mb-4 leading-tight">
            Anadolu'nun Hafızasını Keşfet
          </h1>
          <p className="font-body text-stone-700 text-lg max-w-2xl mx-auto mb-8 leading-relaxed">
            İzmir'in kültürel miras mekanlarını keşfet, kendi rotanı çiz, yorumlarını ve
            fotoğraflarını toplulukla paylaş.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <Link
              to="/kesfet"
              className="inline-flex items-center gap-2 bg-sienna text-white px-7 py-3.5 rounded-organic font-ui font-semibold shadow-card hover:bg-amber transition-all"
            >
              <Compass size={18} /> Mekanları Keşfet
            </Link>
            {isAuthenticated ? (
              <Link
                to="/rota-olustur"
                className="inline-flex items-center gap-2 bg-white border border-stone-200 text-stone-700 px-7 py-3.5 rounded-organic font-ui font-semibold hover:border-amber transition-all"
              >
                <MapIcon size={18} /> Kendi Rotanı Çiz
              </Link>
            ) : (
              <Link
                to="/kayit"
                className="inline-flex items-center gap-2 bg-white border border-stone-200 text-stone-700 px-7 py-3.5 rounded-organic font-ui font-semibold hover:border-amber transition-all"
              >
                Ücretsiz katıl
              </Link>
            )}
          </div>
        </div>
      </section>

      {/* CONTENT */}
      <div className="max-w-7xl mx-auto px-6 py-12">
        {/* Quick-access cards */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-12">
          <FeatureCard
            icon={Compass}
            title="Keşfet"
            description="İzmir'in müze, antik kent, cami ve daha pek çok kültürel mekanını haritada keşfet."
            to="/kesfet"
          />
          <FeatureCard
            icon={MapIcon}
            title="Rota Oluştur"
            description="Bir günlük gezi planını adım adım hazırla, durakları sıraya diz."
            to={isAuthenticated ? '/rota-olustur' : '/giris'}
          />
          <FeatureCard
            icon={Camera}
            title="Anılarını Paylaş"
            description="Ziyaret ettiğin mekanlara puan, yorum ve fotoğraf ekleyerek topluluğa katkı sun."
            to="/kesfet"
          />
        </section>

        <PlaceSection
          title="Popüler Mekanlar"
          subtitle="En yüksek kalite skoruna sahip, sıklıkla ziyaret edilen yerler."
          places={popularPlaces.slice(0, 8)}
          isLoading={popularQuery.isLoading}
          badge="Popüler"
        />

        {unescoPlaces.length > 0 && (
          <PlaceSection
            title="UNESCO Mirası"
            subtitle="Dünya kültür mirası listesindeki seçkin alanlar."
            places={unescoPlaces}
            isLoading={unescoQuery.isLoading}
            badge="UNESCO"
          />
        )}

        {recentPlaces.length > 0 && (
          <PlaceSection
            title="Son Eklenenler"
            subtitle="Topluluğun ve ETL hattının kütüphaneye yeni kazandırdıkları."
            places={recentPlaces}
            isLoading={recentQuery.isLoading}
            badge="Yeni"
          />
        )}

        {/* CTA */}
        <section className="mt-4 bg-gradient-to-r from-sienna to-amber rounded-organic p-8 md:p-12 text-white shadow-card flex flex-col md:flex-row items-center gap-8">
          <div className="flex-shrink-0 w-16 h-16 bg-white/15 backdrop-blur rounded-full flex items-center justify-center">
            <Sparkles size={32} />
          </div>
          <div className="flex-grow text-center md:text-left">
            <h3 className="font-display text-2xl md:text-3xl mb-2">Keşif yolculuğuna hazır mısın?</h3>
            <p className="font-body text-white/90">
              Haritayı aç, kategoriye göre filtre uygula ve İzmir'in kültürel hafızasına dal.
            </p>
          </div>
          <Link
            to="/kesfet"
            className="inline-flex items-center gap-2 bg-white text-sienna px-6 py-3 rounded-organic font-ui font-semibold shadow-card hover:bg-sand transition-colors"
          >
            Şimdi Başla <ArrowRight size={18} />
          </Link>
        </section>
      </div>
    </div>
  );
};

export default HomePage;
