import React from 'react';
import { MapPin } from 'lucide-react';
import { getCategoryConfig } from '../../constants/categories'; // Renk ve etiket ayarımızı çektik

const PlaceCard = ({ place }) => {
  if (!place) return null;

  const placeName = typeof place.isim === 'object' ? (place.isim?.tr || place.isim?.en || 'İsimsiz Mekan') : (place.isim || place.name || 'İsimsiz Mekan');
  
  const rawCategory = Array.isArray(place.kategori) && place.kategori.length > 0 
    ? place.kategori[0] 
    : (place.kategori || place.category);
    
  // İngilizce kodu gönderip, Türkçe etiket ve rengi alıyoruz
  const categoryConfig = getCategoryConfig(rawCategory);

  const city = place.sehir || place.il || place.city || 'Konum Belirtilmemiş';
  
  return (
    <div className="bg-white p-3 rounded-card shadow-card hover:shadow-card-hover transition-all mb-4 border border-stone-100 cursor-pointer flex gap-4 group">
      {/* Kapak Fotoğrafı */}
      <div className="w-24 h-24 rounded-lg bg-stone-200 overflow-hidden shrink-0 relative">
        {place.image_url || place.fotograf || place.gorsel ? (
          <img 
            src={place.image_url || place.fotograf || place.gorsel} 
            alt={placeName} 
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
        ) : (
          <div className="w-full h-full bg-sand flex flex-col items-center justify-center text-stone-400 font-ui text-xs text-center p-2">
            <span className="text-xl mb-1 opacity-50">🏛️</span>
            Görsel Yok
          </div>
        )}
      </div>

      {/* Mekan Bilgileri */}
      <div className="flex flex-col justify-center flex-grow">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span 
            className="text-ui-xs font-ui px-2 py-0.5 rounded-badge uppercase tracking-wider text-white"
            style={{ backgroundColor: categoryConfig.color }}
          >
            {categoryConfig.label}
          </span>
          {place.is_unesco && (
            <span className="text-ui-xs font-ui bg-turquoise/10 text-turquoise px-2 py-0.5 rounded-badge">
              UNESCO
            </span>
          )}
        </div>
        <h3 className="font-display text-lg text-obsidian leading-tight mb-1 group-hover:text-sienna transition-colors">
          {placeName}
        </h3>
        <p className="font-ui text-sm text-stone-500 flex items-center gap-1">
          <MapPin className="w-3.5 h-3.5" /> {city}
        </p>
      </div>
    </div>
  );
};

export default PlaceCard;